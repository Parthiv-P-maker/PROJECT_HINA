"""
Kitchen-style timers. Each timer has an id and its own cancel event, so
several can run at once and each can be cancelled on its own.

When one finishes it calls the notifier. The default notifier logs and speaks;
a window replaces it with set_notifier() so the message also shows on screen.
"""

import itertools
import threading

from utils.logger import get_logger

logger = get_logger(__name__)

_lock = threading.Lock()
_ids = itertools.count(1)
_active = {}  # timer id -> (cancel Event, seconds)


def _default_notifier(message):
    logger.info("Timer: %s", message)
    try:
        import voice
        voice.speak(message, blocking=False)
    except Exception:
        logger.exception("Couldn't speak the timer alert")


_notifier = _default_notifier


def set_notifier(fn):
    """Call `fn(message)` from the timer's thread when a timer finishes (None restores the default)."""
    global _notifier
    _notifier = fn or _default_notifier


def notify(message):
    """Tell the user something unprompted (a timer or reminder going off), through the notifier."""
    try:
        _notifier(message)
    except Exception:
        logger.exception("Notifier failed")


def _describe(seconds):
    if seconds % 60 == 0 and seconds >= 60:
        minutes = seconds // 60
        return f"{minutes} minute" + ("" if minutes == 1 else "s")
    return f"{seconds} second" + ("" if seconds == 1 else "s")


def _run(timer_id, seconds, cancelled):
    fired = not cancelled.wait(seconds)
    with _lock:
        _active.pop(timer_id, None)
    if fired:
        notify(f"Your {_describe(seconds)} timer is up ⏰🌸")


def start(seconds):
    """Start a timer; returns its id."""
    cancelled = threading.Event()
    with _lock:
        timer_id = next(_ids)
        _active[timer_id] = (cancelled, seconds)
    threading.Thread(target=_run, args=(timer_id, seconds, cancelled),
                     name=f"hina-timer-{timer_id}", daemon=True).start()
    return timer_id


def cancel(timer_id=None):
    """Cancel one timer, or every running timer when no id is given. Returns how many were cancelled."""
    with _lock:
        ids = list(_active) if timer_id is None else [timer_id] if timer_id in _active else []
        events = [_active.pop(i)[0] for i in ids]
    for event in events:
        event.set()
    return len(events)


def running():
    """[(id, seconds)] of timers that haven't finished."""
    with _lock:
        return [(i, secs) for i, (_, secs) in _active.items()]
