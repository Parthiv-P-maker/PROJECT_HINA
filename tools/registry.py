"""
The single tool registry.

Every command Hina understands is one `@tool(...)`-decorated function. From
that one definition the registry generates:

  * the parser's matching          -> normalize()
  * the Ollama tool schema         -> ai_schemas() / call_ai()
  * the router's known commands    -> known_prefixes()
  * the AI string-mapping prompt   -> prompt_commands()
  * dispatch                       -> find_for_command() / dispatch()
  * the permission tier            -> permissions.TIERS

See tools/README.md.
"""

import inspect
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from core import permissions
from core.permissions import SAFE, CONFIRM, BLOCKED  # noqa: F401  (re-exported for tool modules)
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class DispatchResult:
    reply: str = ""
    should_exit: bool = False
    exit_delay_ms: int = 0
    needs_confirmation: bool = False


@dataclass
class Param:
    """One tool parameter, as the model sees it."""
    description: str
    type: str = "string"
    required: bool = True


@dataclass
class ToolContext:
    """What a handler can see about the call that reached it."""
    tool: "Tool"
    command: str = ""          # the full normalized command ("open chrome")
    arg: str = ""              # everything after the command prefix ("chrome" for "open chrome")
    via_ai: bool = False       # True when the model's tool call (not typed text) got here
    output_var: object = None  # GUI hooks, only set for typed/spoken commands
    output_label: object = None
    app: object = None

    def run(self, target, fn):
        """Run `fn` under this tool's permission tier (logs; asks first if 'confirm')."""
        return permissions.run_action(self.tool.name, target, fn)


@dataclass
class Tool:
    name: str                      # AI tool name, action-log name and permission-tier key
    description: str
    params: Dict[str, Param]
    command: str                   # canonical normalized form; a prefix ("open ") if it takes an argument
    handler: Callable
    tier: str = SAFE
    ai: bool = False               # expose to the model's tool calling
    aliases: tuple = ()            # other exact normalized commands that dispatch here
    router: bool = True            # counts as a known command for route_command
    prompt: bool = True            # listed in the AI string-mapping prompt
    priority: int = 50             # parse order (lower first); ties keep registration order
    parse: Optional[Callable] = None
    triggers: tuple = ()           # substrings that map free text to `command`
    exact_triggers: tuple = ()     # whole-input phrases that map free text to `command`
    starts: tuple = ()             # inputs already in normalized form that must stop here
    _seq: int = field(default=0, repr=False)

    @property
    def takes_arg(self):
        return bool(self.params)

    def matches_command(self, command):
        if self.takes_arg:
            return command.startswith(self.command)
        return command == self.command or command in self.aliases

    def parse_text(self, text):
        """Normalized command for `text`, or None if this tool doesn't claim it."""
        if self.parse:
            return self.parse(text)
        if text in self.exact_triggers or any(t in text for t in self.triggers):
            return self.command
        if any(text.startswith(s) for s in self.starts):
            return text
        return None

    def schema(self):
        parameters = {
            "type": "object",
            "properties": {
                key: {"type": p.type, "description": p.description}
                for key, p in self.params.items()
            },
        }
        required = [key for key, p in self.params.items() if p.required]
        if required:
            parameters["required"] = required
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": parameters},
        }


_TOOLS: Dict[str, Tool] = {}
_loaded = False


def tool(name, description, params=None, *, command, tier=SAFE, ai=False, aliases=(),
         router=True, prompt=True, priority=50, parse=None, triggers=(),
         exact_triggers=(), starts=()):
    """Register a function as a tool. See tools/README.md for the fields."""
    def decorate(fn):
        if name in _TOOLS:
            raise ValueError(f"duplicate tool name: {name}")
        _TOOLS[name] = Tool(
            name=name, description=description, params=dict(params or {}), command=command,
            handler=fn, tier=tier, ai=ai, aliases=tuple(aliases), router=router, prompt=prompt,
            priority=priority, parse=parse, triggers=tuple(triggers),
            exact_triggers=tuple(exact_triggers), starts=tuple(starts), _seq=len(_TOOLS),
        )
        permissions.TIERS[name] = tier
        return fn
    return decorate


def ensure_loaded():
    global _loaded
    if not _loaded:
        _loaded = True
        import tools  # noqa: F401  (importing the package registers every builtin)


def all_tools() -> List[Tool]:
    ensure_loaded()
    return list(_TOOLS.values())


def get(name) -> Optional[Tool]:
    ensure_loaded()
    return _TOOLS.get(name)


# ---- parser ----------------------------------------------------------------

def normalize(text):
    """Map already-lowercased, prefix-stripped text onto a normalized command, or None."""
    for entry in sorted(all_tools(), key=lambda t: (t.priority, t._seq)):
        normalized = entry.parse_text(text)
        if normalized is not None:
            return normalized
    return None


# ---- router / AI prompt ------------------------------------------------------

def known_prefixes():
    out = []
    for entry in all_tools():
        if entry.router:
            for cmd in (entry.command, *entry.aliases):
                if cmd not in out:
                    out.append(cmd)
    return out


def prompt_commands():
    return [t.command for t in all_tools() if t.prompt]


# ---- dispatch ---------------------------------------------------------------

def is_known_command(command):
    """True if a router-visible tool owns this normalized command."""
    return any(t.router and t.matches_command(command) for t in all_tools())


def find_for_command(command) -> Optional[Tool]:
    """The tool a normalized command belongs to (longest matching prefix wins)."""
    best = None
    for entry in all_tools():
        if entry.matches_command(command):
            if best is None or len(entry.command) > len(best.command):
                best = entry
    return best


def _invoke(entry, ctx):
    return entry.handler(ctx) if inspect.signature(entry.handler).parameters else entry.handler()


def dispatch(command, **gui):
    """Run a normalized command. Returns a DispatchResult, or None if no tool owns it."""
    entry = find_for_command(command)
    if entry is None:
        return None
    arg = command[len(entry.command):] if entry.takes_arg else ""
    out = _invoke(entry, ToolContext(tool=entry, command=command, arg=arg, **gui))
    return out if isinstance(out, DispatchResult) else DispatchResult(reply=out or "")


# ---- Ollama tool calling ----------------------------------------------------

def ai_schemas():
    return [t.schema() for t in all_tools() if t.ai]


def call_ai(name, args):
    """Execute a model-requested tool. Returns the reply string, or None if unknown/failed."""
    entry = get(name)
    if entry is None or not entry.ai:
        logger.warning("Unknown tool requested by model: %s", name)
        return None
    args = args or {}
    try:
        values = []
        for key, param in entry.params.items():
            value = args.get(key, 0 if param.type == "integer" else "")
            values.append(str(int(value)) if param.type == "integer" else str(value))
        ctx = ToolContext(tool=entry, command=entry.command, arg=values[0] if values else "",
                          via_ai=True)
        out = _invoke(entry, ctx)
    except Exception as exc:
        logger.warning("Tool '%s' failed: %s", name, exc)
        return None
    return out.reply if isinstance(out, DispatchResult) else out


# ---- helpers for tool modules -------------------------------------------------

_MY = re.compile(r"\bmy\b\s*")


def drop_my(text):
    """Drop the word "my" from a target: "my notes" -> "notes"."""
    return _MY.sub("", text).strip()


def ask_or_reply(reply):
    """A reply that may be a pending "Should I?" question (shows Yes/No buttons)."""
    return DispatchResult(reply=reply, needs_confirmation=permissions.has_pending())
