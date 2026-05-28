from voice import speak
from ui.effects import _pulse_output
from core.personality_engine import generate_reply
from utils.logger import get_logger

logger = get_logger(__name__)


def hina_reply(message, output_var, output_label, app):
    """Update the UI text, animate the response, and speak it aloud."""
    output_var.set(message)
    logger.info("Reply: %s", message)
    _pulse_output(output_label, app)
    speak(message)


def generate_response(action, target=""):
    """Generate a personality-based reply for a given action."""
    return generate_reply(action=action, target=target)
