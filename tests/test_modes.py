import json

import pytest

from core import mode_manager


@pytest.fixture
def modes_file(tmp_path, monkeypatch):
    def write(data):
        path = tmp_path / "modes.json"
        path.write_text(json.dumps(data))
        monkeypatch.setattr(mode_manager, "_MODE_FILE", path)
        return path
    return write


def test_shipped_modes_json_is_valid():
    modes = mode_manager.load_modes()
    assert {"coding", "study", "research"} <= set(modes)


@pytest.mark.parametrize("bad", [[], {"m": []}, {"m": {}}, {"m": {"apps": "x"}},
                                 {"m": {"apps": [1]}}, {"m": {"apps": [], "folders": "x"}},
                                 {"m": {"apps": [], "folders": [1]}}])
def test_validation_rejects_bad_config(bad):
    with pytest.raises(ValueError):
        mode_manager.validate_modes(bad)


def test_launch_mode_success(machine, modes_file, tmp_path):
    folder = tmp_path / "work"
    folder.mkdir()
    modes_file({"coding": {"apps": ["notepad"], "folders": [str(folder)]}})
    assert mode_manager.launch_mode("coding") == "Coding workspace ready 🌸"
    assert str(folder) in machine.os_calls["startfile"]


def test_launch_mode_unknown(modes_file):
    modes_file({"coding": {"apps": []}})
    assert "not found" in mode_manager.launch_mode("gaming")


def test_launch_mode_missing_folder_reports_issues(machine, modes_file):
    modes_file({"study": {"apps": [], "folders": ["Z:\\definitely\\not\\here"]}})
    assert "some issues" in mode_manager.launch_mode("study")


def test_launch_mode_empty_name_and_bad_file(machine, monkeypatch, tmp_path):
    assert "specify" in mode_manager.launch_mode("")
    monkeypatch.setattr(mode_manager, "_MODE_FILE", tmp_path / "missing.json")
    assert "could not be loaded" in mode_manager.launch_mode("coding")


def test_mode_apps_never_use_a_shell(machine, modes_file):
    modes_file({"x": {"apps": ["calc & del *"]}})
    mode_manager.launch_mode("x")
    assert machine.os_calls["popen"] == [] and machine.os_calls["startfile"] == []
