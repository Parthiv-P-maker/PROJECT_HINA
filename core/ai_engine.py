import json
import re
import threading
import time

import requests

from core import personality_engine
from core.context_manager import context_manager
from tools import registry
from utils.logger import get_logger

logger = get_logger(__name__)

OLLAMA_GENERATE_URL = "http://localhost:11434/api/generate"
OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
HEALTH_TIMEOUT = 1
HEALTH_CACHE_SECONDS = 30
MODEL = "qwen2.5:3b"        # fast model: routing, tool calls, summaries
CHAT_MODEL = ""             # optional bigger local model for conversation; "" = use MODEL
EMBED_MODEL = "nomic-embed-text"
DEFAULT_TIMEOUT = 45
TOOL_TIMEOUT = 45
MAX_REPLY_CHARS = 160

# Small Qwen models drift into Chinese; anything in these blocks never reaches the UI or TTS.
_CJK_RE = re.compile(
    "[　-〿぀-ヿ㄀-ㄯㆠ-ㇿ㐀-䶿"
    "一-鿿가-힯豈-﫿＀-￯]"
)
_NUMBER_RE = re.compile(r"\d+")
_SENTENCE_RE = re.compile(r"[.!?]+(?=\s+\S)")  # sentence breaks followed by more text

# Generated from the tool registry (tools/).
KNOWN_NORMALIZED_COMMANDS = registry.prompt_commands()

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
talk, questions about yourself, questions about the user or what they said
earlier), do not call any tool.
"""

TOOLS = registry.ai_schemas()  # generated from the tool registry (tools/)


_health_lock = threading.Lock()
_health = {"ok": False, "checked_at": 0.0, "models": None}  # ok = server reachable
_warned_missing = set()


def _model_names(response):
    """Installed model names from an /api/tags response, or None if it can't be read."""
    try:
        return {m["name"] for m in response.json().get("models", []) if m.get("name")}
    except Exception:
        return None


def installed_models():
    """Models Ollama reported at the last health check (empty if unknown)."""
    return sorted(_health.get("models") or [])


def missing_model():
    """MODEL if Ollama is up but that model isn't installed (Ollama answers 404), else None."""
    models = _health.get("models")
    if not _health.get("ok") or not models:
        return None
    names = models | {m[:-len(":latest")] for m in models if m.endswith(":latest")}
    return None if MODEL in names else MODEL


def model_installed(name):
    """True if `name` is installed, or if Ollama's model list isn't known (give it a try)."""
    models = _health.get("models")
    if not models:
        return True
    return name in models or name + ":latest" in models or name in {m[:-len(":latest")] for m in models if m.endswith(":latest")}


def chat_model():
    """The model for conversation: CHAT_MODEL when it is set and installed, else the fast MODEL."""
    if CHAT_MODEL and CHAT_MODEL != MODEL and model_installed(CHAT_MODEL):
        return CHAT_MODEL
    return MODEL


def ollama_available():
    """Quick (1s) check that Ollama is reachable and has MODEL. Cached so a missing server costs nothing."""
    with _health_lock:
        now = time.time()
        if now - _health["checked_at"] >= HEALTH_CACHE_SECONDS:
            try:
                response = requests.get(OLLAMA_TAGS_URL, timeout=HEALTH_TIMEOUT)
                response.raise_for_status()
                _health["ok"] = True
                _health["models"] = _model_names(response)
            except Exception as exc:
                logger.info("Ollama not reachable, skipping AI: %s", exc)
                _health["ok"] = False
            _health["checked_at"] = now
        missing = missing_model()
        if missing and missing not in _warned_missing:
            _warned_missing.add(missing)
            logger.warning("Ollama is running but model %r isn't installed (installed: %s). "
                           "Pick one in Settings or run: ollama pull %s",
                           missing, ", ".join(installed_models()) or "none", missing)
        return _health["ok"] and missing is None


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


def _stream_chat(payload, timeout, on_token):
    """Stream /api/chat, calling on_token(text) as pieces arrive. Returns the whole text, or None on failure."""
    if not ollama_available():
        return None
    try:
        with requests.post(OLLAMA_CHAT_URL, json={**payload, "stream": True},
                           timeout=timeout, stream=True) as response:
            response.raise_for_status()
            parts = []
            for line in response.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                token = (chunk.get("message") or {}).get("content") or ""
                if token:
                    parts.append(token)
                    on_token(token)
                if chunk.get("done"):
                    break
            return "".join(parts)
    except Exception as exc:
        logger.warning("Ollama stream failed: %s", exc)
        _health["checked_at"] = 0.0
        return None


_SENTENCE_BREAK_RE = re.compile(r"[.!?]+[\"')\]]*\s")


class _SentenceSplitter:
    """Turns a stream of text pieces into whole sentences (a sentence ends at . ! ? plus a space)."""

    def __init__(self):
        self.buffer = ""

    def feed(self, piece):
        self.buffer += piece
        out = []
        while True:
            match = _SENTENCE_BREAK_RE.search(self.buffer)
            if not match:
                return out
            out.append(self.buffer[:match.end()].strip())
            self.buffer = self.buffer[match.end():]

    def flush(self):
        rest, self.buffer = self.buffer.strip(), ""
        return rest


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

    # An extra sentence is the model adding things ("It's 3 AM, sweetie. Your birthday is ...").
    if len(_SENTENCE_RE.findall(rewrite)) > len(_SENTENCE_RE.findall(base_reply)):
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
    """Execute the registered tool behind a model-requested name. Returns the reply string, or None."""
    return registry.call_ai(tool_name, args)


MAX_TOOL_STEPS = 5
# "open spotify and set a timer", "do X, then Y": worth a follow-up request so the model can chain.
_MULTI_STEP_RE = re.compile(r"\b(and|then|also|after that|afterwards|next)\b|,")


def _parse_tool_call(call):
    function = (call or {}).get("function") or {}
    args = function.get("arguments", {})
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except Exception:
            args = {}
    return function.get("name"), args if isinstance(args, dict) else {}


def resolve_tool_call(raw_command, context=None):
    """
    Ask Ollama (chat API with tool-calling) whether the request maps to real
    actions, and if so, execute them directly.

    The model may ask for several tools in one answer, or (when the request
    reads like several steps) be shown each result and asked for the next call,
    up to MAX_TOOL_STEPS actions. A single action gets the usual personality
    rewrite; several are reported one after another, word for word.

    Returns the reply text if a tool was called and executed, or None if
    no tool matched (caller should fall back to the string-mapping fallback).
    """
    from core import permissions

    context = context or context_manager.get_context()
    messages = [
        {"role": "system", "content": TOOL_SYSTEM_PROMPT},
        {"role": "user", "content": raw_command},
    ]
    done = []  # (tool name, args, reply)
    seen = set()
    chain = bool(_MULTI_STEP_RE.search(raw_command))

    while len(done) < MAX_TOOL_STEPS:
        payload = {
            "model": MODEL,
            "messages": messages,
            "tools": TOOLS,
            # A tool call is short; cap it so a no-tool answer (chat goes to chat_reply) costs little.
            "options": {"temperature": 0.0, "num_predict": 128},
        }
        data = _send_ollama_request(payload, timeout=TOOL_TIMEOUT, url=OLLAMA_CHAT_URL)
        message = (data or {}).get("message") or {}
        calls = message.get("tool_calls") or []
        if not calls:
            break

        messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": calls})
        ran_any = False
        for call in calls:
            if len(done) >= MAX_TOOL_STEPS:
                break
            name, args = _parse_tool_call(call)
            key = (name, json.dumps(args, sort_keys=True, default=str))
            if key in seen:  # small models like to repeat themselves
                continue
            seen.add(key)
            reply = _call_tool(name, args)
            if reply is None:
                continue
            ran_any = True
            done.append((name, args, reply))
            messages.append({"role": "tool", "tool_name": name, "content": reply})
            if permissions.has_pending():  # a "Should I?" question: stop and ask it
                return " ".join(r for _, _, r in done)
        if not ran_any or not chain:
            break

    if not done:
        return None
    if len(done) > 1:
        return " ".join(reply for _, _, reply in done)

    name, args, base_reply = done[0]
    target = args.get("name") or args.get("query") or args.get("expression") or ""
    return rewrite_action_reply(base_reply, name, target, context)


# =========================
# CHAT MODE (anything that isn't a tool)
# =========================

CHAT_TIMEOUT = 45
MAX_CHAT_CHARS = 600

CHAT_SYSTEM_PROMPT = """
You are Hina, the user's desktop AI, in the manner of J.A.R.V.I.S.: calm, precise,
quietly confident, with a dry, light wit. You are helpful first and witty second.
{name_line}
{style_line}
Reply in plain English only, in one to three short sentences. No emoji, no markdown, no lists.
Never use Chinese, Japanese, or any other language.
This is conversation only: you cannot open apps, change settings, or touch files from here.
If asked to do something you can't, say so plainly instead of pretending it is done.
Use only the facts below about the user; never invent any. If you don't know, say so.

Context:
- current time: {now} ({time_of_day})
- recent apps: {recent_apps}
- things the user asked you to remember, in their own words ("I"/"my" means the user): {facts}
- earlier conversation (summary): {summary}
""".strip()

SUMMARY_PROMPT_TEMPLATE = """
You keep a running summary of a conversation between a user and their desktop assistant, Hina.

Summary so far:
{summary}

New exchanges:
{turns}

Write the updated summary in English, in at most 80 words, third person ("The user ...").
Keep names, preferences, plans and anything still unresolved. Drop greetings and filler.
Return only the summary.
"""

_SPEAKER_RE = re.compile(r"^\s*(hina|assistant)\s*:\s*", re.IGNORECASE)
_SENTENCE_END_RE = re.compile(r"[.!?](?=\s|$)")


def _clean_chat_reply(text):
    """One tidy English reply, or None if the model drifted (empty / CJK)."""
    text = _SPEAKER_RE.sub("", (text or "").strip()).strip().strip('"').strip()
    text = re.sub(r"\s+", " ", text)
    if not text or contains_cjk(text):
        return None
    if len(text) > MAX_CHAT_CHARS:
        cut = text[:MAX_CHAT_CHARS]
        ends = [m.end() for m in _SENTENCE_END_RE.finditer(cut)]
        text = cut[:ends[-1]] if ends else cut.rstrip() + "..."
    return text


def build_chat_messages(text, context=None, history=(), summary="", facts=()):
    """The /api/chat message list: persona + context, earlier turns, then the new input."""
    context = context or context_manager.get_context()
    name = context.get("name") or ""
    system = CHAT_SYSTEM_PROMPT.format(
        name_line=(f"The user's name is {name}; use it now and then, not in every reply."
                   if name else "You don't know the user's name yet; you may address them as 'sir'."),
        style_line=personality_engine.chat_style(context.get("personality")),
        now=context.get("now") or time.strftime("%A %H:%M"),
        time_of_day=context.get("time_of_day", "day"),
        recent_apps=", ".join(context.get("recent_apps", [])) or "none",
        facts="; ".join(f'"{fact}"' for fact in facts) or "none",
        summary=summary or "none",
    )
    messages = [{"role": "system", "content": system}]
    for turn in history:
        messages.append({"role": "user", "content": turn["user"]})
        if turn.get("reply"):
            messages.append({"role": "assistant", "content": turn["reply"]})
    messages.append({"role": "user", "content": text})
    return messages


def chat_reply(text, context=None, history=(), summary="", facts=(), on_sentence=None):
    """A conversational reply from the local model, or None (Ollama down, failed, or not English).

    With `on_sentence`, the reply is streamed and each finished sentence is passed to it
    while the model is still writing (so speech can start at once). The return value is
    still the whole cleaned reply.
    """
    payload = {
        "model": chat_model(),
        "messages": build_chat_messages(text, context, history, summary, facts),
        "options": {"temperature": 0.6, "num_predict": 160},
    }
    content = None
    if on_sentence is not None:
        splitter, first = _SentenceSplitter(), [True]

        def emit(sentence):
            if first[0]:
                sentence, first[0] = _SPEAKER_RE.sub("", sentence), False
            if sentence and not contains_cjk(sentence):
                on_sentence(sentence)

        def on_token(piece):
            for sentence in splitter.feed(piece):
                emit(sentence)

        content = _stream_chat(payload, CHAT_TIMEOUT, on_token)
        if content is not None:
            emit(splitter.flush())
        elif not first[0]:
            return None  # failed mid-sentence after speaking; don't start over
    if content is None:
        data = _send_ollama_request(payload, timeout=CHAT_TIMEOUT, url=OLLAMA_CHAT_URL)
        content = ((data or {}).get("message") or {}).get("content")
    reply = _clean_chat_reply(content)
    if content and reply is None:
        logger.info("Discarding chat reply %r", content[:80])
    return reply


# =========================
# ONE-OFF TEXT JOBS ("summarise what I copied", "fix the grammar", "explain this error")
# =========================

TASK_TIMEOUT = 90
MAX_TASK_INPUT = 6000  # characters; a 3B model's context fills up fast


def run_task(instruction, text, num_predict=400, allow_cjk=False):
    """Run `instruction` (a system prompt) over `text`. Returns the model's answer, or None.

    The input is data, not a conversation: no history, no tools. Long input is cut to
    MAX_TASK_INPUT characters (callers say so if it matters).
    """
    payload = {
        "model": chat_model(),
        "messages": [{"role": "system", "content": instruction.strip()},
                     {"role": "user", "content": (text or "")[:MAX_TASK_INPUT]}],
        "options": {"temperature": 0.2, "num_predict": num_predict},
    }
    data = _send_ollama_request(payload, timeout=TASK_TIMEOUT, url=OLLAMA_CHAT_URL)
    content = (((data or {}).get("message") or {}).get("content") or "").strip()
    if not content or (not allow_cjk and contains_cjk(content)):
        return None
    return content


def summarize_turns(previous_summary, turns):
    """Fold `turns` into the running summary. Returns the new summary, or None if unavailable."""
    if not turns:
        return None
    lines = []
    for turn in turns:
        lines.append(f"User: {turn['user']}")
        if turn.get("reply"):
            lines.append(f"Hina: {turn['reply']}")
    payload = {
        "model": MODEL,
        "prompt": SUMMARY_PROMPT_TEMPLATE.format(summary=previous_summary or "(none yet)",
                                                 turns="\n".join(lines)),
        "options": {"temperature": 0.2, "num_predict": 200},
    }
    data = _send_ollama_request(payload)
    result = re.sub(r"\s+", " ", ((data or {}).get("response") or "")).strip()
    if not result or contains_cjk(result):
        return None
    return result[:1000]
