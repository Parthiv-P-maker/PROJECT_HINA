"""Housekeeping commands: goodbye, yes/no answers, and model-written replies."""

from core import permissions
from core.startup import build_goodbye_message
from tools.registry import DispatchResult, Param, ask_or_reply, tool
from utils.constants import EXIT_DELAY_MS


@tool("bye", "Say goodbye and close Hina.", command="bye", aliases=("exit",),
      prompt=False, priority=90)
def bye():
    return DispatchResult(
        reply=build_goodbye_message(),
        should_exit=True,
        exit_delay_ms=EXIT_DELAY_MS,
    )


@tool("confirm_yes", "Answer 'yes' to a pending 'Should I?' question.", command="confirm yes",
      prompt=False, priority=90)
def confirm_yes():
    return permissions.resolve(True)


@tool("confirm_no", "Answer 'no' to a pending 'Should I?' question.", command="confirm no",
      prompt=False, priority=90)
def confirm_no():
    return permissions.resolve(False)


@tool("ai_reply", "A reply the model already produced by running a tool.",
      {"text": Param("The reply text")},
      command="ai_reply::", router=False, prompt=False, priority=90)
def ai_reply(ctx):
    return ask_or_reply(ctx.arg)
