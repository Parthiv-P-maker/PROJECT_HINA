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


_WAKE_ON = {"turn on wake word", "turn on the wake word", "enable wake word", "enable the wake word",
            "start wake word", "wake word on", "listen for hey hina", "start listening for hey hina",
            "listen for your name", "always listen", "start always listening"}
_WAKE_OFF = {"turn off wake word", "turn off the wake word", "disable wake word", "disable the wake word",
             "stop wake word", "wake word off", "stop listening for hey hina", "stop listening for your name",
             "stop always listening", "stop listening in the background"}


def _parse_wake(text):
    text = text.strip().rstrip("?.! ")
    if text in _WAKE_ON:
        return "wake word on"
    if text in _WAKE_OFF:
        return "wake word off"
    return None


@tool("wake_word", 'Turn the "Hey Hina" wake word on or off.', {"state": Param("'on' or 'off'")},
      command="wake word ", parse=_parse_wake, priority=5)
def wake_word(ctx):
    from core import wake
    on = ctx.arg.strip().lower() != "off"
    if not wake.request(on):
        return 'The wake word works in the main HUD (python hina.py). Turn it on in its settings 🎙️'
    return ""  # the window confirms in its log once the mic is (or isn't) listening
