import pytest

import memory
from core.dispatcher import dispatch_command


def reply(command, **kw):
    return dispatch_command(command, **kw).reply


class TestBasics:
    def test_ai_reply_passthrough(self):
        assert reply("ai_reply::Opened it 🌸") == "Opened it 🌸"

    @pytest.mark.parametrize("cmd", ["bye", "exit"])
    def test_exit(self, cmd):
        result = dispatch_command(cmd)
        assert result.should_exit and result.exit_delay_ms > 0 and result.reply

    def test_unknown_command_gets_friendly_reply(self):
        assert reply("zzz") != ""

    @pytest.mark.parametrize("cmd", [
        "hello", "how are you", "who are you", "thanks", "what can you do",
        "what do you think", "im tired", "tell me something",
    ])
    def test_small_talk_always_replies(self, cmd):
        assert reply(cmd)

    def test_time_date(self):
        assert "time" in reply("tell time").lower()
        assert "date" in reply("tell date").lower()


class TestApps:
    def test_open_records_recent_app_and_replies(self, machine):
        text = reply("open chrome")
        assert "chrome" in text.lower()
        assert memory.get_recent_apps()[0] == "chrome"

    def test_open_resolves_favourite(self, machine):
        memory.set_favorite_app("browser", "chrome")
        reply("open browser")
        assert memory.get_recent_apps()[0] == "chrome"

    def test_failed_open_is_not_reported_as_success(self, machine):
        text = reply("open calc & del *")
        assert "ouldn't" in text
        assert memory.get_recent_apps() == []

    def test_close_success_and_failure(self, machine):
        assert "Should I" in reply("close spotify")
        assert machine.os_calls["run"] == []
        assert reply("confirm yes")
        assert machine.os_calls["run"][-1][:3] == ["taskkill", "/IM", "Spotify.exe"]
        reply("close explorer")
        assert "Couldn't close" in reply("confirm yes")

    def test_restart(self, machine, monkeypatch):
        import actions
        monkeypatch.setattr(actions.time, "sleep", lambda s: None)
        assert "Should I" in reply("restart chrome")
        assert reply("confirm yes")

    def test_mode(self, machine):
        assert reply("mode coding")
        assert "not found" in reply("mode gaming")


class TestFiles:
    def test_find_file_is_handled(self, monkeypatch):
        import actions
        monkeypatch.setattr(actions, "_search_files", lambda *a, **k: ["C:\\x\\notes.txt"])
        assert "notes.txt" in reply("find file notes")

    def test_find_folder(self, monkeypatch):
        import actions
        monkeypatch.setattr(actions, "_search_files", lambda *a, **k: ["C:\\Downloads"])
        assert "Downloads" in reply("find folder downloads")

    def test_open_file_records_recent_file(self, machine, monkeypatch):
        import actions
        monkeypatch.setattr(actions, "_search_files", lambda *a, **k: ["C:\\x\\notes.txt"])
        assert "notes.txt" in reply("open file notes")
        assert memory.get_recent_files() == ["notes"]


class TestMemoryCommands:
    def test_set_name(self, machine):
        assert "Amy" in reply("set name amy".replace("amy", "Amy"))
        assert memory.get_name() == "Amy"

    def test_favourite_app_ok_and_usage(self, machine):
        assert "favorite browser" in reply("favorite app chrome as browser")
        assert "Use:" in reply("favorite app chrome")


class TestTimersCalc:
    def test_timer_valid_and_invalid(self, machine):
        assert "Timer set for 10" in reply("timer 10")
        assert "valid number" in reply("timer abc")
        reply("cancel timer")

    def test_cancel_timer(self):
        reply("timer 10")
        assert "cancelled" in reply("cancel timer")
        assert "No timer" in reply("cancel timer")

    def test_calculate_ok_and_hostile(self):
        assert "300" in reply("calculate 25*12")
        assert "Invalid" in reply("calculate __import__('os').system('x')")

    def test_countdown_invalid(self):
        assert "valid number" in reply("countdown x")

    def test_countdown_without_gui_does_nothing(self):
        assert dispatch_command("countdown 3").reply == ""

    def test_countdown_with_gui_starts_thread(self, monkeypatch):
        import tools.system as d
        started = []

        class T:
            def __init__(self, target, args, daemon): started.append(args)
            def start(self): pass

        monkeypatch.setattr(d.threading, "Thread", T)
        dispatch_command("countdown 3", output_var=object(), output_label=object(), app=object())
        assert started and started[0][0] == 3


class TestWeb:
    def test_searches(self, machine):
        assert "Google" in reply("search google cats")
        assert "ChatGPT" in reply("search chatgpt cats")
        assert len(machine.browser) == 2
