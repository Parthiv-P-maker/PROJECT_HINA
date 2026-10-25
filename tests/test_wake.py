"""2.2 wake word ("Hey Hina") and 2.6 follow-up listening."""

import os
import sys
import threading
import time

import pytest

from core import wake

# ---- matching what Whisper heard ------------------------------------------------


@pytest.mark.parametrize("heard, woke, rest", [
    ("Hey Hina.", True, ""),
    ("Hey Hina, open Chrome.", True, "open Chrome"),
    ("Hina what's the time?", True, "what's the time"),
    ("Hey Nina, set a timer for 5 minutes", True, "set a timer for 5 minutes"),
    ("Oh hey Hina!", True, ""),
    ("OK Hina play music", True, "play music"),
    ("Heena", True, ""),
    ("Nina is coming over", False, ""),
    ("He wants to see Hina later", False, ""),
    ("hey china", False, ""),
    ("", False, ""),
])
def test_match_wake(heard, woke, rest):
    assert wake.match_wake(heard) == (woke, rest)


def test_the_wake_prompt_cannot_wake_hina_by_itself():
    """On unclear audio Whisper echoes its prompt; that echo must not count."""
    assert wake.match_wake(wake.WAKE_PROMPT) == (False, "")


# ---- cutting speech out of the stream ---------------------------------------------

def test_segmenter_returns_a_stretch_after_a_pause():
    probs = iter([0.1, 0.1, 0.9, 0.9, 0.9, 0.9] + [0.05] * wake.SEGMENT_END_BLOCKS)
    seg = wake.SpeechSegmenter(lambda block: next(probs))
    out = [seg.feed([i]) for i in range(6 + wake.SEGMENT_END_BLOCKS)]
    assert all(o is None for o in out[:-1])
    assert out[-1] is not None and len(out[-1]) == 2 + 4 + wake.SEGMENT_END_BLOCKS  # pre-roll kept


def test_segmenter_ignores_blips():
    probs = iter([0.9] + [0.05] * wake.SEGMENT_END_BLOCKS)
    seg = wake.SpeechSegmenter(lambda block: next(probs))
    assert all(seg.feed([0]) is None for _ in range(1 + wake.SEGMENT_END_BLOCKS))


# ---- the listener -------------------------------------------------------------------------

class _Vad:
    """Speech for the first 5 blocks of each stream, then silence."""

    def __init__(self):
        self.n = 0

    def reset(self):
        self.n = 0

    def __call__(self, block):
        self.n += 1
        return 0.9 if self.n <= 5 else 0.05


def _blocks_once(count=20):
    opened = []

    def open_blocks(keep_going):
        opened.append(1)
        import numpy as np
        for _ in range(count):
            if not keep_going():
                return
            yield np.full(1600, 0.1, dtype="float32")
        while keep_going():  # an idle mic
            time.sleep(0.01)
            yield np.zeros(1600, dtype="float32")
    return open_blocks, opened


def test_listener_wakes_with_the_command_that_followed():
    woke = threading.Event()
    got, prompts = [], []

    def transcriber(audio, prompt=None):
        prompts.append(prompt)
        return "Hey Hina, open Spotify."

    blocks, _ = _blocks_once()
    listener = wake.WakeListener(on_wake=lambda c: (got.append(c), woke.set()), transcriber=transcriber,
                                 open_blocks=blocks, vad=_Vad())
    listener.start()
    try:
        assert woke.wait(3)
    finally:
        listener.stop()
    assert got == ["open Spotify"]
    assert prompts == [wake.WAKE_PROMPT] and not listener.running


def test_other_speech_does_not_wake():
    called = []
    blocks, _ = _blocks_once()
    listener = wake.WakeListener(on_wake=called.append, transcriber=lambda a, prompt=None: "pass the salt",
                                 open_blocks=blocks, vad=_Vad())
    listener.start()
    time.sleep(0.5)
    listener.stop()
    assert called == []


def test_paused_listener_never_opens_the_mic():
    blocks, opened = _blocks_once()
    listener = wake.WakeListener(on_wake=lambda c: None, transcriber=lambda a, prompt=None: "",
                                 is_paused=lambda: True, open_blocks=blocks, vad=_Vad())
    listener.start()
    time.sleep(0.3)
    listener.stop()
    assert opened == []


def test_voice_toggle_without_the_hud():
    from core.dispatcher import dispatch_command
    from core.command_router import route_command
    assert route_command("turn on wake word") == "wake word on"
    assert "main HUD" in dispatch_command("wake word on").reply
    seen = []
    wake.set_controller(seen.append)
    assert dispatch_command("wake word off").reply == ""
    assert seen == [False]


def test_stt_listen_passes_the_follow_up_timeout():
    from core.stt import SpeechInput
    calls = []

    def recorder(cancel, **kwargs):
        calls.append(kwargs)
        return None

    speech = SpeechInput(recorder=recorder, transcriber=lambda a: "")
    speech.listen()
    speech.listen(no_speech_timeout=8)
    assert calls == [{}, {"no_speech_timeout": 8}]


def test_collect_phrase_waits_as_long_as_asked():
    from core import stt
    blocks = iter([[0.0002] * 10] * 200)
    reads = []

    def read():
        reads.append(1)
        return next(blocks)

    with pytest.raises(stt.SttError):  # dead-quiet input is reported as a silent mic
        stt.collect_phrase(read, speech_prob=lambda b: 0.0, no_speech_timeout=3)
    assert len(reads) == int(3 / stt.BLOCK_SECONDS) + 1


# ---- in the HUD ------------------------------------------------------------------------------

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))


class _Speech:
    """Stands in for core.stt.SpeechInput: hears the queued texts in turn, then nothing."""

    def __init__(self, *texts):
        self.cancel = threading.Event()
        self.texts = list(texts)
        self.timeouts = []

    def listen(self, no_speech_timeout=None):
        self.timeouts.append(no_speech_timeout)
        time.sleep(0.05)
        return self.texts.pop(0) if self.texts else ""


class _FakeListener:
    def __init__(self):
        self.running = False

    def start(self):
        self.running = True

    def stop(self):
        self.running = False


@pytest.fixture
def hud(qtbot, monkeypatch):
    pytest.importorskip("PySide6")
    pytest.importorskip("pytestqt")
    import core.ai_engine as ai_engine
    monkeypatch.setattr(ai_engine, "ollama_available", lambda: False)
    from ui_qt import settings as settings_mod
    from ui_qt.window import HinaWindow
    w = HinaWindow(settings_mod.load(), tray=False, hotkeys=False, speak=lambda text: None)
    qtbot.addWidget(w)
    w.show()
    yield w
    w.cancel_follow_up()
    qtbot.waitUntil(lambda: not w.bridge.busy and not w.bridge.listening, timeout=5000)
    w.quit_app()


def _text(w):
    w.console.finish()
    return w.console.plain_text()


def test_wake_with_a_command_runs_it(hud, qtbot):
    hud.bridge._speech = _Speech()
    hud.bridge.wake_heard.emit("tell time")
    qtbot.waitUntil(lambda: "time is" in _text(hud).lower(), timeout=3000)
    assert "Wake word heard." in _text(hud) and "YOU   tell time" in _text(hud)


def test_wake_alone_opens_the_mic_then_follows_up(hud, qtbot):
    speech = _Speech("tell time")
    hud.bridge._speech = speech
    hud.bridge.wake_heard.emit("")
    qtbot.waitUntil(lambda: "time is" in _text(hud).lower(), timeout=3000)
    # a spoken exchange: the mic reopens for a follow-up, and nobody says anything
    qtbot.waitUntil(lambda: "Standing by." in _text(hud), timeout=4000)
    assert speech.timeouts == [None, 8]
    assert "Listening for a follow-up" in _text(hud)


def test_follow_up_chains_while_the_user_keeps_talking(hud, qtbot):
    speech = _Speech("tell time", "tell date")
    hud.bridge._speech = speech
    hud.toggle_listening()
    qtbot.waitUntil(lambda: "date is" in _text(hud).lower(), timeout=4000)
    qtbot.waitUntil(lambda: "Standing by." in _text(hud), timeout=4000)
    assert speech.timeouts == [None, 8, 8]


def test_typed_commands_and_the_setting_skip_follow_up(hud, qtbot):
    speech = _Speech()
    hud.bridge._speech = speech
    hud.entry.setText("tell time")
    hud.execute_command()
    qtbot.waitUntil(lambda: not hud.bridge.busy, timeout=3000)
    qtbot.wait(400)
    assert speech.timeouts == []

    hud.settings["follow_up"] = False
    speech.texts = ["tell time"]
    hud.toggle_listening()
    qtbot.waitUntil(lambda: "time is" in _text(hud).lower(), timeout=3000)
    qtbot.wait(400)
    assert speech.timeouts == [None]


def test_wake_toggle_by_voice_and_settings(hud, qtbot, monkeypatch):
    listener = _FakeListener()
    real_start = hud.bridge.start_wake
    monkeypatch.setattr(hud.bridge, "start_wake", lambda: real_start(listener=listener))
    from core.dispatcher import dispatch_command
    dispatch_command("wake word on")  # tools run off the GUI thread; the window picks it up
    qtbot.waitUntil(lambda: listener.running, timeout=2000)
    assert hud.settings["wake_word"] is True
    assert hud.status.mic.value == "WAKE"  # the status panel shows the mic is armed
    assert "Wake word on" in _text(hud)
    hud.apply_settings(dict(hud.settings, wake_word=False))
    assert not listener.running and "Wake word off." in _text(hud)


def test_wake_listener_pauses_while_busy_or_listening(hud, qtbot):
    bridge = hud.bridge
    bridge._speech = _Speech()  # waking opens the command mic: never the real one in tests
    assert not bridge._wake_paused()
    bridge.listening = True
    assert bridge._wake_paused()
    bridge.listening = False
    bridge._wake_fired("")
    assert bridge._wake_paused()  # a short quiet spell after waking
    # finish inside the test: pytest-qt schedules the window's deletion before fixture cleanup runs
    qtbot.waitUntil(lambda: not bridge.listening, timeout=3000)
