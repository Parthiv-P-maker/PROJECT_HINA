"""Small talk and the user's name."""

import random

import memory
from core import personality_engine
from tools.registry import Param, tool


def _smalltalk(name, command, replies, *, triggers=(), exact_triggers=(), aliases=()):
    # prompt=False: the AI string-mapping fallback mustn't turn conversation into a
    # canned line; unmatched input goes to chat mode instead (tools/recall.py).
    @tool(name, f"Small talk: '{command}'.", command=command, triggers=triggers,
          exact_triggers=exact_triggers, aliases=aliases, priority=30, prompt=False)
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


_NAME_PREFIXES = ("my name is ", "call me ", "you can call me ")
_NOT_NAMES = {"", "user", "the user", "friend", "sir", "madam", "unknown", "me", "you", "hina"}
_ASK_NAME = {"whats my name", "what's my name", "what is my name", "do you know my name",
             "do you remember my name", "who am i"}


def _parse_my_name(text):
    for prefix in _NAME_PREFIXES:
        if text.startswith(prefix):
            return "set name " + text[len(prefix):].strip()
    return None


# Not exposed to the model: Qwen called it for "what's my name?" and saved "user" as the name.
@tool("set_name", "Remember the user's name for future greetings.",
      {"name": Param("The user's name")},
      command="set name ", parse=_parse_my_name, priority=60)
def set_name(ctx):
    name = ctx.arg.strip().rstrip(".!").strip()
    if name.lower() in _NOT_NAMES or "?" in name or len(name.split()) > 4:
        return "What should I call you? Say \"my name is ...\"."
    return memory.set_name(name)


def _parse_ask_name(text):
    return "whats my name" if text.rstrip("?.! ") in _ASK_NAME else None


@tool("get_name", "Tell the user the name Hina has for them.",
      command="whats my name", parse=_parse_ask_name, priority=5)
def get_name():
    name = memory.get_name()
    return f"You're {name}." if name else "You haven't told me your name yet. Say \"my name is ...\"."


# ---- personality switching ("be tsundere") -------------------------------
_PERSONA_PREFIXES = ("set personality to ", "set personality ", "personality ", "switch to ",
                     "change to ", "be more ", "be ", "act ", "act like a ", "act like ")


def _parse_personality(text):
    text = text.strip().rstrip("?.! ")
    for suffix in (" mode", " personality"):
        if text.endswith(suffix):
            text = text[:-len(suffix)]
    if text in personality_engine.personalities():  # "tsundere mode"
        return "set personality " + text
    for prefix in _PERSONA_PREFIXES:
        if text.startswith(prefix):
            name = text[len(prefix):].strip()
            if name in personality_engine.personalities():
                return "set personality " + name
    return None


@tool("set_personality", "Switch Hina's personality (for example calm or tsundere).",
      {"name": Param("The personality: " + ", ".join(personality_engine.personalities()))},
      command="set personality ", parse=_parse_personality, ai=True, priority=5)
def set_personality(ctx):
    name = ctx.arg.strip().lower()
    if not personality_engine.set_personality(name):
        return "I only know these personalities: " + ", ".join(personality_engine.personalities()) + "."
    return personality_engine.SWITCH_REPLIES.get(name, f"Personality set to {name}.")


@tool("get_personality", "Tell the user which personality Hina is using.",
      command="which personality", exact_triggers=("which personality", "what personality are you",
                                                   "what personality do you have"), priority=5)
def get_personality():
    return f"I'm being {personality_engine.get_personality()} right now."
