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


@tool("stop_speaking", "Stop talking right now.", command="stop talking",
      exact_triggers=("stop", "stop talking", "stop speaking", "be quiet", "quiet", "shut up",
                      "silence", "hush", "enough"), priority=5)
def stop_speaking():
    import voice
    voice.stop()
    return DispatchResult()  # say nothing: that's the point


_DOCTOR = {"run a self check", "run a self-check", "self check", "self-check", "run diagnostics",
           "run a diagnostic", "system check", "run a system check", "check yourself", "diagnose yourself",
           "are you working properly", "is everything working", "health check", "run a health check"}


@tool("self_check", "Check Hina's setup (Ollama, models, microphone, packages) and report problems.",
      command="self check", parse=lambda t: "self check" if t.strip().rstrip("?.! ") in _DOCTOR else None,
      ai=True, priority=5)
def self_check():
    from core import doctor
    return doctor.summary(doctor.run_checks())
