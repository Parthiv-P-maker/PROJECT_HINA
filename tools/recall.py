"""Chat mode and long-term facts: "remember that ...", "what do you know about me?", "forget ..."."""

import re

import memory
from core import conversation, memory_store, permissions
from tools.registry import Param, ask_or_reply, tool

_REMEMBER = ("remember that ", "remember: ", "dont forget that ", "don't forget that ")
_FORGET_ALL = {"everything", "all", "all facts", "everything you know", "everything about me",
               "everything you know about me", "all about me"}


@tool("chat", "Talk with the user: anything that isn't a tool goes to the model as conversation.",
      {"text": Param("What the user said")},
      command=conversation.CHAT_PREFIX, router=False, prompt=False, priority=90)
def chat(ctx):
    return conversation.chat_reply(ctx.arg)


def display(fact):
    """The stored words with a standalone "i" capitalised ("i like jazz" -> "I like jazz")."""
    return re.sub(r"\bi\b", "I", fact)


def _parse_remember(text):
    for prefix in _REMEMBER:
        if text.startswith(prefix):
            return "remember fact " + text[len(prefix):].strip()
    return None


@tool("remember_fact", "Remember a fact the user tells you about themselves for later conversations.",
      {"fact": Param("The fact, in the user's words, e.g. 'my sister is called Maya'")},
      command="remember fact ", parse=_parse_remember, ai=True, priority=5)
def remember_fact(ctx):
    fact = ctx.arg.strip().rstrip(".").strip()
    if not fact:
        return "What should I remember? Say \"remember that ...\"."
    if memory_store.is_private():
        return "Private mode is on, so I won't store that."
    known = {f["text"].lower() for f in memory_store.list_facts()}
    if fact.lower() in known:
        return f"I already have that: {display(fact)}."
    ctx.run(fact, lambda: memory_store.add_fact(fact, source="ai" if ctx.via_ai else "user"))
    return f"Noted: {display(fact)}."


_LIST_PHRASES = {"what do you know about me", "what do you remember", "what do you remember about me",
                 "what do you know", "list facts", "show facts", "show my facts"}


def _parse_list(text):
    return "list facts" if text.rstrip("?.! ") in _LIST_PHRASES else None


@tool("list_facts", "Tell the user everything Hina remembers about them.",
      command="list facts", parse=_parse_list, ai=True, priority=5)
def list_facts():
    facts = [display(f["text"]) for f in memory_store.list_facts()]
    name = memory.get_name()
    if name:
        facts.insert(0, f"your name is {name}")
    if not facts:
        return "Nothing yet. Say \"remember that ...\" and I'll keep it."
    return "Here's what I have: " + "; ".join(facts) + "."


def _parse_forget(text):
    if text.startswith("forget ") and not text.startswith("forget it"):
        what = re.sub(r"^(?:that|about)\s+", "", text[len("forget "):].strip())
        return "forget " + what
    return None


@tool("forget_fact", "Forget remembered facts that match some words.",
      {"what": Param("Words from the fact to forget")},
      command="forget ", parse=_parse_forget, priority=5)
def forget_fact(ctx):
    what = ctx.arg.strip().rstrip("?.!").strip()
    forget_all = what in _FORGET_ALL
    if forget_all:
        matches = memory_store.list_facts()
        if not matches:
            return "There's nothing to forget yet."
        label = "everything I know about you"
    else:
        matches = memory_store.find_facts(what)
        if not matches:
            return f"I don't have anything about {what or 'that'}."
        label = f"{len(matches)} facts about {what}"
    ids = [f["id"] for f in matches]
    if len(ids) == 1 and not forget_all:
        text = display(matches[0]["text"])
        ctx.run(text, lambda: memory_store.delete_facts(ids))
        return f"Forgotten: {text}."
    # Several at once is harder to undo: ask first (tier "confirm").
    return ask_or_reply(permissions.run_action(
        "forget_facts", label, lambda: f"Done. Forgot {memory_store.delete_facts(ids)} facts."))
