from collections import deque
from datetime import datetime

from core.personality_engine import CURRENT_PERSONALITY
from memory import get_name, get_recent_apps


class ContextManager:
    """Keep lightweight session state for AI context and mood."""

    def __init__(self, max_commands=20, max_failures=10):
        self.recent_commands = deque(maxlen=max_commands)
        self.recent_failures = deque(maxlen=max_failures)

    def register_command(self, raw_command, normalized_command, success=True):
        """Record a user command and whether it was successfully parsed."""
        self.recent_commands.append(raw_command)
        if not success:
            self.recent_failures.append(raw_command)

    def get_context(self):
        """Return current conversational context for AI prompts."""
        return {
            "user_name": get_name() or "friend",
            "recent_apps": get_recent_apps()[:5],
            "recent_commands": list(self.recent_commands),
            "recent_failures": list(self.recent_failures),
            "time_of_day": self._time_of_day(),
            "personality": CURRENT_PERSONALITY,
            "emotional_tone": self._emotional_tone(),
        }

    def _time_of_day(self):
        current_hour = datetime.now().hour
        if current_hour < 6:
            return "late night"
        if current_hour < 12:
            return "morning"
        if current_hour < 18:
            return "afternoon"
        return "evening"

    def _emotional_tone(self):
        current_hour = datetime.now().hour
        if current_hour < 6 or current_hour >= 22:
            return "soft"
        if 6 <= current_hour < 12:
            return "energetic"
        if 12 <= current_hour < 18:
            return "focused"
        return "calm"


context_manager = ContextManager()
