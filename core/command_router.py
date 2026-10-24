from parser import normalize_command
from core.ai_loader import get_ai_engine
from core.context_manager import context_manager
import threading
from core import permissions
from tools import registry
from core.conversation import CHAT_PREFIX, is_personal_question

# Generated from the tool registry (tools/); kept for introspection.
KNOWN_COMMAND_PREFIXES = registry.known_prefixes()


def _is_known_command(normalized_command):
    return registry.is_known_command(normalized_command)


# Commands whose argument is stored as typed: put back the capitals lowercasing removed.
_KEEP_CASE = ("set name ", "remember fact ")


def _restore_case(raw_command, normalized):
    for prefix in _KEEP_CASE:
        if normalized.startswith(prefix):
            arg = normalized[len(prefix):]
            at = raw_command.lower().rfind(arg)
            if arg and at >= 0 and raw_command[at:at + len(arg)].lower() == arg:
                return prefix + raw_command[at:at + len(arg)]
    return normalized


def route_command(raw_command):
    """
    Normalize user input and optionally use AI fallback for natural language.
    AI fallback is only attempted if command is not recognized via pattern matching.
    Input no tool claims comes back as "chat::<input>" (chat mode).
    """
    clean_text = raw_command.strip().lower()
    # A pending "Should I?" gets first claim on yes/no; anything else drops it.
    if permissions.has_pending():
        answer = permissions.parse_answer(clean_text)
        if answer is not None:
            return "confirm yes" if answer else "confirm no"
        permissions.cancel_pending("ignored")

    normalized = _restore_case(raw_command, normalize_command(clean_text))

    if _is_known_command(normalized):
        context_manager.register_command(raw_command, normalized, success=True)
        return normalized

    # "When is my birthday?" / "what did I say about Friday?" are for chat, which has the
    # facts and history; tool calling would answer them with the date or a wrong tool.
    if is_personal_question(clean_text):
        context_manager.register_command(raw_command, "chat", success=True)
        return CHAT_PREFIX + raw_command.strip()

    # Try AI fallback only if pattern matching failed
    # This is deferred via lazy loading to avoid startup blocking
    ai_engine = get_ai_engine()
    if ai_engine:
        # 1. Real tool-calling: let the model invoke an action directly instead
        #    of only mapping onto one of the ~25 known command strings.
        if hasattr(ai_engine, 'resolve_tool_call'):
            try:
                tool_reply = ai_engine.resolve_tool_call(clean_text, context_manager.get_context())
                if tool_reply:
                    context_manager.register_command(raw_command, "ai_tool_call", success=True)
                    return "ai_reply::" + tool_reply
            except Exception:
                pass  # Fall through to the string-mapping fallback

        # 2. Fallback: map the input onto a known command string.
        if hasattr(ai_engine, 'fallback_parse_command'):
            try:
                ai_fallback = ai_engine.fallback_parse_command(clean_text, context_manager.get_context())
                if ai_fallback and _is_known_command(ai_fallback):
                    context_manager.register_command(raw_command, ai_fallback, success=True)
                    return ai_fallback
            except Exception:
                pass  # Fall through to normalized command

    # Nothing to run: it's conversation. tools/recall.py's "chat" tool answers it with the
    # model (or a canned reply when Ollama is down).
    context_manager.register_command(raw_command, normalized, success=False)
    return CHAT_PREFIX + raw_command.strip()
