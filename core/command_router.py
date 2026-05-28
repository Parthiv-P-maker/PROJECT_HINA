from parser import normalize_command
from core.ai_engine import fallback_parse_command
from core.context_manager import context_manager

KNOWN_COMMAND_PREFIXES = [
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


def _is_known_command(normalized_command):
    if normalized_command in KNOWN_COMMAND_PREFIXES:
        return True
    return any(normalized_command.startswith(prefix) for prefix in KNOWN_COMMAND_PREFIXES)


def route_command(raw_command):
    """Normalize user input and optionally use AI fallback for natural language."""
    clean_text = raw_command.strip().lower()
    normalized = normalize_command(clean_text)

    if _is_known_command(normalized):
        context_manager.register_command(raw_command, normalized, success=True)
        return normalized

    ai_fallback = fallback_parse_command(clean_text, context_manager.get_context())
    if ai_fallback and _is_known_command(ai_fallback):
        context_manager.register_command(raw_command, ai_fallback, success=True)
        return ai_fallback

    context_manager.register_command(raw_command, normalized, success=False)
    return normalized
