"""
Headless smoke test for gui.py.

gui.py is a script: importing it builds the whole window. We import it with
mainloop() disabled, drive it by hand (type text, pump the event loop) and check
the window behaves. If Tk or customtkinter isn't usable the tests are skipped.

Linux/CI:   xvfb-run python -m pytest tests/test_gui_smoke.py
Windows:    just run it (a window flashes by for a moment).
"""

import importlib
import sys
import time

import pytest

tkinter = pytest.importorskip("tkinter")
ctk = pytest.importorskip("customtkinter")


def pump(app, until=lambda: False, timeout=5.0):
    """Run Tk events until `until()` is true. Returns whether it became true."""
    end = time.time() + timeout
    while time.time() < end:
        app.update()
        if until():
            return True
        time.sleep(0.01)
    return until()


@pytest.fixture(scope="module")
def gui(tmp_path_factory):
    mp = pytest.MonkeyPatch()

    # Keep the window from ever touching the real machine.
    import memory
    import voice
    mp.setattr(memory, "PROFILE_PATH", str(tmp_path_factory.mktemp("prof") / "p.json"))
    spoken = []
    fake_speak = lambda text, blocking=False: spoken.append(text)
    mp.setattr(voice, "speak", fake_speak)
    for name in ("core.assistant", "core.countdown"):
        importlib.import_module(name)
        mp.setattr(sys.modules[name], "speak", fake_speak, raising=False)

    hotkeys = []
    mp.setattr(sys.modules["keyboard"], "add_hotkey", lambda keys, fn, *a, **k: hotkeys.append(keys), raising=False)
    mp.setattr(ctk.CTk, "mainloop", lambda self, *a, **k: None)

    sys.modules.pop("gui", None)
    try:
        module = importlib.import_module("gui")
    except tkinter.TclError as exc:
        mp.undo()
        pytest.skip(f"no display available for Tk: {exc}")

    module._test_spoken = spoken
    module._test_hotkeys = hotkeys
    module.app.deiconify()
    pump(module.app, timeout=0.2)

    yield module

    try:
        module.app.destroy()
    except Exception:
        pass
    sys.modules.pop("gui", None)
    mp.undo()


def submit(gui, text):
    gui.entry.delete(0, "end")
    gui.entry.insert(0, text)
    gui.execute_command()


def wait_idle(gui, timeout=5):
    return pump(gui.app, until=lambda: not gui._busy, timeout=timeout)


def test_window_builds(gui):
    assert gui.app.title() == "Project Hina"
    assert gui.app.winfo_exists()
    assert gui.entry.winfo_exists() and gui.send_btn.winfo_exists()


def test_startup_greeting_shown_and_spoken(gui):
    assert gui.output_var.get()
    assert pump(gui.app, until=lambda: len(gui._test_spoken) >= 1, timeout=2)


def test_global_hotkey_registered(gui):
    assert "ctrl+h" in gui._test_hotkeys


def test_command_gets_a_reply_and_is_spoken(gui, machine):
    submit(gui, "tell time")
    assert wait_idle(gui)
    assert "time is" in gui.output_var.get().lower()
    assert any("time is" in s.lower() for s in machine.spoken)
    assert gui.entry.get() == ""


def test_calculator_through_the_window(gui):
    submit(gui, "calculate 25*12")
    assert wait_idle(gui)
    assert "300" in gui.output_var.get()


def test_hostile_calculation_is_refused(gui):
    submit(gui, "calculate __import__('os').system('calc')")
    assert wait_idle(gui)
    assert "Invalid" in gui.output_var.get()


def test_conversation(gui):
    submit(gui, "hello")
    assert wait_idle(gui)
    assert gui.output_var.get()


def test_empty_input_is_ignored(gui):
    before = gui.output_var.get()
    submit(gui, "   ")
    pump(gui.app, timeout=0.2)
    assert gui.output_var.get() == before and not gui._busy


def test_slow_command_does_not_freeze_the_window(gui, monkeypatch):
    """The Sprint A guarantee: slow work runs off the UI thread."""
    def slow_dispatch(command, **kwargs):
        time.sleep(0.6)
        return gui.DispatchResult(reply="slow reply done")

    monkeypatch.setattr(gui, "dispatch_command", slow_dispatch)
    submit(gui, "tell time")
    assert gui._busy is True
    assert gui.sub_label.cget("text") == "thinking..."

    # The UI thread must stay responsive while the worker sleeps.
    start = time.time()
    ticks = 0
    while gui._busy and time.time() - start < 3:
        t0 = time.time()
        gui.app.update()
        assert time.time() - t0 < 0.3, "UI thread was blocked"
        ticks += 1
        time.sleep(0.02)
    assert ticks > 5
    assert gui.output_var.get() == "slow reply done"
    assert gui.sub_label.cget("text") == "your ambient companion"


def test_second_command_while_busy_is_ignored(gui, monkeypatch):
    calls = []

    def slow_dispatch(command, **kwargs):
        calls.append(command)
        time.sleep(0.4)
        return gui.DispatchResult(reply="first")

    monkeypatch.setattr(gui, "dispatch_command", slow_dispatch)
    submit(gui, "tell time")
    submit(gui, "tell date")
    assert wait_idle(gui)
    assert calls == ["tell time"]


def test_a_crashing_command_shows_a_friendly_message(gui, monkeypatch):
    def boom(command, **kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(gui, "dispatch_command", boom)
    submit(gui, "tell time")
    assert wait_idle(gui)
    assert "went wrong" in gui.output_var.get()
    assert gui._busy is False  # and it can take the next command


def test_toggle_window_hides_and_shows(gui):
    from ui.window import toggle_window
    gui.app.deiconify()
    pump(gui.app, timeout=0.1)
    toggle_window(gui.app, gui.entry)
    assert gui.app.state() == "withdrawn"
    toggle_window(gui.app, gui.entry)
    assert gui.app.state() != "withdrawn"


def test_exit_command_schedules_window_close(gui, monkeypatch):
    destroyed = []
    monkeypatch.setattr(gui.app, "destroy", lambda: destroyed.append(True))
    submit(gui, "bye")
    assert wait_idle(gui)
    assert pump(gui.app, until=lambda: destroyed, timeout=4)
