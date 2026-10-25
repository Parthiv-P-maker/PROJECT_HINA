"""
Top-level windows on the desktop (pywin32): list, find by app or title, focus,
minimise/maximise, snap to half the screen, minimise everything.

Tools call these through the module so tests can fake them.
"""

from dataclasses import dataclass

from utils.launcher import process_name_for
from utils.logger import get_logger

logger = get_logger(__name__)


class WindowError(Exception):
    """str(exc) is safe to show to the user."""


@dataclass
class Win:
    hwnd: int
    title: str
    process: str  # image name, lowercase ("code.exe")

    @property
    def app(self):
        return self.process[:-4] if self.process.endswith(".exe") else self.process


# Windows that are part of the shell, not apps the user means.
_IGNORED_PROCESSES = {"textinputhost.exe", "applicationframehost.exe", "shellexperiencehost.exe",
                      "searchhost.exe", "startmenuexperiencehost.exe", "systemsettings.exe"}


def _win32():
    try:
        import win32con
        import win32gui
        import win32process
        return win32gui, win32con, win32process
    except Exception as exc:
        raise WindowError("I can't manage windows on this machine.") from exc


def list_windows():
    """Visible, titled app windows, front-most first."""
    win32gui, win32con, win32process = _win32()
    import psutil

    names = {}
    found = []

    def visit(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd) or win32gui.GetWindow(hwnd, win32con.GW_OWNER):
            return True
        title = win32gui.GetWindowText(hwnd).strip()
        if not title:
            return True
        if win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) & win32con.WS_EX_TOOLWINDOW:
            return True
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid not in names:
            try:
                names[pid] = psutil.Process(pid).name().lower()
            except Exception:
                names[pid] = ""
        if names[pid] and names[pid] not in _IGNORED_PROCESSES:
            found.append(Win(hwnd, title, names[pid]))
        return True

    win32gui.EnumWindows(visit, None)
    return found


def find(name, windows=None):
    """The best window for "chrome", "vs code", "notes.txt": process name first, then title."""
    wanted = (name or "").strip().lower()
    if not wanted:
        return None
    windows = list_windows() if windows is None else windows
    process = (process_name_for(wanted) or "").lower()
    for win in windows:
        if win.process == process or win.app == wanted.replace(" ", ""):
            return win
    for win in windows:
        if wanted in win.title.lower():
            return win
    for win in windows:
        if wanted.replace(" ", "") in win.process:
            return win
    return None


def focus(win):
    win32gui, win32con, _ = _win32()
    try:
        if win32gui.IsIconic(win.hwnd):
            win32gui.ShowWindow(win.hwnd, win32con.SW_RESTORE)
        # Windows only lets the foreground app hand focus over; a tap of Alt makes us count.
        import win32api
        win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
        win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
        win32gui.SetForegroundWindow(win.hwnd)
    except Exception as exc:
        logger.warning("Focusing %r failed: %s", win.title, exc)
        raise WindowError(f"Windows wouldn't let me switch to {win.app}.") from exc


def minimise(win):
    win32gui, win32con, _ = _win32()
    win32gui.ShowWindow(win.hwnd, win32con.SW_MINIMIZE)


def maximise(win):
    win32gui, win32con, _ = _win32()
    win32gui.ShowWindow(win.hwnd, win32con.SW_MAXIMIZE)
    focus(win)


def snap(win, side):
    """Fill the left or right half of the window's monitor (its work area, above the taskbar)."""
    win32gui, win32con, _ = _win32()
    import win32api
    monitor = win32api.MonitorFromWindow(win.hwnd, win32con.MONITOR_DEFAULTTONEAREST)
    left, top, right, bottom = win32api.GetMonitorInfo(monitor)["Work"]
    half = (right - left) // 2
    x = left if side == "left" else left + half
    win32gui.ShowWindow(win.hwnd, win32con.SW_RESTORE)
    win32gui.MoveWindow(win.hwnd, x, top, half, bottom - top, True)
    focus(win)


def minimise_all():
    try:
        import win32com.client
        win32com.client.Dispatch("Shell.Application").MinimizeAll()
    except Exception as exc:
        logger.warning("MinimizeAll failed: %s", exc)
        raise WindowError("I couldn't minimise everything.") from exc


def running_processes():
    """Lowercase image names of everything running."""
    import psutil
    out = set()
    for proc in psutil.process_iter(["name"]):
        if proc.info["name"]:
            out.add(proc.info["name"].lower())
    return out
