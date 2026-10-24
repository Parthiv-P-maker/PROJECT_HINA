import json
import os

import pytest

from core import permissions
from core.command_router import route_command
from core.dispatcher import dispatch_command
from utils import action_log, file_search


def log_entries():
    path = action_log.log_path()
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as file:
        return [json.loads(line) for line in file]


def run(command):
    return dispatch_command(route_command(command))


class TestTiers:
    def test_tier_table(self):
        assert permissions.tier_of("open_app") == "safe"
        for name in ("close_app", "restart_app", "delete_file", "shutdown", "restart_computer"):
            assert permissions.tier_of(name) == "confirm"
        assert permissions.tier_of("run_shell") == "blocked"

    def test_unknown_actions_default_to_confirm(self):
        assert permissions.tier_of("something_new") == "confirm"

    def test_blocked_never_runs(self):
        calls = []
        reply = permissions.run_action("run_shell", "dir", lambda: calls.append(1))
        assert calls == [] and "not allowed" in reply
        assert log_entries()[-1]["outcome"] == "blocked"

    def test_safe_runs_immediately(self):
        assert permissions.run_action("open_app", "x", lambda: "done") == "done"
        assert not permissions.has_pending()


class TestConfirmFlow:
    def test_close_asks_first_and_runs_nothing(self, machine):
        result = run("close spotify")
        assert "Should I close spotify" in result.reply
        assert result.needs_confirmation
        assert machine.os_calls["run"] == []

    def test_yes_runs_it(self, machine):
        run("close spotify")
        result = run("yes")
        assert machine.os_calls["run"] == [["taskkill", "/IM", "Spotify.exe", "/F"]]
        assert not result.needs_confirmation
        assert not permissions.has_pending()

    @pytest.mark.parametrize("word", ["Yes.", "yeah", "sure!", "go ahead", "Y"])
    def test_spoken_yes_variants(self, machine, word):
        run("close spotify")
        run(word)
        assert len(machine.os_calls["run"]) == 1

    @pytest.mark.parametrize("word", ["no", "No.", "nope", "cancel", "don't"])
    def test_no_variants_cancel(self, machine, word):
        run("close spotify")
        assert "won't" in run(word).reply
        assert machine.os_calls["run"] == []

    def test_other_command_drops_pending(self, machine):
        run("close spotify")
        run("tell time")
        assert not permissions.has_pending()
        run("yes")  # nothing is waiting any more (goes to normal routing)
        assert machine.os_calls["run"] == []

    def test_yes_with_nothing_pending_does_not_act(self, machine):
        assert "nothing waiting" in permissions.resolve(True)
        assert machine.os_calls["run"] == []

    def test_confirmation_expires(self, machine, monkeypatch):
        run("close spotify")
        real = permissions.time.time
        monkeypatch.setattr(permissions.time, "time", lambda: real() + 3600)
        assert not permissions.has_pending()
        assert "timed out" in permissions.resolve(True)
        assert machine.os_calls["run"] == []

    def test_restart_needs_confirmation(self, machine, monkeypatch):
        import actions
        monkeypatch.setattr(actions.time, "sleep", lambda s: None)
        assert run("restart chrome").needs_confirmation
        assert machine.os_calls["run"] == [] and machine.os_calls["popen"] == []

    def test_ai_tool_call_close_is_also_gated(self, fake_ollama, machine):
        fake_ollama.tool_call = ("close_app", {"name": "spotify"})
        fake_ollama.generate_reply = "SHOULD NOT BE USED"
        result = run("could you shut the music app")
        assert "Should I close spotify" in result.reply and result.needs_confirmation
        assert machine.os_calls["run"] == []
        run("yes")
        assert len(machine.os_calls["run"]) == 1

    def test_safe_commands_need_no_confirmation(self, machine):
        result = run("open notepad")
        assert not result.needs_confirmation


class TestActionLog:
    def test_confirm_flow_is_logged(self, machine):
        run("close spotify")
        run("yes")
        outcomes = [(e["action"], e["target"], e["outcome"]) for e in log_entries()]
        assert outcomes == [("close_app", "spotify", "asked"), ("close_app", "spotify", "ok")]
        assert all("time" in e for e in log_entries())

    def test_declined_logged(self, machine):
        run("close spotify")
        run("no")
        assert log_entries()[-1]["outcome"] == "declined"

    def test_failure_logged(self, machine):
        run("close explorer")
        run("yes")
        assert log_entries()[-1]["outcome"] == "failed"

    def test_safe_actions_logged(self, machine):
        run("open notepad")
        assert log_entries()[-1]["action"] == "open_app"

    def test_log_write_failure_never_breaks_action(self, monkeypatch):
        monkeypatch.setattr(action_log, "log_path", lambda: os.path.join("Z:\nope", "x", "log"))
        assert permissions.run_action("open_app", "x", lambda: "fine") == "fine"


class TestSearchScope:
    def test_default_roots_are_limited_to_user_folders(self, tmp_path, monkeypatch):
        for name in ("Desktop", "Documents", "Downloads", "Pictures", "Projects"):
            (tmp_path / name).mkdir()
        monkeypatch.setattr(file_search.Path, "home", classmethod(lambda cls: tmp_path))
        names = {r.name for r in file_search.search_roots()}
        assert names == {"Desktop", "Documents", "Downloads"}

    def test_configured_project_folders_included(self, tmp_path, monkeypatch):
        proj = tmp_path / "myproj"
        proj.mkdir()
        monkeypatch.setattr(file_search.Path, "home", classmethod(lambda cls: tmp_path / "nohome"))
        from utils.paths import user_data_dir
        with open(os.path.join(user_data_dir(), "search_folders.txt"), "w") as f:
            f.write(f"# comment\n{proj}\n")
        assert [str(r) for r in file_search.search_roots()] == [str(proj)]

    def test_find_file_handler_end_to_end(self, tmp_path, monkeypatch):
        (tmp_path / "plan.txt").write_text("x")
        monkeypatch.setattr(file_search, "search_roots", lambda: [tmp_path])
        assert "plan.txt" in run("find file plan.txt").reply
        assert "plan.txt" in run("find my plan.txt").reply

    def test_results_capped(self, tmp_path, monkeypatch):
        for i in range(20):
            (tmp_path / f"a{i}.txt").write_text("x")
        monkeypatch.setattr(file_search, "search_roots", lambda: [tmp_path])
        assert len(file_search.search("a", limit=5)) == 5
