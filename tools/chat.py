"""Small talk and the user's name."""

import random

import memory
from tools.registry import Param, tool


def _smalltalk(name, command, replies, *, triggers=(), exact_triggers=(), aliases=()):
    @tool(name, f"Small talk: '{command}'.", command=command, triggers=triggers,
          exact_triggers=exact_triggers, aliases=aliases, priority=30)
    def _reply():
        return random.choice(replies)
    return _reply


_smalltalk("smalltalk_hello", "hello", [
    "Hello! 🌸", "Hi there! 🎀", "Welcome back! 🌷", "Hina is listening ✨",
], exact_triggers=("hello", "hi", "hey"), aliases=("hi",))

_smalltalk("smalltalk_who_are_you", "who are you", [
    "I'm Hina, your desktop assistant 🌸",
    "Project Hina at your service 🎀",
    "Your cheerful anime companion ✨",
], triggers=("who are you",))

_smalltalk("smalltalk_how_are_you", "how are you", [
    "I'm doing great 🌸", "Feeling cheerful as always 🎀", "All systems happy ✨",
], triggers=("how are you",))

_smalltalk("smalltalk_thanks", "thanks", [
    "You're welcome 🌸", "Happy to help 🎀", "Anytime ✨",
], triggers=("thanks", "thank you"))

_smalltalk("smalltalk_what_can_you_do", "what can you do", [
    "Open apps, manage files, tell time, calculate, set timers, and more 🌸",
], triggers=("what can you do",))

_smalltalk("smalltalk_what_do_you_think", "what do you think", [
    "It feels like a good moment to keep going 🌸",
    "I think your focus is lovely today ✨",
    "You seem ready for something creative 🌷",
], triggers=("what do you think",))

_smalltalk("smalltalk_tired", "im tired", [
    "Take a gentle break when you can 🌸",
    "You deserve a rest after all that work ✨",
    "A little pause can feel really nice right now 🌷",
], triggers=("i'm tired", "im tired", "i am tired"))

_smalltalk("smalltalk_tell_me_something", "tell me something", [
    "Hina says: small steps still move you forward 🌸",
    "A calm mind makes room for good ideas ✨",
    "Sometimes quiet moments are the most powerful 🌷",
], triggers=("tell me something", "say something"))


def _parse_my_name(text):
    if text.startswith("my name is "):
        return "set name " + text.replace("my name is ", "").strip()
    return None


@tool("set_name", "Remember the user's name for future greetings.",
      {"name": Param("The user's name")},
      command="set name ", parse=_parse_my_name, ai=True, priority=60)
def set_name(ctx):
    return memory.set_name(ctx.arg.strip())
