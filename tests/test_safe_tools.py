import pytest

from utils import launcher
from utils.safe_math import safe_eval


class TestSafeMath:
    @pytest.mark.parametrize("expr,expected", [
        ("25*12", 300), ("(4+3)/2", 3.5), ("-2**3", -8), ("10%4", 2),
        ("7//2", 3), ("+5", 5), ("1.5*2", 3.0), ("2**10", 1024),
    ])
    def test_valid(self, expr, expected):
        assert safe_eval(expr) == expected

    @pytest.mark.parametrize("expr", [
        '__import__("os").system("calc")', "open('x')", "().__class__", "lambda: 1",
        "[1,2]", "'a'*5", "True+1", "a+1", "2**99999", "1+", "", "   ", "9" * 300,
    ])
    def test_rejected(self, expr):
        with pytest.raises(ValueError):
            safe_eval(expr)

    def test_division_by_zero_raises(self):
        with pytest.raises(ZeroDivisionError):
            safe_eval("1/0")


class TestLauncherNames:
    @pytest.mark.parametrize("name", ["x & del *", "a | b", "a; b", "../evil", "x\ny", "a>b", "$(x)", "a" * 100])
    def test_unsafe_names_rejected(self, name):
        assert launcher.is_safe_name(name) is False
        assert launcher.process_name_for(name) is None

    @pytest.mark.parametrize("name", ["chrome", "vs code", "my-app_2", "Notepad++"])
    def test_safe_names_accepted(self, name):
        assert launcher.is_safe_name(name) is True

    @pytest.mark.parametrize("friendly,proc", [
        ("vscode", "Code.exe"), ("vs code", "Code.exe"), ("spotify", "Spotify.exe"),
        ("chrome", "chrome.exe"), ("unknownapp", "unknownapp.exe"), ("tool.exe", "tool.exe"),
    ])
    def test_process_mapping(self, friendly, proc):
        assert launcher.process_name_for(friendly) == proc


class TestKill:
    def test_kill_uses_arg_list_not_a_shell(self, machine):
        ok, _ = launcher.kill_process("vscode")
        assert ok
        assert machine.os_calls["run"] == [["taskkill", "/IM", "Code.exe", "/F"]]

    @pytest.mark.parametrize("name", ["explorer", "svchost", "winlogon", "csrss"])
    def test_system_processes_protected(self, machine, name):
        assert launcher.kill_process(name)[0] is False
        assert machine.os_calls["run"] == []

    def test_injection_attempt_runs_nothing(self, machine):
        assert launcher.kill_process("notepad & shutdown /s")[0] is False
        assert machine.os_calls["run"] == []

    def test_not_running_is_reported(self, monkeypatch, machine):
        class Fail:
            returncode = 128
            stdout = stderr = ""

        monkeypatch.setattr(launcher.subprocess, "run", lambda *a, **k: Fail())
        ok, error = launcher.kill_process("chrome")
        assert ok is False and "isn't running" in error


class TestLaunch:
    def test_existing_path_uses_startfile(self, machine, tmp_path):
        target = tmp_path / "thing.txt"
        target.write_text("x")
        assert launcher.launch(str(target)) == (True, "")
        assert machine.os_calls["startfile"] == [str(target)]

    def test_unsafe_name_not_launched(self, machine):
        ok, _ = launcher.launch("calc & del *")
        assert ok is False
        assert machine.os_calls["startfile"] == [] and machine.os_calls["popen"] == []

    def test_empty_target(self, machine):
        assert launcher.launch("")[0] is False

    def test_command_on_path_is_popen_with_list(self, machine, monkeypatch):
        monkeypatch.setattr(launcher.shutil, "which", lambda name: "C:\\Windows\\notepad.exe")
        assert launcher.launch("notepad")[0] is True
        assert machine.os_calls["popen"] == [["C:\\Windows\\notepad.exe"]]

    def test_os_error_is_reported_not_raised(self, machine, monkeypatch):
        monkeypatch.setattr(launcher.shutil, "which", lambda name: None)

        def boom(path):
            raise OSError("no such app")

        monkeypatch.setattr(launcher.os, "startfile", boom, raising=False)
        ok, error = launcher.launch("nothingatall")
        assert ok is False and "no such app" in error
