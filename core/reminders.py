"""
Reminders that survive restarts (roadmap 3.4).

They live in the memory database (core/memory_store.py). A background thread
checks every few seconds and announces anything due through timers.notify(),
so they show in the window and are spoken like a finished timer. Reminders that
fell due while Hina was closed are announced when she starts, marked as missed.
"""

import threading
import time
from datetime import datetime, timedelta

from core import memory_store, timers
from utils.logger import get_logger
from utils.when import describe

logger = get_logger(__name__)

CHECK_SECONDS = 5
LATE_AFTER = timedelta(minutes=2)  # later than this = it was missed while Hina was closed

_started = threading.Event()


def add(due, text):
    return memory_store.add_reminder(due, text)


def pending():
    """[(id, due datetime, text)], soonest first."""
    out = []
    for row in memory_store.pending_reminders():
        try:
            out.append((row["id"], datetime.fromisoformat(row["due"]), row["text"]))
        except ValueError:
            logger.warning("Skipping reminder %s with a bad time %r", row["id"], row["due"])
    return out


def cancel(ids):
    return memory_store.delete_reminders(ids)


def check(now=None):
    """Announce every reminder that is due. Returns the messages sent."""
    now = now or datetime.now()
    sent = []
    for reminder_id, due, text in pending():
        if due > now:
            break
        memory_store.mark_reminder_fired(reminder_id)  # first, so a failing notifier can't repeat it
        if now - due > LATE_AFTER:
            message = f"Missed reminder ({describe_past(due, now)}): {text} 🔔"
        else:
            message = f"Reminder: {text} 🔔"
        timers.notify(message)
        sent.append(message)
    return sent


def describe_past(due, now):
    clock = due.strftime("%I:%M %p").lstrip("0")
    return f"due at {clock}" if due.date() == now.date() else f"due {due.strftime('%d %B')} at {clock}"


def _loop():
    while True:
        try:
            check()
        except Exception:
            logger.exception("Reminder check failed")
        time.sleep(CHECK_SECONDS)


def start():
    """Start the background checker once (the windows call this at startup)."""
    if _started.is_set():
        return
    _started.set()
    threading.Thread(target=_loop, name="hina-reminders", daemon=True).start()


def when_text(due):
    return describe(due)
