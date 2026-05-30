from voice import speak
from ui.effects import _pulse_output
from core.ai_loader import get_ai_engine
from core.context_manager import context_manager
from core.personality_engine import generate_reply
from utils.logger import get_logger

logger = get_logger(__name__)


def hina_reply(message, output_var, output_label, app):
    """Update the UI text, animate the response, and speak it aloud."""
    output_var.set(message)
    logger.info("Reply: %s", message)
    _pulse_output(output_label, app)
    speak(message, blocking=False)


def generate_response(action, target=""):
    """
    Generate a personality-based reply and enhance it with AI rewrites.
    AI enhancement is deferred and happens asynchronously if available.
    """
    base_reply = generate_reply(action=action, target=target)
    
    # Try AI enhancement only if engine is available/loaded
    # This prevents startup blocking and is optional
    ai_engine = get_ai_engine()
    if ai_engine and hasattr(ai_engine, 'rewrite_action_reply'):
        try:
            enhanced = ai_engine.rewrite_action_reply(
                base_reply, action, target, context_manager.get_context()
            )
            return enhanced if enhanced else base_reply
        except Exception as e:
            logger.warning("AI enhancement failed: %s", e)
            return base_reply
    
    return base_reply
