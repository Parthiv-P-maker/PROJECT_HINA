from parser import normalize_command
from core.ai_loader import get_ai_engine
from core.context_manager import context_manager
import threading

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
    "search google ",
    "search chatgpt ",
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
    """
    Normalize user input and optionally use AI fallback for natural language.
    AI fallback is only attempted if command is not recognized via pattern matching.
    """
    clean_text = raw_command.strip().lower()
    normalized = normalize_command(clean_text)

    if _is_known_command(normalized):
        context_manager.register_command(raw_command, normalized, success=True)
        return normalized

    # Try AI fallback only if pattern matching failed
    # This is deferred via lazy loading to avoid startup blocking
    ai_engine = get_ai_engine()
    if ai_engine and hasattr(ai_engine, 'fallback_parse_command'):
        try:
            ai_fallback = ai_engine.fallback_parse_command(clean_text, context_manager.get_context())
            if ai_fallback and _is_known_command(ai_fallback):
                context_manager.register_command(raw_command, ai_fallback, success=True)
                return ai_fallback
        except Exception:
            pass  # Fall through to normalized command

    context_manager.register_command(raw_command, normalized, success=False)
    return normalized
