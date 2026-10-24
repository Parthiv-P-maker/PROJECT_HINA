"""Opening, closing and restarting apps and files; favorites; modes."""

import actions
import memory
from core import assistant
from core.mode_manager import launch_mode
from tools.registry import CONFIRM, Param, ask_or_reply, drop_my, tool

_FILE_EXTENSIONS = [
    ".pdf", ".txt", ".py", ".docx", ".doc",
    ".pptx", ".ppt", ".jpg", ".jpeg", ".png",
    ".mp3", ".mp4", ".csv", ".xlsx", ".exe",
]


def _parse_mode(text):
    if text.endswith(" mode"):
        mode_name = text[:-len(" mode")].strip()
        if mode_name:
            return "mode " + mode_name
    return None


@tool("launch_mode", "Open a saved group of apps and folders (a mode), e.g. 'study' or 'work'.",
      {"name": Param("Mode name")},
      command="mode ", parse=_parse_mode, priority=10)
def mode(ctx):
    return launch_mode(ctx.arg.strip())


def _parse_open(text):
    """'launch X' and 'open X' both become 'open X'; open + a file extension becomes 'open file X'."""
    if text.startswith("launch "):
        return "open " + drop_my(text[len("launch "):])
    if text.startswith("open "):
        target = drop_my(text[len("open "):])
        if any(ext in target for ext in _FILE_EXTENSIONS):
            return "open file " + target
        return "open " + target
    return None


@tool("open_file", "Search for a file by name and open it.",
      {"name": Param("File name, e.g. 'notes.txt'")},
      command="open file ")  # reached via the open_app parse above (extension detection)
def open_file(ctx):
    file_name = ctx.arg.strip()
    memory.add_recent_file(file_name)
    return ctx.run(file_name, lambda: actions.search_and_open_file(file_name))


@tool("open_app", "Open an application, program, or file on the user's computer by name.",
      {"name": Param("App or file name, e.g. 'chrome', 'notepad', 'notes.txt'")},
      command="open ", parse=_parse_open, ai=True)
def open_app(ctx):
    app_name = ctx.arg.strip()
    favorite_app = memory.get_favorite_app(app_name)
    if favorite_app:
        app_name = favorite_app
    result = ctx.run(app_name, lambda: actions.open_app(app_name))
    if "ouldn't" in result or "couldn't find" in result:
        return result
    if ctx.via_ai:
        return result  # the model path restyles the plain reply itself
    memory.add_recent_app(app_name)
    return assistant.generate_response("open_app", app_name)


def _parse_prefixed(prefix):
    def parse(text):
        if text.startswith(prefix):
            return prefix + drop_my(text[len(prefix):])
        return None
    return parse


def _confirmed_action(ctx, run, response_action, app_name):
    """The thing to run once the user says yes."""
    def go():
        result = run(app_name)
        if ctx.via_ai or "ouldn't" in result:
            return result
        return assistant.generate_response(response_action, app_name)
    return go


@tool("close_app", "Close a running application by name.",
      {"name": Param("App name, e.g. 'spotify'")},
      command="close ", parse=_parse_prefixed("close "), tier=CONFIRM, ai=True)
def close_app(ctx):
    app_name = ctx.arg.strip()
    return ask_or_reply(ctx.run(
        app_name, _confirmed_action(ctx, actions.close_app, "close_app", app_name)))


@tool("restart_app", "Restart an application by name (close then reopen it).",
      {"name": Param("App name, e.g. 'vscode'")},
      command="restart ", parse=_parse_prefixed("restart "), tier=CONFIRM, ai=True)
def restart_app(ctx):
    app_name = ctx.arg.strip()
    return ask_or_reply(ctx.run(
        app_name, _confirmed_action(ctx, actions.restart_app, "restart_app", app_name)))


@tool("favorite_app", "Give an app a nickname: 'favorite app chrome as browser'.",
      {"spec": Param("'<app> as <nickname>'")},
      command="favorite app ", starts=("favorite app ",), priority=60)
def favorite_app(ctx):
    data = ctx.arg.split(" as ")
    if len(data) == 2:
        return memory.set_favorite_app(data[1].strip(), data[0].strip())
    return "Use: favorite app chrome as browser 🌸"
