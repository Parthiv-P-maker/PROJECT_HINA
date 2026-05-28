import random


def build_startup_message(saved_name=None):
    """Return a greeting message based on saved user name."""
    if saved_name:
        choices = [
            f"Welcome back, {saved_name} 🌸",
            f"Good to see you again, {saved_name} 🎀",
            f"Hina is ready for another day with you, {saved_name} ✨"
        ]
    else:
        choices = [
            "Hina is awake and ready to help 🌸",
            "Welcome back! What shall we do today? 🎀",
            "Yay, Hina is here 🌷",
            "Ready for another productive day ✨",
            "Hina reporting in 🌸"
        ]
    return random.choice(choices)


def build_goodbye_message():
    """Return a random goodbye message."""
    choices = [
        "Bye bye! Take care 🌸",
        "Hina is going to sleep now 🎀",
        "See you soon! 🌷",
        "Good work today! ✨",
        "Until next time 🌸"
    ]
    return random.choice(choices)
