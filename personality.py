import random

PERSONALITY = "calm"


def enhance_reply(action, target="", base_reply=""):

    if PERSONALITY == "calm":

        calm_replies = {

            "open_app": [
                f"Opening {target} 🌸",
                f"{target} is ready ✨",
                f"Launching {target} now 🌷",
                f"Opening {target}. Try not to open too many tabs 🌸"
            ],

            "close_app": [
                f"Closing {target} 🌸",
                f"{target} has been closed ✨"
            ],

            "timer_done": [
                "Timer finished 🌸",
                "Time's up ✨",
                "Done already? 🌷"
            ]
        }

        if action in calm_replies:
            return random.choice(calm_replies[action])

    return base_reply