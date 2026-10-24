"""Memory v2: safe profile store, SQLite history + rolling summary, chat mode, long-term facts."""

import json
import os
import threading

import pytest

import memory
from core import ai_engine, conversation, memory_store, permissions
from core.command_router import route_command
from core.dispatcher import dispatch_command
from ui_qt import settings as settings_mod


def run(text):
    return dispatch_command(route_command(text))


def set_private(on):
    settings_mod.save(dict(settings_mod.load(), private_mode=on))


def add_turns(n, start=0):
    for i in range(start, start + n):
        memory_store.record_turn(f"question {i}", f"answer {i}", memory_store.CHAT)


# ---- stage 1: profile store ------------------------------------------------

class TestProfileStore:
    def test_default_path_is_in_the_data_dir(self, monkeypatch, tmp_path):
        monkeypatch.setattr(memory, "PROFILE_PATH", None)
        monkeypatch.setattr(memory, "LEGACY_PROFILE_PATH", str(tmp_path / "nope.json"))
        assert memory.profile_path() == os.path.join(os.environ["HINA_DATA_DIR"], "user_profile.json")
        memory.set_name("Amy")
        assert json.load(open(memory.profile_path(), encoding="utf-8"))["name"] == "Amy"

    def test_legacy_profile_is_migrated_once(self, monkeypatch, tmp_path):
        legacy = tmp_path / "legacy.json"
        legacy.write_text(json.dumps({"name": "Parth", "recent_apps": ["chrome"]}))
        monkeypatch.setattr(memory, "PROFILE_PATH", None)
        monkeypatch.setattr(memory, "LEGACY_PROFILE_PATH", str(legacy))
        assert memory.get_name() == "Parth"
        assert memory.get_recent_apps() == ["chrome"]
        memory.set_name("Amy")
        legacy.write_text(json.dumps({"name": "Changed"}))  # never copied again
        assert memory.get_name() == "Amy"
        assert json.loads(legacy.read_text())["name"] == "Changed", "legacy file is left alone"

    def test_save_is_atomic_and_leaves_no_temp_files(self, machine):
        memory.set_name("Amy")
        folder = machine.profile.parent
        assert not [p for p in os.listdir(folder) if p.endswith(".tmp")]

    def test_failed_write_keeps_the_old_profile(self, machine, monkeypatch):
        memory.set_name("Amy")

        def broken_dump(*a, **k):
            raise OSError("disk full")

        monkeypatch.setattr(memory.json, "dump", broken_dump)
        with pytest.raises(OSError):
            memory.set_name("Bob")
        monkeypatch.undo()
        assert json.loads(machine.profile.read_text())["name"] == "Amy"
        assert not [p for p in os.listdir(machine.profile.parent) if p.endswith(".tmp")]

    def test_corrupt_file_is_backed_up_not_lost(self, machine, caplog):
        machine.profile.write_text("{not json")
        assert memory.load_profile() == {}
        backup = machine.profile.with_name(machine.profile.name + ".corrupt")
        assert backup.read_text() == "{not json"
        assert not machine.profile.exists()
        # a second corrupt file doesn't overwrite the first backup
        machine.profile.write_text("[1, 2]")
        assert memory.load_profile() == {}
        assert backup.read_text() == "{not json"
        assert len([p for p in os.listdir(machine.profile.parent) if p.endswith(".corrupt")]) == 2

    def test_concurrent_updates_are_not_lost(self, machine):
        threads = [threading.Thread(target=memory.add_recent_file, args=(f"f{i}",)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sorted(memory.get_recent_files()) == sorted(f"f{i}" for i in range(8))


# ---- stage 2: history ---------------------------------------------------------

class TestHistory:
    def test_turns_roundtrip_oldest_first(self):
        memory_store.record_turn("open chrome", "Opening chrome", memory_store.COMMAND)
        memory_store.record_turn("how's it going", "Splendid.", memory_store.CHAT)
        turns = memory_store.recent_turns(10)
        assert [(t["user"], t["reply"], t["kind"]) for t in turns] == [
            ("open chrome", "Opening chrome", "command"), ("how's it going", "Splendid.", "chat")]
        assert turns[0]["ts"] and os.path.exists(memory_store.db_path())
        assert os.path.dirname(memory_store.db_path()) == os.environ["HINA_DATA_DIR"]

    def test_recent_turns_limit_keeps_newest(self):
        add_turns(15)
        assert [t["user"] for t in memory_store.recent_turns(3)] == ["question 12", "question 13", "question 14"]

    def test_record_marks_chat_vs_command(self, ollama_down):
        conversation.record("tell time", "tell time", "It's noon")
        conversation.record("tell me a joke", "chat::tell me a joke", "No.")
        assert [t["kind"] for t in memory_store.recent_turns()] == ["command", "chat"]

    def test_private_mode_records_nothing(self):
        set_private(True)
        assert memory_store.record_turn("secret", "ok") is None
        assert memory_store.turn_count() == 0

    def test_clear_history(self):
        add_turns(3)
        memory_store.set_summary("old stuff", 2)
        memory_store.clear_history()
        assert memory_store.turn_count() == 0 and memory_store.get_summary() == ("", 0)

    def test_summary_folds_old_turns(self, fake_ollama):
        add_turns(conversation.KEEP_TURNS + conversation.SUMMARY_BATCH)
        fake_ollama.generate_reply = "The user asked many questions."
        assert conversation.maybe_summarise() is True
        text, upto = memory_store.get_summary()
        assert text == "The user asked many questions."
        prompt = fake_ollama.requests[-1][1]["prompt"]
        assert "question 0" in prompt and "question 9" in prompt and "question 10" not in prompt
        summary, history = conversation.prompt_history()
        assert [t["user"] for t in history][0] == "question 10" and len(history) == conversation.KEEP_TURNS

    def test_summary_waits_for_a_full_batch(self, fake_ollama):
        add_turns(conversation.KEEP_TURNS + conversation.SUMMARY_BATCH - 1)
        assert conversation.maybe_summarise() is False
        assert fake_ollama.requests == []

    def test_summary_without_ollama_degrades(self, ollama_down):
        add_turns(conversation.KEEP_TURNS + conversation.SUMMARY_BATCH)
        assert conversation.maybe_summarise() is False
        assert memory_store.get_summary() == ("", 0)
        # the prompt still gets the unsummarised turns, capped
        _, history = conversation.prompt_history()
        assert len(history) == conversation.MAX_PROMPT_TURNS

    def test_non_english_summary_is_discarded(self, fake_ollama):
        add_turns(conversation.KEEP_TURNS + conversation.SUMMARY_BATCH)
        fake_ollama.generate_reply = "用户问了很多问题"
        assert conversation.maybe_summarise() is False


# ---- stage 3: chat mode ---------------------------------------------------------

class TestChat:
    def test_unmatched_input_is_a_real_chat(self, fake_ollama, machine):
        memory.set_name("Parth")
        memory_store.record_turn("my favourite colour is teal", "Teal it is.", memory_store.CHAT)
        memory_store.add_fact("i play the violin")
        fake_ollama.chat_reply = "Hina: A fine question, Parth. Tea, I think."
        result = run("What should I drink?")
        assert result.reply == "A fine question, Parth. Tea, I think."
        url, body = fake_ollama.requests[-1]
        assert url.endswith("/api/chat") and "tools" not in body
        system, *rest = body["messages"]
        assert "J.A.R.V.I.S." in system["content"] and "Parth" in system["content"]
        assert "i play the violin" in system["content"]
        assert [m["content"] for m in rest] == ["my favourite colour is teal", "Teal it is.", "What should I drink?"]

    def test_tool_calling_still_comes_first(self, fake_ollama, machine):
        fake_ollama.tool_call = ("open_app", {"name": "chrome"})
        fake_ollama.generate_reply = "Opening chrome"
        assert route_command("could you fire up the browser").startswith("ai_reply::")

    def test_ollama_down_gives_a_canned_reply_without_posting(self, ollama_down, monkeypatch):
        monkeypatch.setattr(ai_engine.requests, "post", lambda *a, **k: pytest.fail("posted while down"))
        assert run("tell me about black holes").reply in conversation.UNKNOWN_REPLIES

    def test_non_english_chat_falls_back(self, fake_ollama):
        fake_ollama.chat_reply = "你好，我是Hina"
        assert run("say hi in chinese").reply in conversation.UNKNOWN_REPLIES

    def test_long_reply_is_trimmed_at_a_sentence(self, fake_ollama):
        fake_ollama.chat_reply = "First sentence. " * 60
        reply = run("ramble please").reply
        assert len(reply) <= ai_engine.MAX_CHAT_CHARS and reply.endswith(".")

    def test_unknown_name_says_so(self):
        messages = ai_engine.build_chat_messages("hi", {"name": ""}, [], "", [])
        assert "don't know the user's name" in messages[0]["content"]

    def test_known_commands_skip_chat(self, fake_ollama):
        assert route_command("tell time") == "tell time"
        assert fake_ollama.requests == []


# ---- stage 4: facts ---------------------------------------------------------------

class TestFacts:
    def test_remember_list_forget(self, machine):
        assert "Noted: I like jazz" in run("remember that i like jazz").reply
        assert "already" in run("Remember that I like jazz.").reply
        run("hina, remember that my sister is called maya")
        listed = run("what do you know about me?").reply
        assert "I like jazz" in listed and "my sister is called maya" in listed
        assert "Forgotten: I like jazz" in run("forget jazz").reply
        assert [f["text"] for f in memory_store.list_facts()] == ["my sister is called maya"]
        assert "don't have anything" in run("forget the moon").reply

    def test_list_includes_name_and_handles_empty(self, machine):
        assert "Nothing yet" in run("what do you know about me").reply
        memory.set_name("Parth")
        assert "your name is Parth" in run("what do you remember").reply

    def test_forgetting_several_needs_confirmation(self, machine):
        for fact in ("i like jazz", "jazz makes me calm", "i like tea"):
            memory_store.add_fact(fact)
        result = run("forget about jazz")
        assert result.needs_confirmation and "Should I forget 2 facts about jazz" in result.reply
        assert len(memory_store.list_facts()) == 3
        assert "Forgot 2 facts" in run("yes").reply
        assert [f["text"] for f in memory_store.list_facts()] == ["i like tea"]

    def test_forget_everything_can_be_declined(self, machine):
        memory_store.add_fact("i like tea")
        assert run("forget everything").needs_confirmation
        run("no")
        assert len(memory_store.list_facts()) == 1

    def test_forget_is_logged(self, machine):
        from utils.action_log import log_path
        memory_store.add_fact("i like tea")
        run("forget tea")
        log = [json.loads(line) for line in open(log_path(), encoding="utf-8")]
        assert any(e["action"] == "forget_fact" and e["outcome"] == "ok" for e in log)

    def test_private_mode_refuses_new_facts(self, machine):
        set_private(True)
        assert "Private mode" in run("remember that i like jazz").reply
        assert memory_store.list_facts() == []

    def test_model_can_remember_via_tool_call(self, fake_ollama, machine):
        fake_ollama.tool_call = ("remember_fact", {"fact": "my cat is called Miso"})
        fake_ollama.generate_reply = "UNKNOWN"
        run("by the way, my cat is called Miso")
        assert [f["text"] for f in memory_store.list_facts()] == ["my cat is called Miso"]
        assert memory_store.list_facts()[0]["source"] == "ai"

    def test_forget_is_not_exposed_to_the_model(self):
        assert "forget_fact" not in {t["function"]["name"] for t in ai_engine.TOOLS}
        assert permissions.tier_of("forget_facts") == permissions.CONFIRM

    def test_keyword_matching(self):
        assert memory_store.keywords("What do I like about my dogs?") == {"dog"}
        for i in range(10):
            memory_store.add_fact(f"filler fact number {i}")
        memory_store.add_fact("my dog is called Rex")
        assert [f["text"] for f in memory_store.relevant_facts("tell me about dogs")] == ["my dog is called Rex"]
        assert memory_store.relevant_facts("weather today") == []

    def test_few_facts_are_always_included(self):
        memory_store.add_fact("i like tea")
        assert [f["text"] for f in memory_store.relevant_facts("anything")] == ["i like tea"]


# ---- bugs found against real Qwen 2.5 3B ---------------------------------------------

class TestRealModelRegressions:
    def test_whats_my_name_answers_without_the_model(self, fake_ollama, machine):
        memory.set_name("Malu")
        fake_ollama.tool_call = ("set_name", {"name": "user"})  # what Qwen actually did
        assert run("What's my name?").reply == "You're Malu."
        assert memory.get_name() == "Malu" and fake_ollama.requests == []

    def test_set_name_is_not_a_model_tool_and_rejects_placeholders(self, machine):
        assert "set_name" not in {t["function"]["name"] for t in ai_engine.TOOLS}
        assert "What should I call you" in dispatch_command("set name user").reply
        assert memory.get_name() is None
        assert "Malu" in run("call me Malu").reply and memory.get_name() == "Malu"

    def test_names_and_facts_keep_their_capitals(self, machine):
        run("My name is Malu")
        run("Remember that I study computer science at VIT.")
        assert memory.get_name() == "Malu"
        assert memory_store.list_facts()[0]["text"] == "I study computer science at VIT"

    def test_remember_my_keeps_the_my(self, machine):
        assert "Noted: my birthday is on 3 March" in run("remember my birthday is on 3 March").reply

    @pytest.mark.parametrize("text", ["When is my birthday?", "what did I say about Friday?",
                                      "do you remember what I told you", "what do I study?"])
    def test_personal_questions_go_to_chat_not_tools(self, fake_ollama, text):
        memory_store.add_fact("I study computer science at VIT")
        fake_ollama.tool_call = ("tell_date", {})  # what Qwen actually did for the birthday question
        assert route_command(text) == "chat::" + text
        assert all(url.endswith("/api/chat") and "tools" not in body for url, body in fake_ollama.requests)

    @pytest.mark.parametrize("text", ["what time is it?", "how do I open chrome?", "what's my battery?"])
    def test_other_questions_still_try_tools(self, fake_ollama, text):
        fake_ollama.tool_call = ("tell_time", {})
        fake_ollama.generate_reply = "It is 3 o'clock"
        assert route_command(text).startswith("ai_reply::")

    def test_rewrite_that_adds_a_sentence_is_discarded(self, fake_ollama):
        fake_ollama.generate_reply = "It's 03:57 AM, sweetie. Your birthday is on March 3rd."
        assert ai_engine.rewrite_action_reply("The time is 03:57 AM", "tell_time") == "The time is 03:57 AM"

    def test_facts_are_quoted_as_the_users_words(self):
        messages = ai_engine.build_chat_messages("hi", {"name": "Malu"}, [], "", ["my birthday is on 3 March"])
        assert '"my birthday is on 3 March"' in messages[0]["content"]
