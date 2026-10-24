"""
Render the HUD in each state to PNGs without a real display.

    python -m ui_qt.screenshots [out_dir]      (default: docs/screenshots)

Uses Qt's offscreen platform, a throwaway data dir, no hotkeys, no speech.
"""

import os
import sys
import tempfile
import types


def main(out_dir=None):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = os.path.abspath(out_dir or os.path.join(root, "docs", "screenshots"))
    os.makedirs(out_dir, exist_ok=True)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if sys.platform == "win32":
        os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
    os.environ["HINA_DATA_DIR"] = tempfile.mkdtemp(prefix="hina_shots_")
    sys.modules["keyboard"] = types.SimpleNamespace(add_hotkey=lambda *a, **k: None)
    if root not in sys.path:
        sys.path.insert(0, root)

    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    import voice
    voice.speak = lambda *a, **k: None
    from ui_qt.window import HinaWindow

    w = HinaWindow(tray=False, hotkeys=False)
    w._state_timer.stop()
    w.show()
    c = w.console
    c.add_system("Core reactor online.", "ok")
    c.add_system("Command router linked.")
    c.add_system("Audio subsystem standing by.")
    c.add_reply("Good evening. All systems are online.", typewriter=False)
    c.add_user("what's the time")
    c.add_reply("The time is 10:42 PM.", typewriter=False)
    c.add_user("calculate 25*12")
    c.add_reply("25*12 = 300", typewriter=False)
    c.add_user("open chrome")
    c.add_reply("Opening chrome now.", typewriter=False)
    w.status.ai.set("ONLINE", "ok")
    import math
    for i in range(60):  # some telemetry history so the graph isn't empty
        w.telemetry.push(18 + 14 * math.sin(i / 5) + (i % 7) * 2, 62 + 4 * math.sin(i / 11))

    def settle(state, seconds=1.2, level=0.0):
        w.set_state(state)
        for _ in range(int(seconds * 60)):
            w.core.set_level(level)
            w.core.advance(1 / 60)
        app.processEvents()

    def shot(name):
        app.processEvents()
        path = os.path.join(out_dir, name + ".png")
        w.grab().save(path)
        print("saved", path)

    settle("idle")
    shot("hud_idle")
    w.voice_status = "RECEIVING AUDIO"
    settle("listening", level=0.55)
    shot("hud_listening")
    w.voice_status = ""
    c.add_user("find file roadmap")
    settle("thinking")
    shot("hud_thinking")
    c.add_reply("Found HINA_ROADMAP.md in Documents.", typewriter=False)
    settle("speaking", seconds=1.0)
    shot("hud_speaking")

    c.add_user("close notepad")
    c.add_reply("Should I close notepad? Say yes or no.", typewriter=False)
    c.add_system("Awaiting confirmation.", "warn")
    w.show_confirm(True)
    settle("idle")
    shot("hud_confirm")
    w.show_confirm(False)

    w.settings_panel.slide_in(w.settings, animate=False)
    settle("idle", seconds=0.2)
    shot("hud_settings")
    w.settings_panel.slide_out(animate=False)

    w.set_compact(True, save=False)
    settle("speaking", seconds=0.8)
    shot("hud_compact")
    w.quit_app()
    return out_dir


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
