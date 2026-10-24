"""Sprint A regression tests. Run from the project root:  python -m pytest tests"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from parser import normalize_command
from utils.safe_math import safe_eval
from utils import launcher
from utils.file_search import search


@pytest.mark.parametrize("expr,expected", [("25*12", 300), ("(4+3)/2", 3.5), ("-2**3", -8), ("10%4", 2)])
def test_safe_math_ok(expr, expected):
    assert safe_eval(expr) == expected


@pytest.mark.parametrize("expr", ['__import__("os").system("x")', "open('f')", "2**99999", "1+", "", "a+1"])
def test_safe_math_rejects(expr):
    with pytest.raises(ValueError):
        safe_eval(expr)


def test_calculate_wrapper():
    import actions
    assert "300" in actions.calculate("25*12")
    assert "Invalid" in actions.calculate("__import__('os')")
    assert "Invalid" in actions.calculate("1/0")


@pytest.mark.parametrize("raw,expected", [
    ("open mysql", "open mysql"),
    ("close my spotify", "close spotify"),
    ("open my browser", "open browser"),
    ("find my notes.pdf", "find file notes.pdf"),
    ("find folder downloads", "find folder downloads"),
    ("please find my resume folder", "find folder resume"),
    ("open notes.txt", "open file notes.txt"),
])
def test_parser(raw, expected):
    assert normalize_command(raw) == expected


def test_parser_find_inside_sentence_is_not_a_command():
    assert not normalize_command("i cannot find it").startswith("find ")


@pytest.mark.parametrize("name", ["x & del *", "a | b", "../../evil", "x\ny", ""])
def test_launcher_rejects_unsafe_names(name):
    assert launcher.process_name_for(name) is None or name == ""
    assert launcher.kill_process(name)[0] is False


def test_process_name_mapping():
    assert launcher.process_name_for("vscode") == "Code.exe"
    assert launcher.process_name_for("spotify") == "Spotify.exe"


def test_protected_process_not_killed():
    assert launcher.kill_process("explorer")[0] is False


def test_file_search_finds_and_skips(tmp_path, monkeypatch):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "Report.txt").write_text("x")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "Report.txt").write_text("x")
    monkeypatch.setattr("utils.file_search.search_roots", lambda: [tmp_path])
    hits = search("report.txt", want="file")
    assert len(hits) == 1 and "node_modules" not in hits[0]
    assert search("docs", want="folder", exact=True)


def test_dispatcher_find_file_and_unknown_app(monkeypatch):
    import actions
    from core.dispatcher import dispatch_command
    monkeypatch.setattr(actions, "_search_files", lambda *a, **k: ["C:\\x\\notes.txt"])
    assert "notes.txt" in dispatch_command("find file notes").reply


def test_ollama_down_returns_fast(monkeypatch):
    from core import ai_engine
    import requests

    def boom(*a, **k):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(ai_engine.requests, "get", boom)
    ai_engine._health["checked_at"] = 0.0
    assert ai_engine.ollama_available() is False
    assert ai_engine.fallback_parse_command("open chrome please") is None
    assert ai_engine.resolve_tool_call("open chrome") is None


def test_ollama_payload_is_non_streaming_with_options(monkeypatch):
    from core import ai_engine
    sent = {}

    class R:
        def raise_for_status(self): pass
        def json(self): return {"response": "open chrome"}

    monkeypatch.setattr(ai_engine, "ollama_available", lambda: True)
    monkeypatch.setattr(ai_engine.requests, "post", lambda url, json, timeout: (sent.update(json), R())[1])
    assert ai_engine.fallback_parse_command("launch the browser") == "open chrome"
    assert sent["stream"] is False
    assert sent["options"]["temperature"] == 0.0 and "temperature" not in {k for k in sent if k != "options"}
