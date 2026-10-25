"""Window management (roadmap 3.6): switch to, minimise, maximise, snap, minimise all, focus mode."""

import re

from core import permissions, timers
from tools.registry import CONFIRM, Param, ask_or_reply, tool
from utils import launcher, windows

DEFAULT_DISTRACTIONS = ["discord", "steam", "whatsapp", "telegram", "epicgameslauncher", "instagram"]


def _checked(fn):
    try:
        return fn()
    except windows.WindowError as exc:
        return f"{exc} 🪟"


def _target(name):
    return re.sub(r"^(?:the |my )", "", (name or "").strip().rstrip("?.! ")).replace(" window", "").strip()


def _with_window(name, action):
    name = _target(name)
    if not name:
        return "Which window? 🪟"
    win = windows.find(name)
    if win is None:
        return f"{name} isn't open. Say \"open {name}\" to start it 🪟"
    return action(win)


_SWITCH = re.compile(r"^(?:switch to|go to|focus on|focus|bring up|jump to|show me) (.+)$")
_NOT_WINDOWS = re.compile(r"\b(?:list|lists|reminders?|clipboard|mode|sleep|desktop|settings|google|chatgpt)\b|"
                          r"^(?:what|my |it$)")


def _parse_switch(text):
    match = _SWITCH.match(text.strip().rstrip("?.! "))
    if not match or _NOT_WINDOWS.search(match.group(1)):
        return None
    return "switch to " + _target(match.group(1))


@tool("switch_window", "Bring an open app's window to the front.",
      {"name": Param("App or window name, e.g. 'chrome' or 'vs code'")},
      command="switch to ", parse=_parse_switch, ai=True, priority=7)
def switch_window(ctx):
    return _checked(lambda: _with_window(ctx.arg, lambda w: ctx.run(w.app, lambda: windows.focus(w))
                                         or f"Switched to {w.app} 🪟"))


_MIN_ALL = {"minimise all", "minimize all", "minimise everything", "minimize everything", "show desktop",
            "show the desktop", "hide everything", "hide all windows", "minimise all windows",
            "minimize all windows", "clear the screen"}
_MINMAX = re.compile(r"^(minimi[sz]e|maximi[sz]e|hide) (.+)$")


def _parse_minmax(text):
    text = text.strip().rstrip("?.! ")
    if text in _MIN_ALL:
        return "minimise all"
    match = _MINMAX.match(text)
    if not match:
        return None
    verb = "maximise" if match.group(1).startswith("maxim") else "minimise"
    return f"{verb} {_target(match.group(2))}"


@tool("minimise_all", "Minimise every window (show the desktop).", command="minimise all",
      parse=_parse_minmax, ai=True, priority=7)
def minimise_all(ctx):
    return _checked(lambda: ctx.run("all", windows.minimise_all) or "Everything's minimised 🪟")


@tool("minimise_window", "Minimise one app's window.", {"name": Param("App or window name")},
      command="minimise ", ai=True, priority=7)
def minimise_window(ctx):
    return _checked(lambda: _with_window(ctx.arg, lambda w: ctx.run(w.app, lambda: windows.minimise(w))
                                         or f"Minimised {w.app} 🪟"))


@tool("maximise_window", "Maximise one app's window.", {"name": Param("App or window name")},
      command="maximise ", ai=True, priority=7)
def maximise_window(ctx):
    return _checked(lambda: _with_window(ctx.arg, lambda w: ctx.run(w.app, lambda: windows.maximise(w))
                                         or f"Maximised {w.app} 🪟"))


_SNAP = re.compile(r"^(?:snap|move|put|dock) (.+?) (?:to |on )?(?:the )?(left|right)(?: side| half)?$")


def _parse_snap(text):
    match = _SNAP.match(text.strip().rstrip("?.! "))
    return f"snap {match.group(2)} {_target(match.group(1))}" if match else None


@tool("snap_window", "Snap an app's window to the left or right half of the screen.",
      {"spec": Param("'left <app>' or 'right <app>', e.g. 'left chrome'")},
      command="snap ", parse=_parse_snap, ai=True, priority=7)
def snap_window(ctx):
    side, _, name = ctx.arg.strip().partition(" ")
    if side not in ("left", "right"):
        return "Left or right? Say \"snap chrome left\" 🪟"
    return _checked(lambda: _with_window(name, lambda w: ctx.run(f"{w.app} {side}", lambda: windows.snap(w, side))
                                         or f"{w.app} is on the {side} 🪟"))


_LIST = {"what windows are open", "list windows", "which windows are open", "show windows",
         "what apps are open", "which apps are open", "what's open", "whats open", "what is open"}


@tool("list_windows", "Tell the user which app windows are open.", command="list windows",
      parse=lambda t: "list windows" if t.strip().rstrip("?.! ") in _LIST else None, ai=True, priority=7)
def list_windows():
    def report():
        apps = []
        for win in windows.list_windows():
            if win.app not in apps:
                apps.append(win.app)
        return ("Open: " + ", ".join(apps) + " 🪟") if apps else "No app windows are open 🪟"
    return _checked(report)


# =========================
# FOCUS MODE
# =========================

_FOCUS = re.compile(r"^(?:start |enter |turn on |begin )?focus mode(?: for (\d+) ?(?:minutes?|mins?))?$|"
                    r"^(?:i need to|help me|let me) (?:focus|concentrate)$")


def _parse_focus(text):
    match = _FOCUS.match(text.strip().rstrip("?.! "))
    if not match:
        return None
    return "focus mode " + (match.group(1) or "") if match.group(1) else "focus mode"


def distractions():
    try:
        from ui_qt import settings as settings_mod
        apps = settings_mod.load().get("distractions") or DEFAULT_DISTRACTIONS
    except Exception:
        apps = DEFAULT_DISTRACTIONS
    return [a for a in apps if isinstance(a, str) and a.strip()]


@tool("focus_mode", "Close distracting apps (Discord, Steam, ...) and optionally start a focus timer.",
      {"minutes": Param("Optional focus timer length in minutes", type="integer", required=False)},
      command="focus mode", parse=_parse_focus, tier=CONFIRM, ai=True, priority=7)
def focus_mode(ctx):
    minutes = int(ctx.arg) if (ctx.arg or "").strip().isdigit() else 0
    running = windows.running_processes()
    open_now = [app for app in distractions() if (launcher.process_name_for(app) or "").lower() in running]

    def start_timer():
        if minutes:
            timers.start(minutes * 60)
            return f" Focus timer set for {minutes} minutes ⏳"
        return ""

    if not open_now:
        return "Nothing distracting is open. Focus away ✨" + start_timer()

    def close_all():
        closed = [app for app in open_now if launcher.kill_process(app)[0]]
        return (f"Closed {', '.join(closed)}. Focus mode on ✨" if closed else
                "I couldn't close those apps 🌸") + start_timer()

    return ask_or_reply(permissions.run_action("focus_mode", " and ".join(open_now), close_all))
