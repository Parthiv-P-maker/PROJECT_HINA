"""
Lazy loading module for AI systems.
Defers Ollama initialization until first use to prevent startup blocking.
"""

import threading
from utils.logger import get_logger

logger = get_logger(__name__)

# Lazy-loaded modules
_ai_engine = None
_ai_lock = threading.Lock()


def get_ai_engine():
    """Get or lazily initialize the AI engine on first access."""
    global _ai_engine
    
    if _ai_engine is not None:
        return _ai_engine
    
    with _ai_lock:
        # Double-check after acquiring lock
        if _ai_engine is not None:
            return _ai_engine
        
        try:
            from core import ai_engine as engine_module
            _ai_engine = engine_module
            logger.info("AI engine initialized")
            return _ai_engine
        except Exception as e:
            logger.error("Failed to initialize AI engine: %s", e)
            return None


def is_ai_engine_ready():
    """Check if AI engine is already loaded."""
    return _ai_engine is not None
