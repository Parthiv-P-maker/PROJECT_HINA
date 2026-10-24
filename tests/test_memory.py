import json

import memory


def test_missing_profile_loads_empty(machine):
    assert memory.load_profile() == {}


def test_name_roundtrip(machine):
    assert "Amy" in memory.set_name("Amy")
    assert memory.get_name() == "Amy"


def test_recent_apps_dedupe_order_and_cap(machine):
    for app in ["a", "b", "c"]:
        memory.add_recent_app(app)
    memory.add_recent_app("a")
    assert memory.get_recent_apps()[:3] == ["a", "c", "b"]
    for i in range(20):
        memory.add_recent_app(f"app{i}")
    assert len(memory.get_recent_apps()) == 10


def test_recent_files_cap(machine):
    for i in range(15):
        memory.add_recent_file(f"f{i}.txt")
    assert memory.get_recent_files()[0] == "f14.txt" and len(memory.get_recent_files()) == 10


def test_favorite_apps(machine):
    assert "chrome" in memory.set_favorite_app("browser", "chrome")
    assert memory.get_favorite_app("browser") == "chrome"
    assert memory.get_favorite_app("editor") is None


def test_corrupt_profile_does_not_crash(machine):
    machine.profile.write_text("{not json")
    assert memory.load_profile() == {}
    memory.set_name("Amy")
    assert json.loads(machine.profile.read_text())["name"] == "Amy"


def test_real_profile_path_is_absolute():
    import os
    from utils.constants import MEMORY_PROFILE_PATH
    assert os.path.isabs(MEMORY_PROFILE_PATH)
