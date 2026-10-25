import random

import memory

DEFAULT_PERSONALITY = "calm"
CURRENT_PERSONALITY = None  # loaded from the saved profile on first use


PERSONALITIES = {

    "calm": {

        "open_app": [
            "Opening {target} 🌸",
            "{target} is ready ✨",
            "Launching {target} now 🌷",
            "Opening {target}. Looks like another session begins 🌸",
            "{target} again? You seem busy today ✨"
        ],

        "close_app": [
            "Closing {target} 🌸",
            "{target} has been closed ✨",
            "Goodbye, {target} 🌷"
        ],

        "restart_app": [
            "Restarting {target} 🌸",
            "{target} is waking back up ✨"
        ],

        "unknown": [
            "Hmm... I don't understand that yet 🌸",
            "Hina is still learning that one ✨",
            "That sounded mysterious 🌷"
        ]
    },


    "tsundere": {

        "open_app": [
            "I opened {target} already 💢",
            "{target} is open now. Try keeping up.",
            "Opening {target}... not because I wanted to help or anything."
        ],

        "close_app": [
            "Fine. Closing {target} 💢",
            "{target} is gone now."
        ],

        "restart_app": [
            "Restarting {target}. Happy now? 💢"
        ],

        "unknown": [
            "What was that supposed to mean? 💢",
            "Hmph. I don't understand."
        ]
    }
}


# How each personality talks in chat mode (appended to the chat system prompt).
# "calm" is the base Jarvis-style prompt, so it adds nothing.
CHAT_STYLES = {
    "calm": "",
    "tsundere": ("Persona: you are tsundere. You are brusque and a little prickly, you pretend "
                 "not to care, and you still help properly. Never be cruel."),
}

SWITCH_REPLIES = {
    "calm": "Understood. Back to calm 🌸",
    "tsundere": "Fine, I'll be tsundere. Not that I wanted to change for you or anything 💢",
}


def personalities():
    return sorted(PERSONALITIES)


def get_personality():
    """The active personality; the saved one on first use, "calm" if none or unknown."""
    global CURRENT_PERSONALITY
    if CURRENT_PERSONALITY is None:
        try:
            saved = memory.get_personality()
        except Exception:
            saved = None
        CURRENT_PERSONALITY = saved if saved in PERSONALITIES else DEFAULT_PERSONALITY
    return CURRENT_PERSONALITY


def set_personality(name):
    """Switch (and save) the personality. False if there is no such personality."""
    global CURRENT_PERSONALITY
    name = (name or "").strip().lower()
    if name not in PERSONALITIES:
        return False
    CURRENT_PERSONALITY = name
    try:
        memory.set_personality(name)
    except Exception:
        pass  # the switch still applies for this session
    return True


def chat_style(name=None):
    return CHAT_STYLES.get(name or get_personality(), "")


def generate_reply(action, target=""):

    personality_data = PERSONALITIES.get(
        get_personality(),
        PERSONALITIES["calm"]
    )

    responses = personality_data.get(
        action,
        personality_data["unknown"]
    )

    reply = random.choice(responses)

    return reply.format(target=target)
