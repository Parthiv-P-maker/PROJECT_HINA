"""Hardening sprint: complete requirements, file logging, speech in every language, self-check."""

import logging
import os
import sys
import threading

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---- requirements ------------------------------------------------------------------

def test_requirements_list_every_package_the_code_needs():
    from core.doctor import PACKAGES
    with open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8") as f:
        listed = {line.split(">=")[0].split("==")[0].strip().lower() for line in f
                  if line.strip() and not line.startswith("#")}
    for pip_name, _, _, _ in PACKAGES:
        assert pip_name.lower() in listed, f"{pip_name} is checked by the doctor but missing from requirements.txt"


# ---- speech text --------------------------------------------------------------------

@pytest.mark.parametrize("text, spoken", [
    ("Opening Chrome 🌸", "Opening Chrome"),
    ("Café crème, s'il vous plaît", "Café crème, s'il vous plaît"),
    ("नमस्ते दोस्त", "नमस्ते दोस्त"),
    ("നമസ്കാരം", "നമസ്കാരം"),
    ("こんにちは ✨", "こんにちは"),
    ("Kochi: 29°C 🌤️", "Kochi: 29 degrees C"),
    ("👨‍👩‍👧 family", "family"),
])
def test_clean_text_keeps_languages_and_drops_emoji(text, spoken):
    from utils.helpers import clean_text
    assert clean_text(text) == spoken


@pytest.mark.parametrize("text, voice_name", [
    ("Hello there", None),
    ("In Hindi: नमस्ते दोस्त", "hi-IN-SwaraNeural"),
    ("In Malayalam: നമസ്കാരം", "ml-IN-SobhanaNeural"),
    ("こんにちは 世界", "ja-JP-NanamiNeural"),
    ("你好世界", "zh-CN-XiaoxiaoNeural"),
    ("Bonjour, café crème", None),
    ("Hello नम", None),  # a stray word doesn't switch the voice
])
def test_voice_follows_the_script(text, voice_name):
    import voice
    assert voice.voice_for(text, default="USER") == (voice_name or "USER")


# ---- log file -------------------------------------------------------------------------

@pytest.fixture
def file_logging():
    from utils import logger as log
    hooks = sys.excepthook, threading.excepthook
    path = log.enable_file_logging()
    yield path
    handler = log._file_handler
    for lg in log._loggers:
        lg.removeHandler(handler)
    handler.close()
    log._file_handler = None
    sys.excepthook, threading.excepthook = hooks


def test_logs_go_to_a_file_in_the_data_folder(file_logging, tmp_path):
    from utils.logger import get_logger
    assert file_logging.startswith(str(tmp_path)) and file_logging.endswith(os.path.join("logs", "hina.log"))
    get_logger("tests.early").info("written by an existing logger")
    get_logger("tests.late.%d" % id(file_logging)).warning("written by a new logger")
    from utils.logger import enable_file_logging
    assert enable_file_logging() == file_logging  # calling twice is harmless
    for lg in logging.root.manager.loggerDict.values():
        for h in getattr(lg, "handlers", []):
            h.flush()
    text = open(file_logging, encoding="utf-8").read()
    assert "written by an existing logger" in text and "written by a new logger" in text


def test_thread_crashes_are_logged(file_logging):
    def boom():
        raise RuntimeError("kaboom in a thread")

    t = threading.Thread(target=boom, name="crashy")
    t.start()
    t.join()
    from utils import logger as log
    log._file_handler.flush()
    text = open(file_logging, encoding="utf-8").read()
    assert "Uncaught error in thread crashy" in text and "kaboom in a thread" in text


# ---- self-check ------------------------------------------------------------------------

def test_doctor_reports_ollama_down_with_the_fix(ollama_down):
    from core import doctor
    results = doctor.run_checks(settings={"ai_model": "qwen2.5:3b"}, hardware=False)
    ollama = next(r for r in results if r.area == "Ollama")
    assert ollama.status == doctor.FAIL and "ollama serve" in ollama.fix
    text = doctor.report(results)
    text.encode("ascii")  # prints in any Windows console
    assert "[FAIL] Ollama" in text and "-> Start Ollama" in text
    assert "problem" in doctor.summary(results)


def test_doctor_names_missing_models_and_packages(monkeypatch, fake_ollama):
    from core import ai_engine, doctor
    monkeypatch.setitem(ai_engine._health, "models", {"qwen2.5:3b"})
    monkeypatch.setattr(ai_engine, "ollama_available", lambda: True)
    monkeypatch.setitem(ai_engine._health, "ok", True)
    monkeypatch.setattr(doctor, "PACKAGES", [("not-a-real-package", "not_a_real_module_xyz", "nothing", False)])
    results = doctor.run_checks(settings={"ai_model": "qwen2.5:3b", "smart_model": "qwen2.5:7b"}, hardware=False)
    by_area = {r.area: r for r in results}
    assert by_area["AI model"].status == doctor.OK
    assert by_area["Chat model"].status == doctor.WARN and by_area["Chat model"].fix == "ollama pull qwen2.5:7b"
    assert by_area["Recall by meaning"].fix == "ollama pull nomic-embed-text"
    assert by_area["Package not-a-real-package"].fix == "pip install not-a-real-package"


def test_a_broken_check_does_not_break_the_report(monkeypatch):
    from core import doctor

    def explode():
        raise ValueError("oops")

    monkeypatch.setattr(doctor, "check_python", explode)
    results = doctor.run_checks(settings={}, hardware=False)
    assert results[0].area == "Python" and results[0].status == doctor.FAIL and "oops" in results[0].detail


def test_self_check_by_voice(monkeypatch):
    from core import doctor
    from core.command_router import route_command
    from core.dispatcher import dispatch_command
    monkeypatch.setattr(doctor, "run_checks", lambda: [doctor.Check("Ollama", doctor.OK, "running")])
    for phrase in ("run a self check", "is everything working?", "run diagnostics"):
        assert route_command(phrase) == "self check", phrase
    assert dispatch_command("self check").reply.startswith("All 1 checks passed")


def test_doctor_entry_point(monkeypatch, capsys):
    from core import doctor
    monkeypatch.setattr(doctor, "run_checks", lambda: [doctor.Check("Ollama", doctor.FAIL, "down", "start it")])
    import hina
    monkeypatch.setattr(sys, "argv", ["hina.py", "--doctor"])
    assert hina.main() == 1
    assert "[FAIL] Ollama" in capsys.readouterr().out
