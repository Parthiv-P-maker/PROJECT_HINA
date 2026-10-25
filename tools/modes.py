"""Editing modes by voice and suggesting one (roadmap 3.10). Launching a mode is in tools/apps.py."""

import re

from core import mode_manager, permissions
from tools.registry import CONFIRM, Param, ask_or_reply, tool

_MODE = r"(?:my |the )?([a-z0-9][a-z0-9 _-]{0,30}?) mode"


def _name(raw):
    return re.sub(r"\s+", " ", (raw or "").strip().lower())


def _split_items(raw):
    parts = re.split(r",\s*(?:and\s+)?|\s+and\s+", (raw or "").strip())
    return [p.strip(" .") for p in parts if p.strip(" .")]


def _is_folder(item):
    return bool(re.match(r"^[a-z]:[\\/]", item, re.I)) or item.startswith(("\\\\", "/", "~"))


def _load():
    try:
        return mode_manager.load_modes(), None
    except Exception as exc:
        return None, f"I couldn't read the modes ({exc}) 🌸"


def _save(modes):
    try:
        mode_manager.save_modes(modes)
        return None
    except Exception as exc:
        return f"I couldn't save the modes ({exc}) 🌸"


def _join(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


_ADD = re.compile(r"^(?:add|put|include) (.+?) (?:to|in|into) " + _MODE + r"$")
_REMOVE = re.compile(r"^(?:remove|delete|take|drop) (.+?) (?:from|out of) " + _MODE + r"$")
_CREATE = re.compile(r"^(?:create|make|new|add|set up)(?: a| an)?(?: new)? mode (?:called |named )?([a-z0-9 _-]+?)"
                     r"(?: with (.+))?$|^(?:create|make|set up)(?: a| an)? ([a-z0-9 _-]+?) mode(?: with (.+))?$")
_DELETE = re.compile(r"^(?:delete|remove|forget) " + _MODE + r"$")
_SHOW = re.compile(r"^(?:what(?:'s| is|s) in|show(?: me)?|describe) " + _MODE + r"$")
_LIST = {"list modes", "what modes do i have", "show my modes", "my modes", "which modes do i have",
         "show modes", "what are my modes"}
_SUGGEST = {"suggest a mode", "which mode should i use", "what mode should i use", "suggest mode",
            "which mode now", "pick a mode for me", "what mode now"}


def _parse_modes(text):
    text = text.strip().rstrip("?.! ")
    if text in _LIST:
        return "modes list"
    if text in _SUGGEST:
        return "modes suggest"
    for regex, verb in ((_ADD, "add"), (_REMOVE, "remove")):
        match = regex.match(text)
        if match:
            return f"modes {verb} {_name(match.group(2))}: {match.group(1)}"
    match = _CREATE.match(text)
    if match:
        name, items = (match.group(1), match.group(2)) if match.group(1) else (match.group(3), match.group(4))
        return f"modes create {_name(name)}: {items or ''}".rstrip()
    match = _DELETE.match(text)
    if match:
        return f"modes delete {_name(match.group(1))}"
    match = _SHOW.match(text)
    if match:
        return f"modes show {_name(match.group(1))}"
    return None


def _spec(arg):
    name, _, items = arg.partition(":")
    return _name(name), _split_items(items)


@tool("mode_add", "Add apps (or folders) to a mode, creating the mode if it's new.",
      {"spec": Param("'<mode>: <apps>', e.g. 'coding: discord, notion'")},
      command="modes add ", parse=_parse_modes, ai=True, priority=6)
def mode_add(ctx):
    name, items = _spec(ctx.arg)
    if not name or not items:
        return "Say it like \"add discord to coding mode\" 🌸"
    modes, error = _load()
    if error:
        return error
    mode = modes.setdefault(name, {"apps": []})
    added = []
    for item in items:
        key = "folders" if _is_folder(item) else "apps"
        bucket = mode.setdefault(key, [])
        if item.lower() not in (x.lower() for x in bucket):
            bucket.append(item)
            added.append(item)
    if not added:
        return f"{_join(items)} {'is' if len(items) == 1 else 'are'} already in {name} mode 🌸"
    error = ctx.run(f"{name}: {', '.join(added)}", lambda: _save(modes))
    return error or f"Added {_join(added)} to {name} mode 🌸"


@tool("mode_remove", "Take apps or folders out of a mode.",
      {"spec": Param("'<mode>: <apps>', e.g. 'study: spotify'")},
      command="modes remove ", ai=True, priority=6)
def mode_remove(ctx):
    name, items = _spec(ctx.arg)
    modes, error = _load()
    if error:
        return error
    if name not in modes:
        return f"There's no {name} mode 🌸"
    removed = []
    for item in items:
        for key in ("apps", "folders"):
            bucket = modes[name].get(key, [])
            hit = next((x for x in bucket if x.lower() == item.lower()), None)
            if hit:
                bucket.remove(hit)
                removed.append(hit)
    if not removed:
        return f"{_join(items) if items else 'That'} isn't in {name} mode 🌸"
    error = ctx.run(f"{name}: {', '.join(removed)}", lambda: _save(modes))
    return error or f"Took {_join(removed)} out of {name} mode 🌸"


@tool("mode_create", "Create a new mode with some apps.",
      {"spec": Param("'<mode>: <apps>', e.g. 'gaming: steam, discord'")},
      command="modes create ", ai=True, priority=6)
def mode_create(ctx):
    name, items = _spec(ctx.arg)
    if not name:
        return "What should the mode be called? 🌸"
    modes, error = _load()
    if error:
        return error
    if name in modes:
        return f"{name} mode already exists. Say \"add <app> to {name} mode\" to change it 🌸"
    modes[name] = {"apps": [i for i in items if not _is_folder(i)]}
    folders = [i for i in items if _is_folder(i)]
    if folders:
        modes[name]["folders"] = folders
    error = ctx.run(name, lambda: _save(modes))
    if error:
        return error
    if not items:
        return f"Created {name} mode. Add apps with \"add discord to {name} mode\" 🌸"
    return f"Created {name} mode with {_join(items)}. Say \"{name} mode\" to start it 🌸"


@tool("delete_mode", "Delete a mode.", {"name": Param("The mode")},
      command="modes delete ", tier=CONFIRM, priority=6)
def delete_mode(ctx):
    name = _name(ctx.arg)
    modes, error = _load()
    if error:
        return error
    if name not in modes:
        return f"There's no {name} mode 🌸"

    def go():
        modes.pop(name)
        return _save(modes) or f"Deleted {name} mode 🌸"

    return ask_or_reply(permissions.run_action("delete_mode", name, go))


def _describe(name, mode):
    parts = []
    if mode.get("apps"):
        parts.append("apps: " + ", ".join(mode["apps"]))
    if mode.get("folders"):
        parts.append("folders: " + ", ".join(mode["folders"]))
    return f"{name} mode has " + ("; ".join(parts) if parts else "nothing in it yet")


@tool("mode_show", "Tell the user what's in a mode.", {"name": Param("The mode")},
      command="modes show ", ai=True, priority=6)
def mode_show(ctx):
    name = _name(ctx.arg)
    modes, error = _load()
    if error:
        return error
    if name not in modes:
        return f"There's no {name} mode. You have: {', '.join(modes) or 'none'} 🌸"
    return _describe(name, modes[name]) + " 🌸"


@tool("mode_list", "Tell the user which modes they have.", command="modes list", ai=True, priority=6)
def mode_list():
    modes, error = _load()
    if error:
        return error
    if not modes:
        return "No modes yet. Try \"create a mode called gaming with steam and discord\" 🌸"
    return "Your modes: " + ", ".join(modes) + " 🌸"


@tool("mode_suggest", "Suggest which mode suits right now, from the user's habits and the time.",
      command="modes suggest", ai=True, priority=6)
def mode_suggest():
    try:
        name, why = mode_manager.suggest_mode()
    except Exception as exc:
        return f"I couldn't read the modes ({exc}) 🌸"
    if not name:
        return "I don't have a good guess yet. Use your modes for a few days and I'll learn 🌸"
    return f"How about {name} mode? {why[0].upper() + why[1:]}. Say \"{name} mode\" to start it 🌸"
