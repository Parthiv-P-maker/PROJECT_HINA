import random
import time

from voice import speak
from ui.effects import _pulse_output
from utils.logger import get_logger

logger = get_logger(__name__)


def voiced_countdown(seconds, output_var, output_label, app):
    """Run a voice-enabled countdown while updating the GUI text."""
    cute_lines = [
        "Ready?", "Steady...", "Almost there...",
        "Just a little more...", "Don't blink...",
        "Hina is counting...", "Nearly done..."
    ]

    for i in range(seconds, 0, -1):
        msg = f"{i}... {random.choice(cute_lines)}"
        app.after(0, lambda m=msg: output_var.set(m))
        app.after(0, lambda: _pulse_output(output_label, app))
        speak(msg)
        time.sleep(1)

    app.after(0, lambda: output_var.set("Done!"))
    logger.info("Countdown finished for %s seconds", seconds)
