"""File and folder search."""

import re

import actions
from tools.registry import Param, drop_my, tool

_FIND = re.compile(r"^(?:find|locate)\b")


def _parse_find_folder(text):
    if _FIND.match(text) and re.search(r"\bfolder\b", text):
        return "find folder " + drop_my(re.sub(r"\bfolder\b", "", _FIND.sub("", text, count=1)))
    return None


def _parse_find_file(text):
    if _FIND.match(text):
        file_name = drop_my(_FIND.sub("", text, count=1))
        return "find file " + re.sub(r"^file\s+", "", file_name)
    return None


@tool("find_folder", "Search the computer for a folder by name.",
      {"name": Param("Folder name to search for")},
      command="find folder ", parse=_parse_find_folder, ai=True, priority=40)
def find_folder(ctx):
    name = ctx.arg.strip()
    return ctx.run(name, lambda: actions.find_folder(name))


@tool("find_file", "Search the computer for a file by name.",
      {"name": Param("File name to search for")},
      command="find file ", parse=_parse_find_file, ai=True, priority=40)
def find_file(ctx):
    name = ctx.arg.strip()
    return ctx.run(name, lambda: actions.find_file(name))
