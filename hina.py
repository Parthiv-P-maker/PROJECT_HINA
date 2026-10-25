"""
Launch Hina.

    python hina.py            new Qt HUD (PySide6)
    python hina.py --classic  old customtkinter window (gui.py)
    python hina.py --doctor   check the setup (Ollama, models, mic, packages) and exit

Falls back to the classic window if PySide6 isn't installed. Logs go to the
console and to %APPDATA%\\ProjectHina\\logs\\hina.log.
"""

import sys


def main():
    if "--doctor" in sys.argv:
        from core import doctor
        return doctor.main()

    from utils.logger import enable_file_logging
    enable_file_logging()

    if "--classic" not in sys.argv:
        try:
            import PySide6  # noqa: F401
        except ImportError:
            print("PySide6 isn't installed (pip install PySide6); starting the classic window.")
        else:
            from ui_qt.app import main as qt_main
            return qt_main()
    import gui  # noqa: F401  (gui.py builds and runs its window on import)
    return 0


if __name__ == "__main__":
    sys.exit(main())
