"""
Permission tiers for actions.

  safe     runs straight away
  confirm  asks "Should I?" and waits for a yes/no (typed, spoken or button)
  blocked  never runs

Every action is logged (see utils/action_log.py). TIERS is a plain
name -> tier table, filled by the tool registry (tools/).
Unlisted actions default to "confirm" (fail safe).
"""

import re
import threading
import time

from utils.action_log import log_action

SAFE, CONFIRM, BLOCKED = "safe", "confirm", "blocked"

# Tools add themselves here when they register (tools/registry.py), so a tool's
# tier is declared once, in its @tool(...). These are actions with no tool yet.
TIERS = {
    "delete_file": CONFIRM,
    "shutdown": CONFIRM,
    "restart_computer": CONFIRM,
    "forget_facts": CONFIRM,     # forgetting several remembered facts at once (tools/recall.py)
    "run_shell": BLOCKED,
}

CONFIRM_TIMEOUT_SECONDS = 30

_YES = {"yes", "y", "yeah", "yep", "yup", "sure", "ok", "okay", "confirm",
        "do it", "go ahead", "please do", "yes please"}
_NO = {"no", "n", "nope", "nah", "cancel", "stop", "dont", "never mind", "nevermind"}

_lock = threading.Lock()
_pending = None  # {"action", "target", "run", "expires"}


def tier_of(action):
    if action not in TIERS:
        from tools import registry  # registering the tools fills TIERS
        registry.ensure_loaded()
    return TIERS.get(action, CONFIRM)


def _failed(reply):
    return isinstance(reply, str) and "ouldn't" in reply


def _execute(action, target, run):
    try:
        reply = run()
    except Exception:
        log_action(action, target, "error")
        raise
    log_action(action, target, "failed" if _failed(reply) else "ok")
    return reply


def _question(action, target):
    verb = {"close_app": "close", "restart_app": "restart", "forget_facts": "forget"}.get(action, action.replace("_", " "))
    return f"Should I {verb} {target}? (yes/no) 🌸".replace("  ", " ")


def run_action(action, target, run):
    """Run `run()` according to the action's tier. Returns the reply text."""
    global _pending
    tier = tier_of(action)

    if tier == BLOCKED:
        log_action(action, target, "blocked")
        return "I'm not allowed to do that one 🌸"

    if tier == CONFIRM:
        with _lock:
            if _pending:
                log_action(_pending["action"], _pending["target"], "superseded")
            _pending = {
                "action": action, "target": target, "run": run,
                "expires": time.time() + CONFIRM_TIMEOUT_SECONDS,
            }
        log_action(action, target, "asked")
        return _question(action, target)

    return _execute(action, target, run)


def has_pending():
    with _lock:
        return _pending is not None and time.time() < _pending["expires"]


def pending_prompt():
    with _lock:
        return _question(_pending["action"], _pending["target"]) if _pending else ""


def parse_answer(text):
    """'yes'/'no' (punctuation and case ignored), or None if it's something else."""
    cleaned = re.sub(r"[^a-z ]", "", (text or "").lower().replace("'", "")).strip()
    if cleaned in _YES:
        return True
    if cleaned in _NO:
        return False
    return None


def resolve(answer):
    """Apply a yes/no to the pending action. Returns the reply text."""
    global _pending
    with _lock:
        pending, _pending = _pending, None
    if pending is None:
        return "There's nothing waiting for a yes or no 🌸"
    action, target = pending["action"], pending["target"]
    if time.time() >= pending["expires"]:
        log_action(action, target, "expired")
        return "That request timed out, so I didn't do it. Ask again if you still want it 🌸"
    if not answer:
        log_action(action, target, "declined")
        return "Okay, I won't 🌸"
    return _execute(action, target, pending["run"])


def cancel_pending(reason="cancelled"):
    """Drop any pending action (e.g. the user moved on to another command)."""
    global _pending
    with _lock:
        pending, _pending = _pending, None
    if pending:
        log_action(pending["action"], pending["target"], reason)
