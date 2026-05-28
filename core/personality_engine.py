import random


CURRENT_PERSONALITY = "calm"


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


def generate_reply(action, target=""):

    personality_data = PERSONALITIES.get(
        CURRENT_PERSONALITY,
        PERSONALITIES["calm"]
    )

    responses = personality_data.get(
        action,
        personality_data["unknown"]
    )

    reply = random.choice(responses)

    return reply.format(target=target)