import actions


class TestCalculate:
    def test_answer(self):
        assert "300" in actions.calculate("25*12")

    def test_whole_floats_print_as_ints(self):
        assert "The answer is 4 " in actions.calculate("8/2")

    def test_decimal(self):
        assert "3.5" in actions.calculate("(4+3)/2")

    def test_code_is_refused(self):
        assert "Invalid" in actions.calculate("__import__('os').system('calc')")

    def test_divide_by_zero(self):
        assert "Invalid" in actions.calculate("1/0")


class TestOpenApp:
    def test_known_app_launches(self, machine):
        reply = actions.open_app("chrome")
        assert reply.startswith("Opening chrome")

    def test_alias_launches(self, machine):
        assert actions.open_app("spotify").startswith("Opening")

    def test_empty_name(self, machine):
        assert "Which app" in actions.open_app("  ")

    def test_unknown_app_never_opens_a_random_file(self, machine, monkeypatch):
        import os
        monkeypatch.setattr(actions, "_search_files", lambda *a, **k: ["C:\\secret\\a.txt"])
        monkeypatch.setattr(os, "startfile", lambda p: (_ for _ in ()).throw(OSError("nope")), raising=False)
        reply = actions.open_app("zzz-not-an-app")
        assert "couldn't find" in reply.lower()
        assert machine.os_calls["startfile"] == []

    def test_injection_is_not_launched(self, machine):
        reply = actions.open_app("calc & del *")
        assert "ouldn't" in reply
        assert machine.os_calls["popen"] == [] and machine.os_calls["startfile"] == []


class TestCloseRestart:
    def test_close_runs_taskkill_without_shell(self, machine):
        assert actions.close_app("spotify").startswith("Closing")
        assert machine.os_calls["run"][-1] == ["taskkill", "/IM", "Spotify.exe", "/F"]

    def test_close_reports_failure(self, machine, monkeypatch):
        monkeypatch.setattr(actions, "kill_process", lambda name: (False, "nope"))
        assert "Couldn't close" in actions.close_app("spotify")

    def test_close_protected_process(self, machine):
        assert "Couldn't close" in actions.close_app("explorer")
        assert machine.os_calls["run"] == []

    def test_restart_closes_then_opens(self, machine, monkeypatch):
        monkeypatch.setattr(actions.time, "sleep", lambda s: None)
        reply = actions.restart_app("chrome")
        assert machine.os_calls["run"], "close step did not run"
        assert reply.startswith("Opening")


class TestFiles:
    def test_find_file_hit(self, monkeypatch):
        monkeypatch.setattr(actions, "_search_files", lambda name, want="file", **k: ["C:\\d\\notes.txt"])
        assert "C:\\d\\notes.txt" in actions.find_file("notes.txt")

    def test_find_file_miss(self, monkeypatch):
        monkeypatch.setattr(actions, "_search_files", lambda *a, **k: [])
        assert actions.find_file("x") == "File not found 🌸"

    def test_find_folder_hit_and_miss(self, monkeypatch):
        monkeypatch.setattr(actions, "_search_files", lambda name, want="file", **k: ["C:\\Downloads"] if want == "folder" else [])
        assert "C:\\Downloads" in actions.find_folder("downloads")
        monkeypatch.setattr(actions, "_search_files", lambda *a, **k: [])
        assert actions.find_folder("x") == "Folder not found 🌸"

    def test_search_and_open_file_opens_best_hit(self, machine, monkeypatch):
        monkeypatch.setattr(actions, "_search_files", lambda *a, **k: ["C:\\d\\notes.txt", "C:\\d\\other.txt"])
        assert "notes.txt" in actions.search_and_open_file("notes")
        assert machine.os_calls["startfile"] == ["C:\\d\\notes.txt"]

    def test_search_and_open_file_miss(self, machine, monkeypatch):
        monkeypatch.setattr(actions, "_search_files", lambda *a, **k: [])
        assert actions.search_and_open_file("x") == "File not found 🌸"
        assert machine.os_calls["startfile"] == []


class TestSystemInfo:
    def test_time_and_date_shapes(self):
        assert actions.tell_time().startswith("The time is ")
        assert actions.tell_date().startswith("Today's date is ")

    def test_battery_variants(self, monkeypatch):
        class Batt:
            percent = 80
            power_plugged = True

        fake = type("P", (), {"sensors_battery": staticmethod(lambda: Batt())})
        monkeypatch.setattr(actions, "psutil", fake)
        monkeypatch.setattr(actions, "_HAS_PSUTIL", True)
        assert "80%" in actions.battery_status() and "charging" in actions.battery_status()

        fake.sensors_battery = staticmethod(lambda: None)
        assert "not available" in actions.battery_status()

        monkeypatch.setattr(actions, "_HAS_PSUTIL", False)
        assert "not available" in actions.battery_status()

    def test_disk_usage(self, monkeypatch):
        gb = 1024 ** 3

        class Disk:
            free = 50 * gb
            total = 200 * gb

        fake = type("P", (), {"disk_usage": staticmethod(lambda path: Disk())})
        monkeypatch.setattr(actions, "psutil", fake)
        monkeypatch.setattr(actions, "_HAS_PSUTIL", True)
        assert "50.0 GB free out of 200.0 GB" in actions.disk_usage()


class TestWebSearch:
    def test_google(self, machine):
        assert "Searching Google" in actions.search_google("cute cats & dogs")
        assert machine.browser == ["https://www.google.com/search?q=cute%20cats%20%26%20dogs"]

    def test_chatgpt(self, machine):
        assert "ChatGPT" in actions.search_chatgpt("hi there")
        assert machine.browser[0].startswith("https://chatgpt.com/?q=hi%20there")

    def test_empty_queries_open_nothing(self, machine):
        assert "provide a search query" in actions.search_google("  ")
        assert "provide a search query" in actions.search_chatgpt("")
        assert machine.browser == []


class TestTimers:
    def test_set_and_cancel(self, monkeypatch):
        monkeypatch.setattr(actions.time, "sleep", lambda s: None)
        assert "Timer set for 5 seconds" in actions.set_timer(5)
        actions.timer_thread.join(timeout=2)
        assert "cancelled" in actions.cancel_timer()
        assert actions.timer_cancelled is True

    def test_countdown_runs_and_finishes(self, monkeypatch, capsys):
        monkeypatch.setattr(actions.time, "sleep", lambda s: None)
        assert actions.countdown(3) == "Done!"
        assert capsys.readouterr().out.count("Hina:") == 4
