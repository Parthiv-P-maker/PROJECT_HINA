"""The AI layer must never put Chinese (or other off-topic) text in front of the user or TTS."""

import pytest

from core import ai_engine
from core.command_router import route_command
from core.dispatcher import dispatch_command


CHINESE_REPLIES = [
    "晚安，朋友。晚上下播吧～✨",
    "晚安，已为您关闭Spotify 🌸",
    "Spotify を開きました",
    "스포티파이를 열었어요",
]


class TestRewriteGuard:
    @pytest.mark.parametrize("reply", CHINESE_REPLIES)
    def test_cjk_rewrite_falls_back_to_base(self, fake_ollama, reply):
        fake_ollama.generate_reply = reply
        base = "Opening spotify for you 🌸"
        assert ai_engine.rewrite_action_reply(base, "open_app", "spotify") == base

    def test_off_topic_rewrite_without_target_falls_back(self, fake_ollama):
        fake_ollama.generate_reply = "Good night, friend ✨"
        base = "Closing spotify 🌸"
        assert ai_engine.rewrite_action_reply(base, "close_app", "spotify") == base

    def test_rewrite_that_drops_numbers_falls_back(self, fake_ollama):
        fake_ollama.generate_reply = "Here you go 🌸"
        base = "The answer is 42 🌸"
        assert ai_engine.rewrite_action_reply(base, "calculate", "6*7") == base

    def test_overlong_rewrite_falls_back(self, fake_ollama):
        fake_ollama.generate_reply = "Opening spotify " + "la " * 80
        base = "Opening spotify 🌸"
        assert ai_engine.rewrite_action_reply(base, "open_app", "spotify") == base

    def test_good_english_rewrite_is_used(self, fake_ollama):
        fake_ollama.generate_reply = '"Spotify is ready for you ✨"'
        base = "Opening spotify 🌸"
        assert ai_engine.rewrite_action_reply(base, "open_app", "spotify") == "Spotify is ready for you ✨"

    def test_prompt_demands_english_and_low_temperature(self, fake_ollama):
        fake_ollama.generate_reply = "Opening spotify ✨"
        ai_engine.rewrite_action_reply("Opening spotify 🌸", "open_app", "spotify")
        _, body = fake_ollama.requests[0]
        assert "English only" in body["prompt"]
        assert body["options"]["temperature"] <= 0.1


class TestEndToEnd:
    def test_generate_response_never_returns_chinese(self, fake_ollama, monkeypatch):
        import core.ai_loader as ai_loader
        from core.assistant import generate_response
        monkeypatch.setattr(ai_loader, "get_ai_engine", lambda: ai_engine)
        monkeypatch.setattr("core.assistant.get_ai_engine", lambda: ai_engine)
        fake_ollama.generate_reply = CHINESE_REPLIES[0]
        reply = generate_response("open_app", "spotify")
        assert not ai_engine.contains_cjk(reply)
        assert "spotify" in reply.lower()

    def test_tool_call_reply_never_chinese(self, fake_ollama, machine):
        fake_ollama.tool_call = ("close_app", {"name": "spotify"})
        fake_ollama.generate_reply = CHINESE_REPLIES[1]
        routed = route_command("could you shut the music app")
        assert routed.startswith("ai_reply::")
        reply = dispatch_command(routed).reply
        assert reply and not ai_engine.contains_cjk(reply)

    def test_chinese_parser_output_is_rejected(self, fake_ollama):
        fake_ollama.generate_reply = "打开 spotify"
        assert ai_engine.fallback_parse_command("start the music") is None


def test_contains_cjk():
    assert ai_engine.contains_cjk("晚安")
    assert ai_engine.contains_cjk("ok～")
    assert not ai_engine.contains_cjk("Opening Spotify 🌸✨")
    assert not ai_engine.contains_cjk("")
