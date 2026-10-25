"""Reminders (roadmap 3.4) and lists / to-dos (roadmap 3.9)."""

import re

from core import memory_store, permissions, reminders
from tools.registry import CONFIRM, Param, ask_or_reply, tool
from utils.when import parse_when

# =========================
# REMINDERS
# =========================

_REMIND = re.compile(r"^(?:remind me|set (?:a )?reminder|add (?:a )?reminder|create (?:a )?reminder)\b[ ,:]*(.*)$")
_LEADING = re.compile(r"^(?:to|that|about|for|of|i need to|i have to)\s+")


def _parse_remind(text):
    match = _REMIND.match(text.strip())
    return "remind me " + match.group(1).strip() if match else None


def _what(rest):
    """The thing to be reminded of, and whether it was said as "to <do something>"."""
    rest = re.sub(r"\s+", " ", rest).strip(" ,.!?")
    said_to = False
    while True:  # "for to submit" -> "submit"
        match = _LEADING.match(rest)
        if not match:
            return rest, said_to
        said_to = said_to or match.group(0).strip() in ("to", "i need to", "i have to")
        rest = rest[match.end():]


@tool("set_reminder", "Remind the user about something at a time, e.g. 'at 6pm to call mom' or "
                      "'in 20 minutes to stretch'. Reminders survive restarts.",
      {"request": Param("When and what, in the user's words, e.g. 'tomorrow at 9 to submit the form'")},
      command="remind me ", parse=_parse_remind, ai=True, priority=5)
def set_reminder(ctx):
    due, rest = parse_when(ctx.arg)
    what, said_to = _what(rest)
    if due is None:
        return "When should I remind you? Try \"remind me at 6 to call mom\" or \"in 10 minutes\" 🔔"
    if not what:
        return "What should I remind you about? 🔔"
    ctx.run(what, lambda: reminders.add(due, what))
    return f"Okay, I'll remind you {reminders.when_text(due)}{' to ' if said_to else ': '}{what} 🔔"


_LIST_REMINDERS = {"list reminders", "show reminders", "my reminders", "reminders", "what are my reminders",
                   "what reminders do i have", "do i have any reminders", "show my reminders",
                   "any reminders"}


@tool("list_reminders", "Tell the user which reminders are coming up.", command="list reminders",
      parse=lambda t: "list reminders" if t.rstrip("?.! ") in _LIST_REMINDERS else None,
      ai=True, priority=5)
def list_reminders():
    upcoming = reminders.pending()
    if not upcoming:
        return "No reminders coming up 🔔"
    parts = [f"{reminders.when_text(due)}: {text}" for _, due, text in upcoming[:8]]
    more = f" (and {len(upcoming) - 8} more)" if len(upcoming) > 8 else ""
    return "Coming up: " + "; ".join(parts) + more + " 🔔"


_CANCEL = re.compile(r"^(?:cancel|delete|remove|clear|forget)(?: (?:all|my|the|every))* reminders?(?: (?:about|for|to))?\s*(.*)$")


def _parse_cancel(text):
    match = _CANCEL.match(text.rstrip("?.! "))
    if not match:
        return None
    what = match.group(1).strip()
    if not what and re.search(r"\b(all|every)\b|reminders$", text.rstrip("?.! ")):
        what = "all"
    return "cancel reminder " + what if what else "cancel reminder "


@tool("cancel_reminder", "Cancel reminders whose text matches some words, or 'all'.",
      {"what": Param("Words from the reminder, or 'all'")},
      command="cancel reminder ", parse=_parse_cancel, ai=True, priority=5)
def cancel_reminder(ctx):
    what = ctx.arg.strip().lower()
    upcoming = reminders.pending()
    if not upcoming:
        return "There are no reminders to cancel 🔔"
    if what == "all":
        picked = upcoming
    elif what:
        words = set(memory_store.keywords(what))
        picked = [r for r in upcoming if words and words <= memory_store.keywords(r[2])] or \
                 [r for r in upcoming if what in r[2].lower()]
    elif len(upcoming) == 1:
        picked = upcoming
    else:
        return "Which one? Say \"cancel reminder about ...\" or \"cancel all reminders\" 🔔"
    if not picked:
        return f"I don't have a reminder about {what} 🔔"
    count = ctx.run(what or picked[0][2], lambda: reminders.cancel(r[0] for r in picked))
    if count == 1:
        return f"Cancelled the reminder: {picked[0][2]} 🔔"
    return f"Cancelled {count} reminders 🔔"


# =========================
# LISTS AND TO-DOS
# =========================

DEFAULT_LIST = "to-do"
_LIST_NAME = r"(?:my |the |our )?(?:(.+?) )?list"
_ADD = re.compile(r"^(?:add|put|write down|write) (.+?) (?:to|on|in|onto) " + _LIST_NAME + r"$")
_SHOW = re.compile(r"^(?:what(?:'s| is|s) (?:on|in) |show(?: me)? |read(?: me)? |check |open |tell me )" + _LIST_NAME + r"$")
_REMOVE = re.compile(r"^(?:remove|delete|take|cross off|cross|tick off|tick|strike) (.+?) (?:from|off) " + _LIST_NAME + r"$")
_CLEAR = re.compile(r"^(?:clear|empty|wipe|delete|reset) " + _LIST_NAME + r"$")
_ALL_LISTS = {"what lists do i have", "show my lists", "show me my lists", "what are my lists", "my lists", "list my lists", "show lists",
              "which lists do i have", "show all lists"}


def list_name(raw):
    name = re.sub(r"\s+", " ", (raw or "").strip().lower())
    if name in ("", "to do", "todo", "to-do", "task", "tasks", "things to do"):
        return DEFAULT_LIST
    return name


def _items(raw):
    """'milk, eggs and bread' -> ['milk', 'eggs', 'bread']."""
    parts = re.split(r",\s*(?:and\s+)?|\s+and\s+", raw.strip())
    return [p.strip(" .") for p in parts if p.strip(" .")]


def _parse_lists(text):
    text = text.rstrip("?.! ")
    if text in _ALL_LISTS:
        return "list all"
    match = _ADD.match(text)
    if match:
        return f"list add {list_name(match.group(2))}: {match.group(1)}"
    match = _REMOVE.match(text)
    if match:
        return f"list remove {list_name(match.group(2))}: {match.group(1)}"
    match = _SHOW.match(text)
    if match:
        return f"list show {list_name(match.group(1))}"
    match = _CLEAR.match(text)
    if match:
        return f"list clear {list_name(match.group(1))}"
    return None


def _split(arg):
    name, _, item = arg.partition(":")
    return list_name(name), item.strip()


def _the(name):
    return f"your {name} list"


@tool("list_add", "Add one or more items to one of the user's lists (to-do, shopping, ...).",
      {"spec": Param("'<list>: <items>', e.g. 'shopping: milk, eggs' or 'to-do: call the bank'")},
      command="list add ", parse=_parse_lists, ai=True, priority=5)
def list_add(ctx):
    name, raw = _split(ctx.arg)
    items = _items(raw)
    if not items:
        return "What should I add? Say \"add milk to my shopping list\" 📝"
    have = {i["text"].lower() for i in memory_store.list_items(name)}
    new = [i for i in items if i.lower() not in have]
    if not new:
        return f"{', '.join(items).capitalize()} {'is' if len(items) == 1 else 'are'} already on {_the(name)} 📝"
    ctx.run(f"{name}: {', '.join(new)}", lambda: [memory_store.add_list_item(name, i) for i in new])
    return f"Added {_join(new)} to {_the(name)} 📝"


def _join(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


@tool("list_show", "Read out one of the user's lists.",
      {"name": Param("The list, e.g. 'shopping' or 'to-do'")},
      command="list show ", ai=True, priority=5)
def list_show(ctx):
    name = list_name(ctx.arg)
    items = [i["text"] for i in memory_store.list_items(name)]
    if not items:
        return f"{_the(name).capitalize()} is empty 📝"
    return f"On {_the(name)}: {_join(items)} 📝"


@tool("list_remove", "Take items off one of the user's lists (when they're done or bought).",
      {"spec": Param("'<list>: <items>', e.g. 'shopping: milk'")},
      command="list remove ", ai=True, priority=5)
def list_remove(ctx):
    name, raw = _split(ctx.arg)
    current = memory_store.list_items(name)
    gone, missing = [], []
    for wanted in _items(raw):
        hit = next((i for i in current if i["text"].lower() == wanted.lower()), None) or \
              next((i for i in current if wanted.lower() in i["text"].lower()), None)
        if hit and hit not in gone:
            gone.append(hit)
        else:
            missing.append(wanted)
    if not gone:
        return f"I couldn't find {_join(missing) if missing else 'that'} on {_the(name)} 📝"
    ctx.run(f"{name}: {', '.join(i['text'] for i in gone)}",
            lambda: memory_store.delete_list_items(i["id"] for i in gone))
    reply = f"Took {_join([i['text'] for i in gone])} off {_the(name)}"
    if missing:
        reply += f" (no {_join(missing)} on it)"
    return reply + " 📝"


@tool("clear_list", "Remove everything from one of the user's lists.",
      {"name": Param("The list, e.g. 'shopping'")},
      command="list clear ", tier=CONFIRM, priority=5)
def clear_list(ctx):
    name = list_name(ctx.arg)
    items = memory_store.list_items(name)
    if not items:
        return f"{_the(name).capitalize()} is already empty 📝"
    ids = [i["id"] for i in items]
    return ask_or_reply(permissions.run_action(
        "clear_list", _the(name),
        lambda: f"Cleared {_the(name)} ({memory_store.delete_list_items(ids)} items) 📝"))


@tool("list_all", "Tell the user which lists they have.", command="list all", ai=True, priority=5)
def list_all():
    lists = memory_store.list_names()
    if not lists:
        return "You don't have any lists yet. Try \"add milk to my shopping list\" 📝"
    return "Your lists: " + ", ".join(f"{name} ({n})" for name, n in lists) + " 📝"
