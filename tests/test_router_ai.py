"""Command routing + the Ollama paths (all against a fake Ollama)."""

import pytest

from core import ai_engine
from core.command_router import route_command
from core.dispatcher import dispatch_command


class TestRouterWithoutAI:
    def test_known_commands_never_call_ollama(self, fake_ollama):
        assert route_command("open chrome") == "open chrome"
        assert route_command("Tell Time") == "tell time"
        assert fake_ollama.requests == []

    def test_unknown_input_with_ollama_down_becomes_chat_with_a_canned_reply(self, ollama_down):
        assert route_command("Blorp the flarn") == "chat::Blorp the flarn"
        from core.conversation import UNKNOWN_REPLIES
        assert dispatch_command("chat::Blorp the flarn").reply in UNKNOWN_REPLIES

    def test_failure_is_recorded_in_context(self, ollama_down):
        from core.context_manager import context_manager
        route_command("blorp the flarn")
        assert "blorp the flarn" in context_manager.get_context()["recent_failures"]


class TestOllamaHealth:
    def test_down_is_detected_and_cached(self, monkeypatch):
        calls = []

        def get(url, timeout):
            calls.append(url)
            raise ai_engine.requests.ConnectionError("down")

        monkeypatch.setattr(ai_engine.requests, "get", get)
        assert ai_engine.ollama_available() is False
        assert ai_engine.ollama_available() is False
        assert len(calls) == 1, "failed health check must be cached"

    def test_up(self, monkeypatch):
        class R:
            def raise_for_status(self): pass
        monkeypatch.setattr(ai_engine.requests, "get", lambda url, timeout: R())
        assert ai_engine.ollama_available() is True

    def test_down_returns_none_without_posting(self, monkeypatch):
        monkeypatch.setattr(ai_engine, "ollama_available", lambda: False)
        monkeypatch.setattr(ai_engine.requests, "post", lambda *a, **k: pytest.fail("posted while down"))
        assert ai_engine.fallback_parse_command("anything") is None
        assert ai_engine.resolve_tool_call("anything") is None
        assert ai_engine.rewrite_action_reply("Opening x", "open_app", "x") == "Opening x"

    def test_request_failure_resets_health_cache(self, monkeypatch):
        monkeypatch.setattr(ai_engine, "ollama_available", lambda: True)

        def post(*a, **k):
            raise ai_engine.requests.Timeout("slow")

        monkeypatch.setattr(ai_engine.requests, "post", post)
        ai_engine._health["checked_at"] = 999.0
        assert ai_engine.fallback_parse_command("x") is None
        assert ai_engine._health["checked_at"] == 0.0


class TestPayloads:
    def test_generate_payload_is_non_streaming_with_options(self, fake_ollama):
        fake_ollama.generate_reply = "open chrome"
        ai_engine.fallback_parse_command("launch the browser")
        url, body = fake_ollama.requests[0]
        assert url.endswith("/api/generate")
        assert body["stream"] is False
        assert body["options"]["temperature"] == 0.0
        assert "temperature" not in body and "max_length" not in body

    def test_chat_payload(self, fake_ollama):
        ai_engine.resolve_tool_call("open chrome")
        url, body = fake_ollama.requests[0]
        assert url.endswith("/api/chat") and body["stream"] is False
        assert body["tools"] and body["options"]["temperature"] == 0.0

    def test_every_tool_schema_has_a_handler(self):
        names = {t["function"]["name"] for t in ai_engine.TOOLS}
        for name in names:
            # An unknown tool returns None; a known one must not.
            result = ai_engine._call_tool(name, {})
            assert result is not None or name in {"set_timer"}, name


class TestFallbackParse:
    def test_maps_text_to_command(self, fake_ollama):
        fake_ollama.generate_reply = "open chrome\nextra chatter"
        assert ai_engine.fallback_parse_command("launch the browser") == "open chrome"

    def test_unknown_gives_none(self, fake_ollama):
        fake_ollama.generate_reply = "UNKNOWN"
        assert ai_engine.fallback_parse_command("sing me a song") is None

    def test_router_uses_fallback_when_no_tool_call(self, fake_ollama):
        fake_ollama.tool_call = None
        fake_ollama.generate_reply = "tell time"
        assert route_command("what's the clock say") == "tell time"

    def test_router_rejects_fallback_that_is_not_a_known_command(self, fake_ollama):
        fake_ollama.generate_reply = "format c:"
        assert route_command("do something") == "chat::do something"


class TestToolCalling:
    def test_tool_call_executes_and_is_returned_as_ai_reply(self, fake_ollama, machine):
        fake_ollama.tool_call = ("open_app", {"name": "chrome"})
        fake_ollama.generate_reply = "Chrome is up 🌸"
        routed = route_command("could you fire up the browser")
        assert routed == "ai_reply::Chrome is up 🌸"
        assert dispatch_command(routed).reply == "Chrome is up 🌸"

    def test_tool_arguments_may_arrive_as_a_json_string(self, fake_ollama, machine):
        fake_ollama.tool_call = ("calculate", '{"expression": "6*7"}')
        fake_ollama.generate_reply = "It is 42 🌸"
        assert ai_engine.resolve_tool_call("six times seven") == "It is 42 🌸"

    def test_calculate_tool_is_safe(self, fake_ollama):
        fake_ollama.tool_call = ("calculate", {"expression": "__import__('os').system('calc')"})
        fake_ollama.generate_reply = "x"
        result = ai_engine._call_tool("calculate", {"expression": "__import__('os').system('calc')"})
        assert "Invalid" in result

    def test_close_tool_cannot_be_used_for_injection_or_system_processes(self, machine):
        from core import permissions
        ai_engine._call_tool("close_app", {"name": "x & shutdown /s"})
        assert "Couldn't" in permissions.resolve(True)
        ai_engine._call_tool("close_app", {"name": "explorer"})
        assert "Couldn't" in permissions.resolve(True)
        assert machine.os_calls["run"] == []

    def test_unknown_tool_name_is_ignored(self, fake_ollama):
        fake_ollama.tool_call = ("format_disk", {})
        assert ai_engine.resolve_tool_call("wipe it") is None

    def test_tool_that_raises_is_swallowed(self, monkeypatch):
        import actions
        monkeypatch.setattr(actions, "tell_time", lambda: (_ for _ in ()).throw(RuntimeError("x")))
        assert ai_engine._call_tool("tell_time", {}) is None

    def test_bad_seconds_argument_is_swallowed(self):
        assert ai_engine._call_tool("set_timer", {"seconds": "soon"}) is None


class TestRewrite:
    def test_rewrite_uses_first_line(self, fake_ollama):
        fake_ollama.generate_reply = "Opening x softly 🌸\nsecond line"
        assert ai_engine.rewrite_action_reply("Opening x", "open_app", "x") == "Opening x softly 🌸"

    def test_empty_rewrite_keeps_base(self, fake_ollama):
        fake_ollama.generate_reply = "   "
        assert ai_engine.rewrite_action_reply("Opening x", "open_app", "x") == "Opening x"

    def test_empty_base_untouched(self):
        assert ai_engine.rewrite_action_reply("", "open_app") == ""

    def test_generate_response_falls_back_to_template(self, ollama_down):
        from core.assistant import generate_response
        assert "chrome" in generate_response("open_app", "chrome").lower()


def test_blank_model_output_does_not_crash_fallback(fake_ollama):
    fake_ollama.generate_reply = "   "
    assert ai_engine.fallback_parse_command("x") is None


# --- Phase 1: multi-step tools, streaming, tiering, personality --------------

def test_multi_step_request_runs_every_tool_the_model_asks_for(fake_ollama, monkeypatch):
    import core.ai_engine as ai_engine
    calls = []
    monkeypatch.setattr(ai_engine, "_call_tool", lambda name, args: calls.append((name, args)) or f"{name} done.")
    script = iter([
        [("open_app", {"name": "spotify"})],
        [("set_timer", {"seconds": 1500})],
        [],
    ])

    def post(url, json=None, timeout=None, stream=False):
        class R:
            def raise_for_status(self): pass
            def json(self_):
                step = next(script)
                return {"message": {"tool_calls": [{"function": {"name": n, "arguments": a}} for n, a in step]}}
        return R()

    monkeypatch.setattr(ai_engine.requests, "post", post)
    reply = ai_engine.resolve_tool_call("open spotify and set a 25 minute timer")
    assert [c[0] for c in calls] == ["open_app", "set_timer"]
    assert reply == "open_app done. set_timer done."


def test_repeated_identical_tool_call_runs_once(fake_ollama, monkeypatch):
    import core.ai_engine as ai_engine
    calls = []
    monkeypatch.setattr(ai_engine, "_call_tool", lambda name, args: calls.append(name) or "ok.")
    monkeypatch.setattr(ai_engine, "rewrite_action_reply", lambda base, *a, **k: base)
    fake_ollama.tool_call = ("tell_time", {})
    ai_engine.resolve_tool_call("tell me the time and the time")
    assert calls == ["tell_time"]


def test_single_tool_call_does_not_make_a_second_request(fake_ollama, monkeypatch):
    import core.ai_engine as ai_engine
    monkeypatch.setattr(ai_engine, "_call_tool", lambda name, args: "ok.")
    monkeypatch.setattr(ai_engine, "rewrite_action_reply", lambda base, *a, **k: base)
    fake_ollama.tool_call = ("tell_time", {})
    ai_engine.resolve_tool_call("what time is it")
    assert len([r for r in fake_ollama.requests if r[0].endswith("/api/chat")]) == 1


def test_chat_streams_sentences_as_they_finish(fake_ollama):
    import core.ai_engine as ai_engine
    fake_ollama.chat_reply = "Good evening. All systems are running! Anything else?"
    heard = []
    reply = ai_engine.chat_reply("hello", {}, on_sentence=heard.append)
    assert heard == ["Good evening.", "All systems are running!", "Anything else?"]
    assert reply == "Good evening. All systems are running! Anything else?"
    assert fake_ollama.requests[-1][1]["stream"] is True


def test_chat_stream_skips_non_english_sentences(fake_ollama):
    import core.ai_engine as ai_engine
    fake_ollama.chat_reply = "Hello there. 你好吗 friend. Bye now."
    heard = []
    ai_engine.chat_reply("hello", {}, on_sentence=heard.append)
    assert all(not ai_engine.contains_cjk(s) for s in heard)


def test_conversation_passes_the_stream_sink(fake_ollama):
    from core import conversation
    fake_ollama.chat_reply = "First one. Second one."
    heard = []
    conversation.set_stream_sink(heard.append)
    assert conversation.chat_reply("tell me a story") == "First one. Second one."
    assert heard == ["First one.", "Second one."]


def test_chat_uses_the_bigger_model_only_when_installed(fake_ollama, monkeypatch):
    import core.ai_engine as ai_engine
    monkeypatch.setattr(ai_engine, "MODEL", "small:3b")
    monkeypatch.setattr(ai_engine, "CHAT_MODEL", "big:8b")
    monkeypatch.setitem(ai_engine._health, "models", {"small:3b", "big:8b"})
    assert ai_engine.chat_model() == "big:8b"
    monkeypatch.setitem(ai_engine._health, "models", {"small:3b"})
    assert ai_engine.chat_model() == "small:3b"
    monkeypatch.setattr(ai_engine, "CHAT_MODEL", "")
    assert ai_engine.chat_model() == "small:3b"


def test_personality_switch_is_saved_and_reaches_the_chat_prompt(fake_ollama):
    import core.ai_engine as ai_engine
    from core import personality_engine as pe
    from core.command_router import route_command
    from core.dispatcher import dispatch_command
    for text in ("be tsundere", "tsundere mode", "switch to tsundere", "set personality to tsundere"):
        pe.set_personality("calm")
        assert route_command(text) == "set personality tsundere", text
    assert "tsundere" in dispatch_command("set personality tsundere").reply.lower()
    assert pe.get_personality() == "tsundere"
    import memory
    assert memory.get_personality() == "tsundere"
    system = ai_engine.build_chat_messages("hi", {"personality": "tsundere"})[0]["content"]
    assert "tsundere" in system
    pe.CURRENT_PERSONALITY = None  # a restart reads it back from the profile
    assert pe.get_personality() == "tsundere"


def test_unknown_personality_and_be_phrases_are_not_hijacked():
    from parser import normalize_command
    assert not normalize_command("be quiet").startswith("set personality")
    assert not normalize_command("be there at 5").startswith("set personality")
    from core.dispatcher import dispatch_command
    assert "only know" in dispatch_command("set personality pirate").reply
