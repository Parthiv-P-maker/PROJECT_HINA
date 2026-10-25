"""The tool registry is the single source of truth: everything it declares must show up
in the parser, the Ollama schema, the router and the dispatcher."""

import pytest

from core import ai_engine, permissions
from core.command_router import KNOWN_COMMAND_PREFIXES, _is_known_command
from core.dispatcher import dispatch_command
from tools import registry

TOOLS = registry.all_tools()
SAMPLE_ARG = "5"  # a valid argument for every tool that takes one


def _sample(entry):
    return entry.command + SAMPLE_ARG if entry.takes_arg else entry.command


def test_registry_is_not_empty_and_names_are_unique():
    names = [t.name for t in TOOLS]
    assert len(names) == len(set(names)) > 20


def test_duplicate_registration_is_rejected():
    with pytest.raises(ValueError):
        registry.tool("tell_time", "dup", command="x")(lambda: "")


@pytest.mark.parametrize("entry", [t for t in TOOLS if t.ai], ids=lambda t: t.name)
def test_ai_tools_are_in_the_schema_and_callable(entry):
    schema = {t["function"]["name"]: t for t in ai_engine.TOOLS}
    assert entry.name in schema
    assert schema[entry.name] == entry.schema()
    assert ai_engine._call_tool(entry.name, {"seconds": 5}) is not None


def test_schema_only_contains_registered_ai_tools():
    registered = {t.name for t in TOOLS if t.ai}
    assert {t["function"]["name"] for t in ai_engine.TOOLS} == registered


@pytest.mark.parametrize("entry", TOOLS, ids=lambda t: t.name)
def test_every_tool_is_routable_and_dispatchable(entry, machine):
    for command in (_sample(entry), *entry.aliases):
        assert registry.find_for_command(command) is entry
        assert _is_known_command(command) == entry.router
    assert (entry.command in KNOWN_COMMAND_PREFIXES) == entry.router
    assert (entry.command in ai_engine.KNOWN_NORMALIZED_COMMANDS) == entry.prompt


@pytest.mark.parametrize("entry", [t for t in TOOLS if t.router], ids=lambda t: t.name)
def test_known_commands_never_fall_through_to_the_unknown_reply(entry, machine):
    result = dispatch_command(_sample(entry))
    assert result.reply or entry.name in {"countdown", "stop_speaking"}  # silent on purpose
    if entry.name != "quick_answer":  # offline, a lookup falls back to chat, which may not know either
        assert "don't know that one" not in result.reply


@pytest.mark.parametrize("entry", TOOLS, ids=lambda t: t.name)
def test_tier_comes_from_the_registry(entry):
    assert permissions.tier_of(entry.name) == entry.tier


def test_confirm_tier_tools_ask_before_acting(machine):
    from core import memory_store
    memory_store.add_list_item("notepad", "something")  # clearing an empty list has nothing to ask about
    from core import mode_manager
    mode_manager.save_modes({**mode_manager.load_modes(), "notepad": {"apps": ["notepad"]}})
    for entry in TOOLS:
        if entry.tier == registry.CONFIRM:
            result = dispatch_command(entry.command + "notepad" if entry.takes_arg else entry.command)
            assert result.needs_confirmation, entry.name
            permissions.cancel_pending()


def test_unknown_command_gets_the_fallback_reply():
    assert registry.dispatch("definitely not a command") is None
    assert dispatch_command("definitely not a command").reply


def test_exit_is_known_to_the_router():
    # the original bug: bye/exit were not in the router's list
    assert _is_known_command("bye") and _is_known_command("exit")
