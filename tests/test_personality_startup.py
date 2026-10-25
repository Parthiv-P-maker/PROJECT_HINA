import pytest

from core import personality_engine as pe
from core.startup import build_goodbye_message, build_startup_message


def test_startup_greets_by_name():
    assert all("Amy" in build_startup_message("Amy") for _ in range(20))


def test_startup_without_name_and_goodbye():
    assert build_startup_message()
    assert build_goodbye_message()


@pytest.mark.parametrize("persona", ["calm", "tsundere"])
@pytest.mark.parametrize("action", ["open_app", "close_app", "restart_app", "unknown"])
def test_every_persona_has_every_reply(monkeypatch, persona, action):
    monkeypatch.setattr(pe, "CURRENT_PERSONALITY", persona)
    assert pe.generate_reply(action, "chrome")


def test_unknown_action_and_persona_fall_back(monkeypatch):
    assert pe.generate_reply("not_an_action", "x")
    monkeypatch.setattr(pe, "CURRENT_PERSONALITY", "nonexistent")
    assert pe.generate_reply("open_app", "x")


def test_target_is_formatted_in(monkeypatch):
    monkeypatch.setattr(pe, "CURRENT_PERSONALITY", "calm")
    assert all("chrome" in pe.generate_reply("close_app", "chrome") for _ in range(30))


def test_helpers():
    from utils.helpers import clean_text, try_parse_int
    assert clean_text("Hello 🌸 world") == "Hello world"
    assert clean_text("Café नमस्ते 👍🏽 ok") == "Café नमस्ते ok"  # other languages survive, emoji don't
    assert clean_text("29°C ❤️‍🔥") == "29 degrees C"
    assert try_parse_int("12") == 12 and try_parse_int("x") is None and try_parse_int(None, 5) == 5


def test_context_has_expected_keys():
    from core.context_manager import context_manager
    ctx = context_manager.get_context()
    assert {"user_name", "recent_apps", "recent_commands", "time_of_day", "personality", "emotional_tone"} <= set(ctx)
