import requests

from core.context_manager import context_manager
from utils.logger import get_logger

logger = get_logger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen2.5:3b"
DEFAULT_TIMEOUT = 15

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

Rewrite the reply in a short, anime-inspired companion style.
Keep it to one or two short sentences.
Do not add new actions or promises.
Return only the rewritten reply.
"""


def _send_ollama_request(payload, timeout=DEFAULT_TIMEOUT):

    try:
        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=timeout
        )

        response.raise_for_status()

        data = response.json()

        if isinstance(data, dict):
            text = data.get("response")
        else:
            text = None

        return text.strip() if text else None

    except Exception as exc:
        logger.warning("Ollama request failed: %s", exc)
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
        "temperature": 0.0,
        "num_predict": 80,
    }
    result = _send_ollama_request(payload)
    if not result:
        return None

    normalized = result.splitlines()[0].strip().lower()
    if normalized == "unknown":
        return None
    return normalized


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
        "temperature": 0.3,
        "max_length": 80,
    }
    rewrite = _send_ollama_request(payload)
    if not rewrite:
        return base_reply

    cleaned = rewrite.splitlines()[0].strip()
    if not cleaned:
        return base_reply
    return cleaned
