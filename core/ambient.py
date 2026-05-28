import random
import time

from utils.constants import AMBIENT_INACTIVITY_MS, AMBIENT_REPEAT_DELAY_MS, AMBIENT_THOUGHTS
from utils.logger import get_logger

logger = get_logger(__name__)


class AmbientThoughtManager:
    """Manage subtle ambient thoughts after user inactivity."""

    def __init__(self, app, output_var, output_label):
        self.app = app
        self.output_var = output_var
        self.output_label = output_label
        self.timer_id = None
        self.last_activity = time.time()

    def start(self):
        """Begin monitoring user activity for ambient thoughts."""
        self._schedule_idle_check()

    def reset_timer(self, event=None):
        """Reset inactivity tracking when the user interacts with Hina."""
        self.last_activity = time.time()
        if self.timer_id:
            self.app.after_cancel(self.timer_id)
        self._schedule_idle_check()

    def _schedule_idle_check(self):
        self.timer_id = self.app.after(AMBIENT_INACTIVITY_MS, self._on_idle)

    def _on_idle(self):
        if self.app.focus_get() is not None:
            logger.debug("Ambient thought skipped because user is active")
            self._schedule_idle_check()
            return

        if time.time() - self.last_activity < (AMBIENT_INACTIVITY_MS / 1000):
            self._schedule_idle_check()
            return

        self._show_thought()
        self.timer_id = self.app.after(AMBIENT_REPEAT_DELAY_MS, self._on_idle)

    def _show_thought(self):
        thought = random.choice(AMBIENT_THOUGHTS)
        self.output_var.set(thought)
        logger.info("Ambient thought: %s", thought)
