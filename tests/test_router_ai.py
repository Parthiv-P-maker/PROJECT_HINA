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

    def test_unknown_input_with_ollama_down_falls_back_to_normalized(self, ollama_down):
        assert route_command("blorp the flarn") == "blorp the flarn"

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
        assert route_command("do something") == "do something"


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
