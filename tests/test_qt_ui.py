"""
Smoke tests for the PySide6 HUD (ui_qt/), run headless with Qt's offscreen
platform. Skipped if PySide6 or pytest-qt isn't installed.

Nothing here touches the real machine: conftest stubs speech, processes,
browser and keyboard hooks, and points the data dir (settings.json) at tmp.
"""

import json
import os
import sys
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt  # noqa: E402

from core.dispatcher import DispatchResult  # noqa: E402
from ui_qt import settings as settings_mod  # noqa: E402


@pytest.fixture
def no_ai(monkeypatch):
    import core.ai_engine as ai_engine
    monkeypatch.setattr(ai_engine, "ollama_available", lambda: False)


@pytest.fixture
def window(qtbot, no_ai):
    from ui_qt.window import HinaWindow
    w = HinaWindow(settings_mod.load(), tray=False, hotkeys=False)
    qtbot.addWidget(w)
    w.show()
    yield w
    qtbot.waitUntil(lambda: not w.bridge.busy and not w.bridge.listening, timeout=5000)
    w.quit_app()


def submit(qtbot, window, text):
    window.entry.setText(text)
    qtbot.keyClick(window.entry, Qt.Key_Return)


def wait_idle(qtbot, window, timeout=5000):
    qtbot.waitUntil(lambda: not window.bridge.busy, timeout=timeout)
    window.console.finish()


# ---- construction ----------------------------------------------------------

def test_window_builds(window):
    assert window.windowTitle() == "Project Hina"
    assert window.windowFlags() & Qt.FramelessWindowHint
    assert window.windowFlags() & Qt.WindowStaysOnTopHint
    assert window.testAttribute(Qt.WA_TranslucentBackground)
    assert window.entry.isVisible() and window.send_btn.isVisible() and window.mic_btn.isVisible()
    assert not window.yes_btn.isVisible() and not window.no_btn.isVisible()
    assert window.state == "idle" and window.core.state == "idle"
    assert window.left_col.isVisible()  # expanded by default


def test_hotkeys_registered(qtbot, no_ai, monkeypatch):
    from ui_qt.window import HinaWindow
    registered = []
    monkeypatch.setattr(sys.modules["keyboard"], "add_hotkey",
                        lambda combo, fn, *a, **k: registered.append(combo) or combo, raising=False)
    w = HinaWindow(settings_mod.load(), tray=False, hotkeys=True)
    qtbot.addWidget(w)
    assert registered == ["ctrl+h", "ctrl+m"]
    w.quit_app()


def test_hotkey_signal_toggles_visibility(window, qtbot):
    window.hotkey_toggle.emit()
    assert not window.isVisible()
    window.hotkey_toggle.emit()
    assert window.isVisible()


def test_boot_sequence_and_greeting(window, qtbot, machine):
    from ui_qt.app import boot
    message = boot(window, name="Parth")
    qtbot.waitUntil(lambda: "Parth" in window.console.plain_text(), timeout=3000)
    assert "Core reactor online" in window.console.plain_text()
    qtbot.waitUntil(lambda: message in machine.spoken, timeout=3000)


@pytest.mark.parametrize("hour,part", [(2, "evening"), (8, "morning"), (14, "afternoon"), (21, "evening")])
def test_greeting_time_of_day(hour, part):
    from datetime import datetime
    from ui_qt.window import greeting
    text = greeting("Parth", now=datetime(2026, 1, 1, hour))
    assert f"Good {part}, Parth" in text


# ---- commands ----------------------------------------------------------------

def test_command_gets_a_reply_and_is_spoken(window, qtbot, machine):
    submit(qtbot, window, "tell time")
    assert window.entry.text() == ""
    wait_idle(qtbot, window)
    text = window.console.plain_text()
    assert "YOU   tell time" in text
    assert "time is" in text.lower()
    assert any("time is" in s.lower() for s in machine.spoken)


def test_send_button_and_calculator(window, qtbot):
    window.entry.setText("calculate 25*12")
    qtbot.mouseClick(window.send_btn, Qt.LeftButton)
    wait_idle(qtbot, window)
    assert "300" in window.console.last_line()


def test_empty_input_is_ignored(window, qtbot):
    before = window.console.plain_text()
    submit(qtbot, window, "   ")
    assert window.console.plain_text() == before and not window.bridge.busy


def test_slow_command_shows_thinking_without_freezing(window, qtbot, monkeypatch):
    import ui_qt.bridge as bridge

    def slow(command, **kwargs):
        time.sleep(0.5)
        return DispatchResult(reply="slow reply done")

    monkeypatch.setattr(bridge, "dispatch_command", slow)
    submit(qtbot, window, "tell time")
    assert window.bridge.busy and window.state == "thinking" and window.core.state == "thinking"
    submit(qtbot, window, "tell date")  # ignored while busy
    assert "tell date" not in window.console.plain_text()
    ticks = 0
    start = time.time()
    while window.bridge.busy and time.time() - start < 3:
        t0 = time.time()
        qtbot.wait(20)
        assert time.time() - t0 < 0.3, "GUI thread was blocked"
        ticks += 1
    assert ticks > 5
    window.console.finish()
    assert "slow reply done" in window.console.last_line()


def test_crashing_command_shows_a_message(window, qtbot, monkeypatch):
    import ui_qt.bridge as bridge

    def boom(command, **kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(bridge, "dispatch_command", boom)
    submit(qtbot, window, "tell time")
    wait_idle(qtbot, window)
    assert "went wrong" in window.console.last_line()
    assert window.bridge.busy is False


def test_typewriter_reveal_counts_as_speaking(window, qtbot):
    window.console.add_reply("A fairly long reply so the typewriter takes a few frames to finish.")
    assert window.console.is_revealing()
    window.refresh_state()
    assert window.state == "speaking"
    qtbot.waitUntil(lambda: not window.console.is_revealing(), timeout=3000)
    assert window.console.last_line().endswith("few frames to finish.")
    window.refresh_state()
    assert window.state == "idle"


def test_cute_emoji_are_stripped_from_the_hud(window):
    window.console.add_reply("Hello! \U0001F338 \u2728", typewriter=False)
    assert window.console.last_line().endswith("Hello!")


def test_exit_command_schedules_quit(window, qtbot, monkeypatch):
    quit_calls = []
    monkeypatch.setattr(window, "quit_app", lambda: quit_calls.append(True))
    submit(qtbot, window, "bye")
    wait_idle(qtbot, window)
    qtbot.waitUntil(lambda: bool(quit_calls), timeout=4000)


def test_countdown_ticks_reach_the_console(window, qtbot):
    submit(qtbot, window, "countdown 1")
    wait_idle(qtbot, window)
    qtbot.waitUntil(lambda: "Done!" in window.console.plain_text(), timeout=4000)
    assert "1..." in window.console.plain_text()


# ---- confirmation ------------------------------------------------------------

def test_confirm_buttons_yes_runs_the_action(window, qtbot, machine):
    submit(qtbot, window, "close spotify")
    wait_idle(qtbot, window)
    assert "Should I close spotify" in window.console.plain_text()
    assert window.yes_btn.isVisible() and window.no_btn.isVisible()
    assert machine.os_calls["run"] == []

    qtbot.mouseClick(window.yes_btn, Qt.LeftButton)
    wait_idle(qtbot, window)
    assert machine.os_calls["run"] == [["taskkill", "/IM", "Spotify.exe", "/F"]]
    assert not window.yes_btn.isVisible()


def test_confirm_buttons_no_cancels(window, qtbot, machine):
    from core import permissions
    submit(qtbot, window, "close spotify")
    wait_idle(qtbot, window)
    qtbot.mouseClick(window.no_btn, Qt.LeftButton)
    wait_idle(qtbot, window)
    assert machine.os_calls["run"] == []
    assert not permissions.has_pending()
    assert not window.no_btn.isVisible()


# ---- voice -------------------------------------------------------------------

class _FakeSpeech:
    def __init__(self, text="tell time", error=None):
        import threading
        self.cancel = threading.Event()
        self.text, self.error = text, error

    def listen(self):
        time.sleep(0.1)
        if self.error:
            from core.stt import SttError
            raise SttError(self.error)
        return self.text


def test_mic_runs_heard_text_as_a_command(window, qtbot):
    window.bridge._speech = _FakeSpeech("tell time")
    qtbot.mouseClick(window.mic_btn, Qt.LeftButton)
    assert window.bridge.listening and window.state == "listening"
    assert window.mic_btn.isChecked()
    qtbot.waitUntil(lambda: not window.bridge.listening, timeout=3000)
    wait_idle(qtbot, window)
    assert "YOU   tell time" in window.console.plain_text()
    assert "time is" in window.console.plain_text().lower()
    assert not window.mic_btn.isChecked()


@pytest.mark.parametrize("button", ["yes", "no"])
def test_spoken_bye_asks_before_shutting_down(window, qtbot, monkeypatch, button):
    """Whisper can mishear unclear audio as 'bye'; voice must never quit straight away."""
    quit_calls = []
    monkeypatch.setattr(window, "quit_app", lambda: quit_calls.append(True))
    window.bridge._speech = _FakeSpeech("Bye.")
    window.toggle_listening()
    qtbot.waitUntil(lambda: not window.bridge.listening, timeout=3000)
    window.console.finish()
    assert "Shut down Hina?" in window.console.plain_text()
    assert window.yes_btn.isVisible() and not window.bridge.busy
    qtbot.wait(300)
    assert not quit_calls

    qtbot.mouseClick(window.yes_btn if button == "yes" else window.no_btn, Qt.LeftButton)
    wait_idle(qtbot, window)
    assert not window.yes_btn.isVisible()
    if button == "yes":
        qtbot.waitUntil(lambda: bool(quit_calls), timeout=4000)
    else:
        assert "Staying online" in window.console.plain_text()
        qtbot.wait(300)
        assert not quit_calls


def test_other_command_after_spoken_bye_drops_the_question(window, qtbot):
    window.bridge._speech = _FakeSpeech("bye")
    window.toggle_listening()
    qtbot.waitUntil(lambda: not window.bridge.listening, timeout=3000)
    submit(qtbot, window, "tell time")
    wait_idle(qtbot, window)
    assert "time is" in window.console.last_line().lower()
    assert not window._pending_exit and not window.yes_btn.isVisible()


def test_typed_bye_still_quits_directly(window, qtbot, monkeypatch):
    quit_calls = []
    monkeypatch.setattr(window, "quit_app", lambda: quit_calls.append(True))
    submit(qtbot, window, "bye")
    wait_idle(qtbot, window)
    qtbot.waitUntil(lambda: bool(quit_calls), timeout=4000)


def test_mic_error_is_reported(window, qtbot):
    window.bridge._speech = _FakeSpeech(error="No microphone found")
    window.toggle_listening()
    qtbot.waitUntil(lambda: not window.bridge.listening, timeout=3000)
    assert "No microphone found" in window.console.plain_text()


# ---- core widget ---------------------------------------------------------------

def test_core_states(qtbot):
    from ui_qt.core_orb import ArcReactor, STATES
    core = ArcReactor()
    qtbot.addWidget(core)
    core.resize(240, 240)
    angles = []
    for state in STATES:
        core.set_state(state)
        before = core.angle
        for _ in range(30):
            core.advance(1 / 60)
        angles.append(core.angle - before)
        assert core.state == state
        assert not core.grab().isNull()  # paints without raising
    idle, listening, thinking, speaking = angles
    assert thinking > idle * 4  # thinking spins much faster
    with pytest.raises(ValueError):
        core.set_state("dancing")


def test_core_level_follows_mic_only_while_listening(qtbot):
    from ui_qt.core_orb import ArcReactor
    core = ArcReactor()
    qtbot.addWidget(core)
    core.set_state("listening")
    core.set_level(0.8)
    for _ in range(30):
        core.advance(1 / 60)
    assert core.level > 0.6
    core.set_state("idle")
    for _ in range(30):
        core.advance(1 / 60)
    assert core.level < 0.05


def test_speaking_spawns_ripples(qtbot):
    from ui_qt.core_orb import ArcReactor
    core = ArcReactor()
    qtbot.addWidget(core)
    core.set_state("speaking")
    for _ in range(90):
        core.advance(1 / 60)
    assert core.ripples


# ---- settings ------------------------------------------------------------------

def test_settings_defaults_when_missing_or_corrupt():
    s = settings_mod.load()
    assert s == settings_mod.DEFAULTS
    with open(settings_mod.settings_path(), "w") as f:
        f.write("{not json")
    assert settings_mod.load() == settings_mod.DEFAULTS


def test_settings_roundtrip_and_validation():
    s = settings_mod.load()
    s.update(ai_model="llama3.2:3b", opacity=5, ambient_minutes=-3,
             search_folders=["C:\\Work", "  "], bogus="x", always_on_top="yes")
    saved = settings_mod.save(s)
    assert saved["opacity"] == 1.0 and saved["ambient_minutes"] == 0
    assert saved["always_on_top"] is True  # wrong type -> default
    assert "bogus" not in saved
    loaded = settings_mod.load()
    assert loaded["ai_model"] == "llama3.2:3b" and loaded["search_folders"] == ["C:\\Work"]
    with open(settings_mod.settings_path()) as f:
        assert json.load(f)["ai_model"] == "llama3.2:3b"
    from utils.file_search import _extra_roots
    assert [str(p) for p in _extra_roots()] == ["C:\\Work"]


def test_first_run_imports_existing_search_folders():
    from utils.paths import user_data_dir
    with open(os.path.join(user_data_dir(), "search_folders.txt"), "w") as f:
        f.write("# old style\nD:\\Projects\n")
    assert settings_mod.load()["search_folders"] == ["D:\\Projects"]


def test_apply_runtime_wires_model_voice_and_local_only(monkeypatch):
    import core.ai_engine as ai_engine
    import voice
    monkeypatch.setattr(ai_engine, "MODEL", ai_engine.MODEL)
    monkeypatch.setattr(voice, "VOICE", voice.VOICE)
    monkeypatch.setattr(voice, "_HAS_EDGE_TTS", True)
    monkeypatch.delattr(voice, "_HINA_EDGE_AVAILABLE", raising=False)
    settings_mod.apply_runtime(dict(settings_mod.DEFAULTS, ai_model="phi3:mini",
                                    tts_voice="en-GB-RyanNeural", local_only=True))
    assert ai_engine.MODEL == "phi3:mini"
    assert voice.VOICE == "en-GB-RyanNeural"
    assert voice._HAS_EDGE_TTS is False
    settings_mod.apply_runtime(dict(settings_mod.DEFAULTS, local_only=False))
    assert voice._HAS_EDGE_TTS is True
    monkeypatch.delattr(voice, "_HINA_EDGE_AVAILABLE", raising=False)


def test_whisper_setting_maps_to_model_name():
    assert settings_mod.whisper_model_name({"whisper_model": "auto"}) is None
    assert settings_mod.whisper_model_name({"whisper_model": "small.en"}) == "small.en"


def test_settings_panel_save(window, qtbot, monkeypatch):
    import core.ai_engine as ai_engine
    monkeypatch.setattr(ai_engine, "MODEL", ai_engine.MODEL)
    qtbot.mouseClick(window.gear_btn, Qt.LeftButton)
    panel = window.settings_panel
    assert panel.open and panel.isVisible()
    panel.ai_model.setCurrentText("qwen2.5:7b")
    panel.ambient.setValue(12)
    panel.opacity.setValue(80)
    panel.swatches[2].click()
    qtbot.mouseClick(panel.save_btn, Qt.LeftButton)
    assert not panel.open
    assert window.settings["ai_model"] == "qwen2.5:7b"
    assert ai_engine.MODEL == "qwen2.5:7b"
    assert window.settings["accent"] == settings_mod.ACCENTS[2]
    assert window.core.accent.name() == settings_mod.ACCENTS[2]
    assert abs(window.windowOpacity() - 0.8) < 0.02 or window.windowOpacity() == 1.0  # offscreen may ignore
    on_disk = settings_mod.load()
    assert on_disk["ai_model"] == "qwen2.5:7b" and on_disk["ambient_minutes"] == 12
    assert "Configuration saved" in window.console.plain_text()


def test_settings_panel_cancel_reverts_preview(window, qtbot):
    window.toggle_settings()
    window.settings_panel.swatches[4].click()
    assert window.core.accent.name() == settings_mod.ACCENTS[4]  # live preview
    window.toggle_settings()  # gear again = cancel
    assert window.core.accent.name() == settings_mod.DEFAULTS["accent"]
    assert settings_mod.load()["accent"] == settings_mod.DEFAULTS["accent"]


def test_compact_mode_toggle_is_remembered(window, qtbot):
    big = window.size()
    qtbot.mouseClick(window.compact_btn, Qt.LeftButton)
    assert window.compact and window.width() < big.width()
    assert not window.left_col.isVisible()
    assert settings_mod.load()["compact"] is True
    window.set_compact(False)
    assert window.size() == big


def test_window_position_is_saved(window, qtbot):
    window.move(123, 77)
    window._save_position()
    assert settings_mod.load()["window_pos"] == [window.x(), window.y()]


def test_ambient_thought_after_idle(window):
    window.settings["ambient_minutes"] = 1
    window.last_activity = time.time() - 120
    before = window.console.plain_text()
    assert window._ambient_tick()
    assert window.console.plain_text() != before
    assert not window._ambient_tick()  # not again straight away
    window.settings["ambient_minutes"] = 0
    window.last_ambient = 0
    assert not window._ambient_tick()
