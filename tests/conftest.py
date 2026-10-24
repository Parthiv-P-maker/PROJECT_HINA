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


@pytest.fixture(autouse=True)
def isolate_machine(tmp_path, monkeypatch):
    """Runs around every test."""
    import memory
    import voice

    # 0. Action log / user data go to a temp dir; no pending confirmation leaks between tests.
    monkeypatch.setenv("HINA_DATA_DIR", str(tmp_path / "hina_data"))
    from core import permissions
    permissions.cancel_pending("test-reset")

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

    # 4. No browser windows.
    import webbrowser
    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: opened.append(url) or True)

    # 5. Fresh AI + session state.
    import core.ai_engine as ai_engine
    ai_engine._health["checked_at"] = 0.0
    ai_engine._health["ok"] = False
    from core.context_manager import context_manager
    context_manager.recent_commands.clear()
    context_manager.recent_failures.clear()

    return types.SimpleNamespace(spoken=spoken, os_calls=os_calls, browser=opened, profile=profile)


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
    A scriptable Ollama. Set `.generate_reply` / `.tool_call` on the returned
    object; every request is recorded in `.requests`.
    """
    import core.ai_engine as ai_engine

    class Fake:
        def __init__(self):
            self.requests = []
            self.generate_reply = "UNKNOWN"
            self.tool_call = None  # e.g. ("open_app", {"name": "chrome"})

    fake = Fake()

    class _Resp:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            pass

        def json(self):
            return self._data

    def post(url, json=None, timeout=None):
        fake.requests.append((url, json))
        if url.endswith("/api/chat"):
            if fake.tool_call is None:
                return _Resp({"message": {"content": "hi"}})
            name, args = fake.tool_call
            return _Resp({"message": {"tool_calls": [{"function": {"name": name, "arguments": args}}]}})
        return _Resp({"response": fake.generate_reply})

    monkeypatch.setattr(ai_engine, "ollama_available", lambda: True)
    monkeypatch.setattr(ai_engine.requests, "post", post)
    return fake
