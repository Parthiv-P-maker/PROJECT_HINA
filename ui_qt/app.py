"""Start the Qt HUD: settings, window, boot sequence, greeting."""

import sys
import threading

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from ui_qt import settings as settings_mod
from ui_qt import theme
from utils.logger import get_logger

logger = get_logger(__name__)

BOOT_LINES = [
    ("Core reactor online.", "ok"),
    ("Command router linked.", "info"),
    ("Audio subsystem standing by.", "info"),
]


def boot(window, name=None, speak=True):
    """Boot sequence in the console, then the greeting (typed and spoken)."""
    from ui_qt.window import greeting
    for i, (line, level) in enumerate(BOOT_LINES):
        QTimer.singleShot(120 * i, lambda l=line, lv=level: window.console.add_system(l, lv))
    message = greeting(name)

    def greet():
        window.console.add_reply(message)
        if speak:
            threading.Thread(target=window.speak, args=(message,), daemon=True).start()
    QTimer.singleShot(120 * len(BOOT_LINES) + 80, greet)
    return message


def main(argv=None):
    argv = sys.argv if argv is None else argv
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName("Project Hina")
    app.setQuitOnLastWindowClosed(False)  # hiding to the tray must not quit
    theme.load_fonts()

    from ui_qt.window import HinaWindow
    settings = settings_mod.load()
    window = HinaWindow(settings)
    app._hina_owner = window

    try:
        from memory import get_name
        name = get_name()
    except Exception:
        name = None

    if settings.get("show_on_start", True) or "--show" in argv:
        window.show_window()
    boot(window, name)
    logger.info("Qt HUD started")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
