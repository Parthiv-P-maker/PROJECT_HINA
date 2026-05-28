from voice import speak
from ui.effects import _pulse_output
from core.ai_engine import rewrite_action_reply
from core.context_manager import context_manager
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
    """Generate a personality-based reply and enhance it with AI rewrites."""
    base_reply = generate_reply(action=action, target=target)
    return rewrite_action_reply(base_reply, action, target, context_manager.get_context())
