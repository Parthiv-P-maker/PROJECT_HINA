"""
Shared test setup. Nothing in the suite may touch the real laptop:
no real apps launched, no real processes killed, no network, no speech,
and the real memory/user_profile.json is never written.
"""

import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest


def _stub_if_missing(name, **attrs):
    """Provide a stand-in for an optional/hardware package that isn't installed."""
    try:
        __import__(name)
    except Exception:
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module


# Hardware / global-hook packages: never let a test reach the real ones.
sys.modules["keyboard"] = types.SimpleNamespace(add_hotkey=lambda *a, **k: None)
_stub_if_missing(
    "psutil",
    sensors_battery=lambda: None,
    disk_usage=lambda path: types.SimpleNamespace(free=1024 ** 3, total=2 * 1024 ** 3),
)


# The reminder checker is a background thread the windows start; tests call reminders.check() directly.
from core import reminders as _reminders  # noqa: E402
_reminders._started.set()
from utils import file_index as _file_index  # noqa: E402
_file_index._started.set()  # no background disk scans in tests


@pytest.fixture(autouse=True)
def isolate_machine(tmp_path, monkeypatch):
    """Runs around every test."""
    import memory
    import voice

    # 0. Action log / user data go to a temp dir; no pending confirmation leaks between tests.
    monkeypatch.setenv("HINA_DATA_DIR", str(tmp_path / "hina_data"))
    from core import conversation, permissions
    permissions.cancel_pending("test-reset")
    conversation.set_stream_sink(None)

    from core import personality_engine
    monkeypatch.setattr(personality_engine, "CURRENT_PERSONALITY", None)  # reload from the temp profile

    # 1. Memory goes to a throwaway file.
    profile = tmp_path / "user_profile.json"
    monkeypatch.setattr(memory, "PROFILE_PATH", str(profile))

    # 2. No speech. `speak` is imported by name in several modules, so patch each.
    spoken = []
    fake_speak = lambda text, blocking=False: spoken.append(text)
    monkeypatch.setattr(voice, "speak", fake_speak)
    for module_name in ("core.assistant", "core.countdown"):
        module = sys.modules.get(module_name)
        if module is not None:
            monkeypatch.setattr(module, "speak", fake_speak, raising=False)

    # 3. No real launching / killing / opening files.
    import subprocess
    os_calls = {"startfile": [], "popen": [], "run": []}
    monkeypatch.setattr(os, "startfile", lambda path: os_calls["startfile"].append(path), raising=False)

    class _Popen:
        def __init__(self, args, *a, **k):
            os_calls["popen"].append(args)

    monkeypatch.setattr(subprocess, "Popen", _Popen)

    class _Done:
        returncode = 0
        stdout = ""
        stderr = ""

    def _run(args, *a, **k):
        os_calls["run"].append(args)
        return _Done()

    monkeypatch.setattr(subprocess, "run", _run)

    # 3b. No volume, brightness, media keys, lock/sleep/shutdown (utils/device.py).
    from utils import device
    device_calls = []
    fake_state = {"volume": 50, "muted": False, "brightness": 70}

    def _record(name, result=None):
        def fake(*args, **kwargs):
            device_calls.append((name, args))
            return result() if callable(result) else result
        return fake

    def _set_volume(percent):
        device_calls.append(("set_volume", (percent,)))
        fake_state["volume"] = max(0, min(100, int(percent)))
        return fake_state["volume"]

    def _change_volume(delta):
        return _set_volume(fake_state["volume"] + delta)

    def _set_brightness(percent):
        device_calls.append(("set_brightness", (percent,)))
        fake_state["brightness"] = max(0, min(100, int(percent)))
        return fake_state["brightness"]

    def _set_mute(muted):
        device_calls.append(("set_mute", (muted,)))
        fake_state["muted"] = bool(muted)

    monkeypatch.setattr(device, "get_volume", lambda: (fake_state["volume"], fake_state["muted"]))
    monkeypatch.setattr(device, "set_volume", _set_volume)
    monkeypatch.setattr(device, "change_volume", _change_volume)
    monkeypatch.setattr(device, "set_mute", _set_mute)
    monkeypatch.setattr(device, "get_brightness", lambda: fake_state["brightness"])
    monkeypatch.setattr(device, "set_brightness", _set_brightness)
    for name in ("lock", "sleep", "shutdown", "media", "spotify_search", "_media_key", "_powershell"):
        monkeypatch.setattr(device, name, _record(name))
    monkeypatch.setattr(device, "cancel_shutdown", _record("cancel_shutdown", True))
    monkeypatch.setattr(device, "now_playing", lambda: "")

    # 3c. No real windows, clipboard or disk scans (utils/windows.py, utils/clipboard.py, utils/file_index.py).
    from utils import clipboard, file_index, windows
    fake_windows = [windows.Win(101, "Inbox - Google Chrome", "chrome.exe"),
                    windows.Win(102, "main.py - Visual Studio Code", "code.exe"),
                    windows.Win(103, "Spotify Premium", "spotify.exe")]
    window_calls = []
    monkeypatch.setattr(windows, "list_windows", lambda: list(fake_windows))
    for name in ("focus", "minimise", "maximise", "snap", "minimise_all"):
        monkeypatch.setattr(windows, name, (lambda n: lambda *a: window_calls.append((n, a)))(name))
    monkeypatch.setattr(windows, "running_processes", lambda: {"chrome.exe", "code.exe", "discord.exe"})
    clip = {"text": ""}
    monkeypatch.setattr(clipboard, "get_text", lambda: clip["text"])
    monkeypatch.setattr(clipboard, "set_text", lambda text: clip.__setitem__("text", text) or True)
    files_root = tmp_path / "files"
    files_root.mkdir()
    monkeypatch.setattr(file_index, "_roots", lambda: [files_root])
    from utils import documents
    documents.close()

    # 4. No browser windows.
    import webbrowser
    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: opened.append(url) or True)

    # 5. No network: a test that wants Ollama uses fake_ollama (or patches these itself).
    import core.ai_engine as ai_engine

    def _no_network(*a, **k):
        raise ai_engine.requests.ConnectionError("network disabled in tests")

    monkeypatch.setattr(ai_engine.requests, "get", _no_network)
    monkeypatch.setattr(ai_engine.requests, "post", _no_network)

    # 6. Fresh AI + session state.
    ai_engine._health["checked_at"] = 0.0
    ai_engine._health["ok"] = False
    ai_engine._health["models"] = None
    from core.context_manager import context_manager
    context_manager.recent_commands.clear()
    context_manager.recent_failures.clear()

    return types.SimpleNamespace(spoken=spoken, os_calls=os_calls, browser=opened, profile=profile,
                                 device=device_calls, device_state=fake_state, windows=window_calls,
                                 clipboard=clip, files_root=files_root)


@pytest.fixture
def machine(isolate_machine):
    """The recorder of everything that WOULD have touched the laptop."""
    return isolate_machine


@pytest.fixture
def ollama_down(monkeypatch):
    """Ollama is not running."""
    import core.ai_engine as ai_engine
    monkeypatch.setattr(ai_engine, "ollama_available", lambda: False)


@pytest.fixture
def fake_ollama(monkeypatch):
    """
    A scriptable Ollama. Set `.generate_reply` / `.tool_call` / `.chat_reply` on
    the returned object; every request is recorded in `.requests`.
    """
    import core.ai_engine as ai_engine

    class Fake:
        def __init__(self):
            self.requests = []
            self.generate_reply = "UNKNOWN"
            self.tool_call = None  # e.g. ("open_app", {"name": "chrome"})
            self.chat_reply = "hi"  # /api/chat content when no tool is called

    fake = Fake()

    class _Resp:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            pass

        def json(self):
            return self._data

    class _Stream:
        """A streamed /api/chat answer: the reply in 4-character pieces, as NDJSON lines."""

        def __init__(self, text):
            self.text = text

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def raise_for_status(self):
            pass

        def iter_lines(self):
            import json as _json
            for i in range(0, len(self.text), 4):
                yield _json.dumps({"message": {"content": self.text[i:i + 4]}, "done": False}).encode()
            yield _json.dumps({"message": {"content": ""}, "done": True}).encode()

    def post(url, json=None, timeout=None, stream=False):
        fake.requests.append((url, json))
        if stream and url.endswith("/api/chat"):
            return _Stream(fake.chat_reply)
        if url.endswith("/api/chat"):
            if fake.tool_call is None:
                return _Resp({"message": {"content": fake.chat_reply}})
            name, args = fake.tool_call
            return _Resp({"message": {"tool_calls": [{"function": {"name": name, "arguments": args}}]}})
        return _Resp({"response": fake.generate_reply})

    monkeypatch.setattr(ai_engine, "ollama_available", lambda: True)
    monkeypatch.setattr(ai_engine.requests, "post", post)
    return fake
