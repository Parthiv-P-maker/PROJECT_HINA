"""Rest of Phase 3: clipboard (3.5), windows (3.6), web info (3.7), files and documents (3.8),
modes by voice (3.10), code helper (3.12)."""

import os
import time
import zipfile
from datetime import datetime, timedelta

import pytest

from core import mode_manager
from core.command_router import route_command
from core.dispatcher import dispatch_command
from utils import documents, file_index, web_info


def say(text):
    return dispatch_command(route_command(text))


# ---- 3.5 clipboard / 3.12 code helper -----------------------------------------

def test_clipboard_needs_text(machine):
    assert "clipboard is empty" in say("summarise what i copied").reply
    assert "Copy the error" in say("explain this error").reply


def test_clipboard_without_the_model(machine, ollama_down):
    machine.clipboard["text"] = "some long text"
    assert "Ollama isn't answering" in say("summarise this").reply


def test_summarise_and_explain_send_the_clipboard_to_the_model(machine, fake_ollama):
    machine.clipboard["text"] = "Traceback: ZeroDivisionError at line 3"
    fake_ollama.chat_reply = "You divided by zero on line 3."
    assert say("explain this error").reply == "You divided by zero on line 3."
    sent = fake_ollama.requests[-1][1]["messages"]
    assert "senior developer" in sent[0]["content"] and "ZeroDivisionError" in sent[1]["content"]


def test_translate_and_fix_copy_the_result_back(machine, fake_ollama):
    machine.clipboard["text"] = "hello friend"
    fake_ollama.chat_reply = "bonjour l'ami"
    reply = say("translate this to french").reply
    assert "In French: bonjour l'ami" in reply and "copied" in reply
    assert machine.clipboard["text"] == "bonjour l'ami"
    machine.clipboard["text"] = "i has a apple"
    fake_ollama.chat_reply = "I have an apple."
    assert "Fixed and copied: I have an apple." in say("fix the grammar").reply
    assert machine.clipboard["text"] == "I have an apple."


def test_translation_into_japanese_is_not_filtered(machine, fake_ollama):
    machine.clipboard["text"] = "hello"
    fake_ollama.chat_reply = "こんにちは"
    assert "こんにちは" in say("translate this into japanese").reply


def test_read_clipboard(machine):
    machine.clipboard["text"] = "meeting at 5"
    assert say("what did i copy").reply == "You copied: meeting at 5 📋"


# ---- 3.6 windows --------------------------------------------------------------------

def test_switch_minimise_maximise_snap(machine):
    assert "Switched to chrome" in say("switch to chrome").reply
    assert "Switched to code" in say("go to vs code").reply
    assert "Minimised spotify" in say("minimise spotify").reply
    assert "Maximised chrome" in say("maximize chrome").reply
    assert "on the left" in say("snap chrome to the left").reply
    assert [c[0] for c in machine.windows] == ["focus", "focus", "minimise", "maximise", "snap"]
    assert machine.windows[-1][1][1] == "left"


def test_missing_window_and_list(machine):
    assert "notepad isn't open" in say("switch to notepad").reply
    assert say("what windows are open").reply == "Open: chrome, code, spotify 🪟"
    say("minimise everything")
    assert machine.windows[-1][0] == "minimise_all"


def test_focus_mode_asks_then_closes_distractions(machine, monkeypatch):
    from utils import launcher
    killed = []
    monkeypatch.setattr(launcher, "kill_process", lambda app: killed.append(app) or (True, ""))
    reply = say("start focus mode for 25 minutes")
    assert reply.needs_confirmation and "discord" in reply.reply
    assert not killed
    reply = say("yes").reply
    assert killed == ["discord"] and "25 minutes" in reply
    from core import timers
    timers.cancel()


# ---- 3.10 modes -----------------------------------------------------------------------

def test_editing_modes_by_voice_saves_to_the_user_folder(machine):
    assert "Added discord to coding mode" in say("add discord to my coding mode").reply
    assert "discord" in mode_manager.load_modes()["coding"]["apps"]
    assert mode_manager.user_modes_path().exists()
    assert "Created gaming mode with steam and discord" in say("create a mode called gaming with steam and discord").reply
    assert "Took steam out" in say("remove steam from gaming mode").reply
    assert "apps: discord" in say("what's in gaming mode").reply
    reply = say("delete the gaming mode")
    assert reply.needs_confirmation
    say("yes")
    assert "gaming" not in mode_manager.load_modes()


def test_mode_suggestion_learns_from_launches(machine):
    modes = mode_manager.load_modes()
    assert mode_manager.suggest_mode(hour=9, modes=modes)[0] == "study"  # a guess by name
    for _ in range(3):
        mode_manager.record_launch("research", hour=21)
    name, why = mode_manager.suggest_mode(hour=22, modes=modes)
    assert name == "research" and "usually" in why


# ---- 3.7 web info -------------------------------------------------------------------------

class _Resp:
    def __init__(self, data=None, content=b""):
        self._data, self.content = data, content

    def json(self):
        return self._data


def test_weather_uses_the_home_city(machine, monkeypatch):
    assert "Which city?" in say("what's the weather").reply
    assert "you're in Kochi" in say("my city is kochi").reply
    calls = []

    def fake_get(url, params=None, **k):
        calls.append(params)
        if "geocoding" in url:
            return _Resp({"results": [{"name": "Kochi", "country": "Japan", "country_code": "JP",
                                       "latitude": 33.5, "longitude": 133.5},
                                      {"name": "Kochi", "country": "India", "country_code": "IN",
                                       "latitude": 9.9, "longitude": 76.3}]})
        return _Resp({"current": {"temperature_2m": 29.4, "apparent_temperature": 34, "weather_code": 2},
                      "daily": {"temperature_2m_max": [31, 30], "temperature_2m_min": [24, 25],
                                "precipitation_probability_max": [70, 20], "weather_code": [61, 3]}})

    monkeypatch.setattr(web_info, "_get", fake_get)
    reply = say("how's the weather").reply
    assert reply.startswith("Kochi, India: 29°C and partly cloudy now") and "70% chance of rain" in reply
    assert calls[-1]["latitude"] == 9.9  # the Indian Kochi, not the Japanese one
    assert "tomorrow: overcast, 25 to 30°C" in say("weather tomorrow").reply
    assert "Unlikely: 20% chance of rain" in say("will it rain tomorrow").reply


def test_news_headlines(machine, monkeypatch):
    rss = (b"<rss><channel><item><title>Big story - The Hindu</title><source>The Hindu</source></item>"
           b"<item><title>Second</title></item></channel></rss>")
    seen = []
    monkeypatch.setattr(web_info, "_get", lambda url, params=None, **k: seen.append(params) or _Resp(content=rss))
    assert say("what's the news").reply == "Top headlines: Big story (The Hindu) | Second 📰"
    assert "Headlines about cricket" in say("cricket news").reply and seen[-1]["q"] == "cricket"


def test_quick_answer_and_its_fallback(machine, monkeypatch, ollama_down):
    monkeypatch.setattr(web_info, "wiki_summary", lambda q: ("Marie Curie", "Marie Curie was a physicist."))
    assert say("who is marie curie").reply == "Marie Curie was a physicist. (Wikipedia: Marie Curie) 📚"
    assert route_command("tell me about yourself") != "lookup yourself"

    def offline(q):
        raise web_info.WebError(web_info.OFFLINE)

    monkeypatch.setattr(web_info, "wiki_summary", offline)
    from core import conversation
    assert say("tell me about black holes").reply in conversation.UNKNOWN_REPLIES  # chat takes over


def test_page_text_extraction():
    parser = web_info._TextExtractor()
    parser.feed("<html><head><title>My Page</title><script>evil()</script></head><body><nav>Home About</nav>"
                "<p>This is the first real paragraph of the article text.</p><p>Short</p></body></html>")
    assert parser.title == "My Page"
    text = "".join(parser.parts)
    assert "first real paragraph" in text and "evil" not in text and "Home About" not in text


def test_summarise_page_uses_the_copied_link(machine, monkeypatch, fake_ollama):
    assert "Copy the page's address" in say("summarise this page").reply
    machine.clipboard["text"] = "https://example.com/post"
    monkeypatch.setattr(web_info, "page_text", lambda url: ("Post", "A long article about tests."))
    fake_ollama.chat_reply = "It is about tests."
    assert say("summarise this page").reply == "Post: It is about tests. 🌐"
    assert say("summarise what i copied").reply == "Post: It is about tests. 🌐"  # a copied link means its page


# ---- 3.8 files and documents ------------------------------------------------------------------

def _touch(folder, name, days_ago=0, text="x"):
    path = folder / name
    path.write_text(text)
    stamp = (datetime.now() - timedelta(days=days_ago)).timestamp()
    os.utime(path, (stamp, stamp))
    return path


def test_recent_files_by_type_and_day(machine):
    downloads = machine.files_root / "Downloads"
    downloads.mkdir()
    _touch(downloads, "old.pdf", days_ago=5)
    _touch(downloads, "invoice.pdf", days_ago=1)
    _touch(downloads, "photo.png", days_ago=1)
    _touch(machine.files_root, "notes.txt", days_ago=0)
    file_index.refresh()
    assert say("open the pdf i downloaded yesterday").reply.startswith("Opening invoice.pdf (yesterday)")
    assert machine.os_calls["startfile"][-1].endswith("invoice.pdf")
    assert "invoice.pdf" in say("what did i download").reply
    assert "I didn't find any PDFs from today" in say("open the pdf i downloaded today").reply
    assert "photo.png" in say("show my recent downloads").reply


def test_window_ranges():
    now = datetime(2026, 10, 28, 15, 0)  # a Wednesday
    since, until = file_index.window("yesterday", now)
    assert since == datetime(2026, 10, 27) and until == datetime(2026, 10, 28)
    assert file_index.window("this week", now)[0] == datetime(2026, 10, 26)


def _docx(path, paragraphs):
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", f"<w:document><w:body>{body}</w:body></w:document>")
    return path


def test_extract_pdf_docx_and_chunking(tmp_path):
    import fitz
    pdf_path = tmp_path / "report.pdf"
    with fitz.open() as pdf:
        for text in ("Intro page about budgets.", "The deadline is 5 March."):
            pdf.new_page().insert_text((72, 72), text)
        pdf.save(pdf_path)
    pages = documents.extract(str(pdf_path))
    assert [p for p, _ in pages] == [1, 2] and "deadline" in pages[1][1]
    docx = _docx(tmp_path / "notes.docx", ["Alpha &amp; beta", "Gamma"])
    assert documents.extract(str(docx))[0][1].split("\n")[:2] == ["Alpha & beta", "Gamma"]
    chunks = documents.chunk([(1, "word " * 600)])
    assert len(chunks) > 2 and all(len(c.text) <= documents.CHUNK_CHARS for c in chunks)
    with pytest.raises(documents.DocumentError):
        documents.extract(str(tmp_path / "song.mp3"))


def test_load_ask_summarise_close(machine, fake_ollama, tmp_path):
    import fitz
    path = machine.files_root / "budget report.pdf"
    with fitz.open() as pdf:
        pdf.new_page().insert_text((72, 72), "Overview of the plan.")
        pdf.new_page().insert_text((72, 72), "The submission deadline is 5 March.")
        pdf.save(path)
    file_index.refresh()
    assert "Loaded budget report.pdf (2 pages" in say("load my budget report").reply
    fake_ollama.chat_reply = "The deadline is 5 March (p. 2)."
    assert say("ask the document when is the deadline").reply == "The deadline is 5 March (p. 2). 📄"
    system = fake_ollama.requests[-1][1]["messages"][0]["content"]
    assert "[p. 2] The submission deadline" in system  # the page that matches the question is sent
    fake_ollama.chat_reply = "A plan with a deadline."
    assert "A plan with a deadline." in say("summarise the document").reply
    assert "budget report.pdf" in say("which document is loaded").reply
    assert "Closed" in say("close the document").reply
    assert "No document is open" in say("ask the document anything").reply


def test_unknown_document(machine):
    assert "couldn't find a document called nothing here" in say("load nothing here").reply
