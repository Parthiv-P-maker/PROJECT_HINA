"""
Chat mode and conversation memory.

The router sends anything that isn't a tool here as "chat::<text>" (tools/chat.py).
`chat_reply` asks the local model for a real answer with the recent turns, a
rolling summary of older ones and the user's relevant facts; when Ollama is
down it falls back to the canned replies straight away.

The UIs call `record` after every command so the history (core/memory_store.py)
survives restarts; `maybe_summarise` folds old turns into the summary in the
background once enough have piled up.
"""

import random
import re
import threading
from datetime import datetime

from core import memory_store
from core.ai_loader import get_ai_engine
from core.context_manager import context_manager
from utils.logger import get_logger

logger = get_logger(__name__)

CHAT_PREFIX = "chat::"
KEEP_TURNS = 10        # newest turns sent to the model word for word
SUMMARY_BATCH = 10     # summarise once this many older turns are waiting
MAX_PROMPT_TURNS = KEEP_TURNS + SUMMARY_BATCH

UNKNOWN_REPLIES = [
    "Hmm, I don't know that one yet 🌸",
    "Hina is still learning! 🎀",
    "That's a new one for me ✨",
]

_summary_lock = threading.Lock()


_QUESTION_START = re.compile(
    r"^(what|whats|what's|when|where|who|whos|who's|which|why|how|do|does|did|am|is|are|was|were|have|has)\b")
_FIRST_PERSON = re.compile(r"\b(i|i'm|im|my|me|mine|myself)\b")
_RECALL_WORDS = re.compile(r"\b(said|say|told|tell you|mentioned|remember|talk(?:ed)? about|name|birthday)\b")


def is_personal_question(text):
    """A question about the user or the conversation ("when is my birthday?"), not a request."""
    text = (text or "").lower().strip()
    if not (text.endswith("?") or _QUESTION_START.match(text)) or not _FIRST_PERSON.search(text):
        return False
    if _RECALL_WORDS.search(text):
        return True
    wanted = memory_store.keywords(text)
    return bool(wanted) and any(wanted & memory_store.keywords(f["text"]) for f in memory_store.list_facts())


def kind_of(command):
    return memory_store.CHAT if (command or "").startswith(CHAT_PREFIX) else memory_store.COMMAND


def chat_context():
    context = context_manager.get_context()
    try:
        import memory
        context["name"] = memory.get_name() or ""
    except Exception:
        context["name"] = ""
    context["now"] = datetime.now().strftime("%A %d %B, %H:%M")
    return context


def prompt_history():
    """Turns the summary doesn't cover yet (at most MAX_PROMPT_TURNS), oldest first."""
    summary, upto = memory_store.get_summary()
    return summary, memory_store.recent_turns(limit=MAX_PROMPT_TURNS, after_id=upto)


def chat_reply(text):
    """Hina's conversational answer to `text` (never empty)."""
    engine = get_ai_engine()
    if engine is not None and hasattr(engine, "chat_reply"):
        try:
            summary, history = prompt_history()
            facts = [f["text"] for f in memory_store.relevant_facts(text)]
            reply = engine.chat_reply(text, chat_context(), history, summary, facts)
            if reply:
                return reply
        except Exception as exc:
            logger.warning("Chat failed, using a canned reply: %s", exc)
    return random.choice(UNKNOWN_REPLIES)


def record(raw_command, command, reply):
    """Store one exchange (skipped in private mode), then maybe summarise in the background."""
    try:
        if memory_store.record_turn(raw_command, reply, kind_of(command)) is not None:
            maybe_summarise(background=True)
    except Exception as exc:  # history must never break a command
        logger.warning("Couldn't record the conversation: %s", exc)


def maybe_summarise(background=False):
    """Fold turns older than KEEP_TURNS into the rolling summary, if enough are waiting.

    Without Ollama nothing changes; those turns are retried next time.
    Returns True if the summary was updated (always False when backgrounded).
    """
    if len(memory_store.unsummarised_turns(KEEP_TURNS)) < SUMMARY_BATCH:
        return False
    if background:
        threading.Thread(target=maybe_summarise, daemon=True).start()
        return False
    if not _summary_lock.acquire(blocking=False):
        return False  # another thread is already on it
    try:
        pending = memory_store.unsummarised_turns(KEEP_TURNS)
        if len(pending) < SUMMARY_BATCH or memory_store.is_private():
            return False
        engine = get_ai_engine()
        if engine is None or not hasattr(engine, "summarize_turns"):
            return False
        previous, _ = memory_store.get_summary()
        summary = engine.summarize_turns(previous, pending)
        if not summary:
            return False
        memory_store.set_summary(summary, pending[-1]["id"])
        return True
    except Exception as exc:
        logger.warning("Couldn't summarise history: %s", exc)
        return False
    finally:
        _summary_lock.release()
