"""Phase 2 cleanup: voice engines (2.5), barge-in by the wake phrase (2.4)."""

import os

import pytest

import voice


@pytest.fixture
def engines(monkeypatch):
    """Record which engine spoke; each can be made to fail."""
    calls = []
    state = {"edge": True, "piper": True}

    def edge(text):
        if not state["edge"]:
            raise ConnectionError("403")
        calls.append(("edge", text))
        return b"mp3"

    def piper(text):
        if not state["piper"]:
            return None
        calls.append(("piper", text))
        return b"wav"

    monkeypatch.setattr(voice, "_HAS_EDGE_TTS", True)
    monkeypatch.setattr(voice, "_HAS_PYGAME", True)
    monkeypatch.setattr(voice, "_edge_audio", edge)
    monkeypatch.setattr(voice, "_piper_audio", piper)
    monkeypatch.setattr(voice, "_play", lambda audio, hint, gen: calls.append(("play", hint)))
    monkeypatch.setattr(voice, "_speak_sync", lambda text: calls.append(("windows", text)))
    monkeypatch.setattr(voice, "_edge_down_until", 0.0)
    return calls, state


def _say(text):
    voice._mark(1)
    voice._speak_thread(text)


def test_online_voice_first_played_from_memory(engines):
    calls, _ = engines
    _say("Hello 🌸")
    assert calls == [("edge", "Hello"), ("play", "mp3")]
    assert not voice.is_speaking()


def test_offline_neural_voice_when_online_fails_and_online_rests(engines):
    calls, state = engines
    state["edge"] = False
    _say("one")
    state["edge"] = True  # back up, but it's skipped for EDGE_RETRY_SECONDS
    _say("two")
    assert calls == [("piper", "one"), ("play", "wav"), ("piper", "two"), ("play", "wav")]
    voice._edge_down_until = 0.0
    _say("three")
    assert calls[-2:] == [("edge", "three"), ("play", "mp3")]


def test_windows_voice_is_the_last_resort(engines):
    calls, state = engines
    state["edge"] = state["piper"] = False
    _say("hi")
    assert calls == [("windows", "hi")]


def test_local_only_skips_the_online_voice(engines, monkeypatch):
    calls, _ = engines
    monkeypatch.setattr(voice, "_HAS_EDGE_TTS", False)  # what settings "local_only" does
    _say("hi")
    assert calls == [("piper", "hi"), ("play", "wav")]


def test_piper_is_available_only_with_a_downloaded_model(monkeypatch, tmp_path):
    pytest.importorskip("piper")
    monkeypatch.setattr(voice, "PIPER_VOICE", "en_US-test-medium")
    assert not voice.piper_available()
    path = voice.piper_model_path()
    assert path.startswith(str(tmp_path)) and path.endswith(os.path.join("voices", "en_US-test-medium.onnx"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").close()
    assert voice.piper_available()


def test_settings_choose_the_offline_voice(monkeypatch):
    from ui_qt import settings as settings_mod
    monkeypatch.setattr(voice, "warm_up_offline_voice", lambda: None)
    settings_mod.apply_runtime(dict(settings_mod.DEFAULTS, offline_voice="en_GB-alba-medium"))
    assert voice.PIPER_VOICE == "en_GB-alba-medium"
    settings_mod.apply_runtime(settings_mod.DEFAULTS)


def test_self_check_reports_both_voices(monkeypatch):
    from core import doctor
    monkeypatch.setattr(voice, "_HINA_EDGE_AVAILABLE", True, raising=False)
    monkeypatch.setattr(voice, "_HAS_PYGAME", True)
    monkeypatch.setattr(voice, "_edge_audio", lambda text: b"mp3")
    by_area = {c.area: c for c in doctor.check_voice({})}
    assert by_area["Online voice"].status == doctor.OK
    assert by_area["Offline voice"].status == doctor.WARN and "piper.download_voices" in by_area["Offline voice"].fix

    def refused(text):
        raise RuntimeError("403, message='Invalid response status'")

    monkeypatch.setattr(voice, "_edge_audio", refused)
    online = {c.area: c for c in doctor.check_voice({})}["Online voice"]
    assert online.status == doctor.WARN and "pip install -U edge-tts" in online.fix
    assert {c.area: c for c in doctor.check_voice({"local_only": True})}["Online voice"].detail.startswith("not used")


# ---- 2.4 barge-in by the wake phrase ---------------------------------------------------

@pytest.fixture
def bridge(qtbot):
    pytest.importorskip("PySide6")
    from ui_qt.bridge import HinaBridge
    return HinaBridge({})


def test_wake_mic_stays_open_while_hina_talks(bridge, monkeypatch):
    monkeypatch.setattr(voice, "is_speaking", lambda: True)
    assert not bridge._wake_paused()
    bridge.settings = {"voice_barge_in": False}
    assert bridge._wake_paused()


def test_wake_phrase_while_talking_stops_her(bridge, monkeypatch):
    stops, heard = [], []
    monkeypatch.setattr(voice, "is_speaking", lambda: True)
    monkeypatch.setattr(voice, "stop", lambda: stops.append(1))
    bridge.wake_heard.connect(heard.append)
    bridge._wake_fired("what's the time")
    assert stops == [1] and heard == ["what's the time"]


def test_wake_phrase_when_quiet_does_not_call_stop(bridge, monkeypatch):
    stops = []
    monkeypatch.setattr(voice, "is_speaking", lambda: False)
    monkeypatch.setattr(voice, "stop", lambda: stops.append(1))
    bridge._wake_fired("")
    assert stops == []
