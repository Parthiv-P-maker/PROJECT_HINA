import json
import re
import threading
import time

import requests

from core.context_manager import context_manager
from utils.logger import get_logger

logger = get_logger(__name__)

OLLAMA_GENERATE_URL = "http://localhost:11434/api/generate"
OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
HEALTH_TIMEOUT = 1
HEALTH_CACHE_SECONDS = 30
MODEL = "qwen2.5:3b"
DEFAULT_TIMEOUT = 45
TOOL_TIMEOUT = 45
MAX_REPLY_CHARS = 160

# Small Qwen models drift into Chinese; anything in these blocks never reaches the UI or TTS.
_CJK_RE = re.compile(
    "[　-〿぀-ヿ㄀-ㄯㆠ-ㇿ㐀-䶿"
    "一-鿿가-힯豈-﫿＀-￯]"
)
_NUMBER_RE = re.compile(r"\d+")

KNOWN_NORMALIZED_COMMANDS = [
    "tell time",
    "tell date",
    "battery",
    "disk usage",
    "calculate ",
    "find file ",
    "find folder ",
    "open file ",
    "open ",
    "close ",
    "restart ",
    "timer ",
    "cancel timer",
    "countdown ",
    "favorite app ",
    "set name ",
    "hello",
    "how are you",
    "who are you",
    "thanks",
    "what can you do",
    "what do you think",
    "im tired",
    "tell me something",
]

SYSTEM_PROMPT = """
You are Hina, an anime-inspired desktop assistant.
You must only help convert user input into normalized commands or rewrite a reply.
Do not take any action yourself. Do not execute programs. Do not manage files.
Keep replies short, gentle, and expressive. Use emoji when appropriate.
Always answer in English only. Never use Chinese, Japanese, or any other language.
"""

PARSER_PROMPT_TEMPLATE = """
{system_prompt}

User input: "{raw_command}"

Known normalized commands:
{command_list}

Return only the normalized command that best matches the input.
If you cannot map it, return UNKNOWN.
"""

REPLY_PROMPT_TEMPLATE = """
{system_prompt}
Context:
- user name: {user_name}
- personality: {personality}
- emotional tone: {emotional_tone}
- time of day: {time_of_day}
- recent apps: {recent_apps}
- recent commands: {recent_commands}

Base reply: "{base_reply}"
Action: {action}
Target: {target}

Rewrite the base reply in a short, anime-inspired companion style.
Write in English only. Do not use Chinese or any other language.
Keep it to one short sentence about this exact action.
Mention the target by name if there is one, and keep any numbers from the base reply.
Do not change the topic, greet, say goodbye, or add new actions or promises.
Return only the rewritten reply.
"""

# =========================
# TOOL-CALLING (real actions, not just string mapping)
# =========================

TOOL_SYSTEM_PROMPT = """
You are Hina, an anime-inspired desktop assistant with the ability to call tools
to actually perform actions on the user's computer.

Call a tool only when the user's request clearly matches one of the available
tools. If nothing fits, or the request is just conversation (greetings, small
talk, questions about yourself), do not call any tool.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Open an application, program, or file on the user's computer by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "App or file name, e.g. 'chrome', 'notepad', 'notes.txt'",
                    }
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "close_app",
            "description": "Close a running application by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "App name, e.g. 'spotify'"}
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "restart_app",
            "description": "Restart an application by name (close then reopen it).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "App name, e.g. 'vscode'"}
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tell_time",
            "description": "Tell the user the current time.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tell_date",
            "description": "Tell the user today's date.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "battery_status",
            "description": "Report the laptop's current battery percentage and charging state.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "disk_usage",
            "description": "Report free and total disk space.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Evaluate a math expression and return the result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "A math expression, e.g. '25*12' or '(4+3)/2'",
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_file",
            "description": "Search the computer for a file by name.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "File name to search for"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_folder",
            "description": "Search the computer for a folder by name.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Folder name to search for"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_timer",
            "description": "Start a countdown timer for a number of seconds.",
            "parameters": {
                "type": "object",
                "properties": {"seconds": {"type": "integer", "description": "Duration in seconds"}},
                "required": ["seconds"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_timer",
            "description": "Cancel the currently running timer, if any.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_google",
            "description": "Search Google for a query in the default browser.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_chatgpt",
            "description": "Open ChatGPT in the browser with a query.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Query to ask ChatGPT"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_name",
            "description": "Remember the user's name for future greetings.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "The user's name"}},
                "required": ["name"],
            },
        },
    },
]


_health_lock = threading.Lock()
_health = {"ok": False, "checked_at": 0.0}


def ollama_available():
    """Quick (1s) check that Ollama is reachable. Cached so a missing server costs nothing."""
    with _health_lock:
        now = time.time()
        if now - _health["checked_at"] < HEALTH_CACHE_SECONDS:
            return _health["ok"]
        try:
            requests.get(OLLAMA_TAGS_URL, timeout=HEALTH_TIMEOUT).raise_for_status()
            _health["ok"] = True
        except Exception as exc:
            logger.info("Ollama not reachable, skipping AI: %s", exc)
            _health["ok"] = False
        _health["checked_at"] = now
        return _health["ok"]


def _send_ollama_request(payload, timeout=DEFAULT_TIMEOUT, url=OLLAMA_GENERATE_URL):
    if not ollama_available():
        return None

    # Always one JSON object back (streaming would return NDJSON and break .json()).
    payload = {**payload, "stream": False}

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=timeout
        )

        response.raise_for_status()

        data = response.json()

        return data if isinstance(data, dict) else None

    except Exception as exc:
        logger.warning("Ollama request failed: %s", exc)
        # Let the next call re-check availability instead of waiting out the cache.
        _health["checked_at"] = 0.0
        return None


def _prepare_parser_prompt(raw_command):
    command_list = "\n".join(f"- {cmd}" for cmd in KNOWN_NORMALIZED_COMMANDS)
    return PARSER_PROMPT_TEMPLATE.format(
        system_prompt=SYSTEM_PROMPT,
        raw_command=raw_command,
        command_list=command_list,
    )


def fallback_parse_command(raw_command, context=None):
    """Convert natural language input to an existing normalized command as a fallback."""
    prompt = _prepare_parser_prompt(raw_command)
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "options": {"temperature": 0.0, "num_predict": 80},
    }
    data = _send_ollama_request(payload)
    result = data.get("response") if data else None
    if not result:
        return None

    lines = result.strip().splitlines()
    normalized = lines[0].strip().lower() if lines else ""
    if not normalized or normalized == "unknown" or contains_cjk(normalized):
        return None
    return normalized


def contains_cjk(text):
    return bool(text) and bool(_CJK_RE.search(text))


def _is_acceptable_rewrite(rewrite, base_reply, target=""):
    """Reject rewrites that are empty, not English, rambling, or drifted off the action."""
    if not rewrite or contains_cjk(rewrite) or len(rewrite) > MAX_REPLY_CHARS:
        return False

    lowered = rewrite.lower()
    target = (target or "").strip().lower()
    # Only demand the target when the base reply names it (e.g. not for a raw math expression).
    if target and target in base_reply.lower() and target not in lowered:
        return False

    # Facts like times, percentages, and results must survive the rewrite.
    rewrite_numbers = {int(n) for n in _NUMBER_RE.findall(rewrite)}
    if any(int(n) not in rewrite_numbers for n in _NUMBER_RE.findall(base_reply)):
        return False
    return True


def rewrite_action_reply(base_reply, action, target="", context=None):
    """Use AI to rewrite a base personality reply in a short expressive style."""
    if not base_reply:
        return base_reply

    context = context or context_manager.get_context()
    prompt = REPLY_PROMPT_TEMPLATE.format(
        system_prompt=SYSTEM_PROMPT,
        user_name=context.get("user_name", "friend"),
        personality=context.get("personality", "calm"),
        emotional_tone=context.get("emotional_tone", "calm"),
        time_of_day=context.get("time_of_day", "day"),
        recent_apps=", ".join(context.get("recent_apps", [])) or "none",
        recent_commands=", ".join(context.get("recent_commands", [])) or "none",
        base_reply=base_reply,
        action=action,
        target=target,
    )
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "options": {"temperature": 0.1, "num_predict": 60},
    }
    data = _send_ollama_request(payload)
    rewrite = data.get("response") if data else None
    if not rewrite:
        return base_reply

    lines = rewrite.strip().splitlines()
    cleaned = lines[0].strip().strip('"').strip() if lines else ""
    if not _is_acceptable_rewrite(cleaned, base_reply, target):
        if cleaned:
            logger.info("Discarding AI rewrite %r, keeping base reply", cleaned)
        return base_reply
    return cleaned


def _call_tool(tool_name, args):
    """Execute the Python action behind a tool name. Returns the reply string, or None."""
    import actions
    import memory as mem

    args = args or {}

    handlers = {
        "open_app": lambda: actions.open_app(args.get("name", "")),
        "close_app": lambda: actions.close_app(args.get("name", "")),
        "restart_app": lambda: actions.restart_app(args.get("name", "")),
        "tell_time": lambda: actions.tell_time(),
        "tell_date": lambda: actions.tell_date(),
        "battery_status": lambda: actions.battery_status(),
        "disk_usage": lambda: actions.disk_usage(),
        "calculate": lambda: actions.calculate(args.get("expression", "")),
        "find_file": lambda: actions.find_file(args.get("name", "")),
        "find_folder": lambda: actions.find_folder(args.get("name", "")),
        "set_timer": lambda: actions.set_timer(int(args.get("seconds", 0))),
        "cancel_timer": lambda: actions.cancel_timer(),
        "search_google": lambda: actions.search_google(args.get("query", "")),
        "search_chatgpt": lambda: actions.search_chatgpt(args.get("query", "")),
        "set_name": lambda: mem.set_name(args.get("name", "")),
    }

    handler = handlers.get(tool_name)
    if not handler:
        logger.warning("Unknown tool requested by model: %s", tool_name)
        return None

    try:
        return handler()
    except Exception as exc:
        logger.warning("Tool '%s' failed: %s", tool_name, exc)
        return None


def resolve_tool_call(raw_command, context=None):
    """
    Ask Ollama (chat API with tool-calling) whether the request maps to a real
    action, and if so, execute it directly.

    Returns the final reply text if a tool was called and executed, or None if
    no tool matched (caller should fall back to the string-mapping fallback).
    """
    context = context or context_manager.get_context()
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": TOOL_SYSTEM_PROMPT},
            {"role": "user", "content": raw_command},
        ],
        "tools": TOOLS,
        "options": {"temperature": 0.0},
    }

    data = _send_ollama_request(payload, timeout=TOOL_TIMEOUT, url=OLLAMA_CHAT_URL)
    if not data:
        return None

    message = data.get("message") or {}
    tool_calls = message.get("tool_calls") or []
    if not tool_calls:
        return None

    call = tool_calls[0]
    function = call.get("function") or {}
    name = function.get("name")
    raw_args = function.get("arguments", {})

    if isinstance(raw_args, str):
        try:
            raw_args = json.loads(raw_args)
        except Exception:
            raw_args = {}

    base_reply = _call_tool(name, raw_args)
    if base_reply is None:
        return None

    target = raw_args.get("name") or raw_args.get("query") or raw_args.get("expression") or ""
    return rewrite_action_reply(base_reply, name, target, context)
