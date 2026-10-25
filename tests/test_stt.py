"""Speech-to-text: no microphone and no model needed, both are faked."""

import threading
import time

import pytest

from core.stt import SpeechInput, SttError, WhisperTranscriber, clean_transcript, collect_phrase, normalise
from test_gui_smoke import gui, pump, wait_idle  # noqa: F401  (fixture reuse)


def make(recorder=None, transcriber=None, **kw):
    return SpeechInput(
        recorder=recorder or (lambda cancel: [0.1] * 10),
        transcriber=transcriber or (lambda audio: "  tell time "),
        **kw,
    )


def test_listen_returns_stripped_transcript_and_reports_states():
    states = []
    assert make(on_state=states.append).listen() == "tell time"
    assert states == ["listening", "transcribing"]


def test_nothing_heard_skips_the_transcriber():
    called = []
    stt = make(recorder=lambda cancel: None, transcriber=lambda a: called.append(a) or "x")
    assert stt.listen() == ""
    assert called == []


def test_does_not_record_while_hina_is_speaking():
    speaking = [True]
    recorded_while_speaking = []

    def recorder(cancel):
        recorded_while_speaking.append(speaking[0])
        return [0.1]

    stt = make(recorder=recorder, is_speaking=lambda: speaking[0])
    threading.Timer(0.2, lambda: speaking.__setitem__(0, False)).start()
    states = []
    stt.on_state = states.append
    assert stt.listen() == "tell time"
    assert recorded_while_speaking == [False]
    assert states[0] == "waiting"


def test_gives_up_if_hina_never_stops_talking():
    stt = make(is_speaking=lambda: True, speaking_wait=0.2)
    with pytest.raises(SttError, match="still talking"):
        stt.listen()


def test_cancel_while_waiting_returns_empty():
    stt = make(is_speaking=lambda: True)
    threading.Timer(0.1, stt.cancel.set).start()
    assert stt.listen() == ""


def test_microphone_error_propagates_friendly():
    def broken(cancel):
        raise SttError("I can't reach a microphone")

    with pytest.raises(SttError, match="microphone"):
        make(recorder=broken).listen()


def test_missing_model_is_a_friendly_error(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "faster_whisper", None)  # import fails
    with pytest.raises(SttError, match="isn.t installed"):
        WhisperTranscriber()([0.0])


def _fake_whisper(monkeypatch, exc):
    import sys, types

    def boom(*a, **k):
        raise exc

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=boom))


def test_download_failure_is_reported_as_network(monkeypatch):
    _fake_whisper(monkeypatch, ConnectionError("Max retries exceeded"))
    with pytest.raises(SttError, match="download"):
        WhisperTranscriber()([0.0])


def test_other_load_failure_names_the_real_error(monkeypatch):
    _fake_whisper(monkeypatch, ValueError("bad compute type"))
    with pytest.raises(SttError, match="ValueError: bad compute type"):
        WhisperTranscriber()([0.0])


def feed(levels):
    """Each 'block' is just its RMS level, so rms=identity."""
    it = iter(levels)
    return lambda: next(it, 0.0)


def phrase(levels):
    return collect_phrase(feed(levels), rms=lambda b: b)


def test_quiet_laptop_mic_speech_is_detected():
    # room noise ~0.0001, speech only ~0.004: the old 0.015 floor missed this
    quiet_room = [0.0001] * 5
    kept = phrase(quiet_room + [0.004] * 8 + [0.0001] * 12)
    assert kept is not None
    assert kept.count(0.004) == 8


def test_first_word_is_not_clipped():
    kept = phrase([0.0001] * 5 + [0.0008, 0.005, 0.005] + [0.0001] * 12)
    assert 0.0008 in kept  # pre-roll keeps the soft onset


def test_silent_input_is_reported_as_a_mic_problem():
    with pytest.raises(SttError, match="only hearing silence"):
        phrase([0.00004] * 200)


def test_room_noise_without_speech_is_just_nothing_heard():
    assert phrase([0.0008] * 200) is None


def test_phrase_ends_after_a_pause():
    kept = phrase([0.0001] * 3 + [0.01] * 5 + [0.0001] * 9 + [0.01] * 50)
    assert kept.count(0.01) == 5


def test_normalise_boosts_quiet_audio():
    import numpy as np
    out = normalise(np.array([0.001, -0.002], dtype="float32"))
    assert abs(float(abs(out).max()) - 0.9) < 1e-6


@pytest.mark.parametrize("heard, typed", [
    ("Open Chrome.", "Open Chrome"),
    ("Tell time.", "Tell time"),
    ("What can you do?", "What can you do"),
    ("Set name, Parthiv.", "Set name Parthiv"),
    ("Open file notes.txt.", "Open file notes.txt"),
    ("Calculate 25 times 12.", "Calculate 25 * 12"),
    ("Calculate 100 divided by 4, plus 3.", "Calculate 100 / 4 + 3"),
    ("Calculate 7x8", "Calculate 7 * 8"),
    ("Calculate 2 to the power of 10.", "Calculate 2 ** 10"),
    ("", ""),
])
def test_clean_transcript_matches_typed_commands(heard, typed):
    assert clean_transcript(heard) == typed


def test_math_words_are_left_alone_outside_calculate():
    assert clean_transcript("Search google times square.") == "Search google times square"


def test_listen_returns_cleaned_text():
    assert make(transcriber=lambda a: "Open Chrome.").listen() == "Open Chrome"


class _Seg:
    def __init__(self, text):
        self.text = text


def test_gpu_failure_falls_back_to_cpu(monkeypatch):
    import sys, types
    built = []

    class Model:
        def __init__(self, name, device, compute_type):
            built.append((name, device))
            self.device = device

        def transcribe(self, audio, **kw):
            if self.device == "cuda":
                raise RuntimeError("cublas64_12.dll not found")
            return [_Seg(" Open Chrome.")], None

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=Model))
    t = WhisperTranscriber(use_gpu=True, prompt="p")
    assert t([0.0]) == "Open Chrome."
    assert built == [("small.en", "cuda"), ("base.en", "cpu")]


def test_decoding_is_primed_with_commands_and_saved_name(monkeypatch):
    import sys, types
    import memory
    seen = {}

    class Model:
        def __init__(self, *a, **k):
            pass

        def transcribe(self, audio, **kw):
            seen.update(kw)
            return [], None

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=Model))
    monkeypatch.setattr(memory, "get_name", lambda: "Parthiv")
    WhisperTranscriber(use_gpu=False)([0.0])
    assert "open chrome" in seen["initial_prompt"]
    assert "Parthiv" in seen["initial_prompt"]
    assert seen["beam_size"] == 5


def test_voice_module_tracks_speaking(monkeypatch):
    import voice
    monkeypatch.setattr(voice, "_HAS_EDGE_TTS", False)
    gate = threading.Event()
    monkeypatch.setattr(voice, "_speak_sync", lambda text: gate.wait(2))
    assert not voice.is_speaking()
    # conftest replaces voice.speak, so do what the real one does by hand.
    voice._mark(1)
    threading.Thread(target=voice._speak_thread, args=("hello",), daemon=True).start()
    assert voice.is_speaking()
    gate.set()
    end = time.time() + 2
    while voice.is_speaking() and time.time() < end:
        time.sleep(0.01)
    assert not voice.is_speaking()


# Imported at load time: conftest swaps voice.speak for a recorder once tests start.
from voice import speak as real_speak  # noqa: E402


def test_speech_is_queued_in_order_and_one_at_a_time(monkeypatch):
    import voice
    spoken, overlap, active = [], [], [0]

    def fake_utterance(text):
        active[0] += 1
        overlap.append(active[0])
        time.sleep(0.02)
        spoken.append(text)
        active[0] -= 1
        voice._mark(-1)

    monkeypatch.setattr(voice, "_speak_thread", fake_utterance)
    for word in ("one", "two", "three"):
        real_speak(word)
    real_speak("four", blocking=True)
    assert spoken == ["one", "two", "three", "four"]
    assert max(overlap) == 1
    assert not voice.is_speaking()


# --- through the window -------------------------------------------------

def fake_speech(gui, monkeypatch, text="", error=None, delay=0.0):
    def listen():
        gui.speech.on_state("listening")
        time.sleep(delay)
        gui.speech.on_state("transcribing")
        if error:
            raise SttError(error)
        return text

    monkeypatch.setattr(gui.speech, "listen", listen)


def test_mic_button_and_hotkey_exist(gui):
    assert gui.mic_btn.winfo_exists()
    assert "ctrl+m" in gui._test_hotkeys


def test_spoken_command_goes_through_the_normal_path(gui, monkeypatch, machine):
    fake_speech(gui, monkeypatch, text="tell time", delay=0.3)
    gui.toggle_listening()
    assert gui._busy and gui._listening
    pump(gui.app, until=lambda: "listening" in gui.sub_label.cget("text"), timeout=1)
    assert "listening" in gui.sub_label.cget("text")
    assert wait_idle(gui)
    assert "time is" in gui.output_var.get().lower()
    assert not gui._listening


def test_ui_stays_responsive_while_listening(gui, monkeypatch):
    fake_speech(gui, monkeypatch, text="", delay=0.6)
    gui.toggle_listening()
    start = time.time()
    while gui._busy and time.time() - start < 3:
        t0 = time.time()
        gui.app.update()
        assert time.time() - t0 < 0.3
        time.sleep(0.02)
    assert "didn't catch" in gui.output_var.get()


def test_mic_failure_shows_friendly_message(gui, monkeypatch):
    fake_speech(gui, monkeypatch, error="I can't reach a microphone 🎤")
    gui.toggle_listening()
    assert wait_idle(gui)
    assert "microphone" in gui.output_var.get()
    assert gui.sub_label.cget("text") == "your ambient companion"


def test_clicking_mic_again_cancels(gui, monkeypatch):
    def listen():
        gui.speech.cancel.clear()
        gui.speech.cancel.wait(3)
        return ""

    monkeypatch.setattr(gui.speech, "listen", listen)
    gui.output_var.set("before")
    gui.toggle_listening()
    pump(gui.app, timeout=0.2)
    gui.toggle_listening()  # second click
    assert wait_idle(gui)
    assert "didn't catch" not in gui.output_var.get()


def test_mic_ignored_while_busy(gui):
    gui._set_busy(True)
    try:
        gui.toggle_listening()
        assert not gui._listening
    finally:
        gui._set_busy(False)
