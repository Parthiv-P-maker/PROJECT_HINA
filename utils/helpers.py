import re
import unicodedata

# Unicode categories that are never spoken: symbols (emoji live here), modifiers, private/unassigned.
_UNSPOKEN = {"So", "Sk", "Cs", "Co", "Cn"}
_INVISIBLE = {"‍", "︎", "️"}  # emoji joiners and variation selectors


def clean_text(text):
    """Text for speech: drop emoji and symbols, keep letters in every language ("café", "नमस्ते")."""
    text = str(text).replace("°", " degrees ")
    kept = "".join(" " if unicodedata.category(c) in _UNSPOKEN else c for c in text if c not in _INVISIBLE)
    return re.sub(r"\s+", " ", kept).strip()


def try_parse_int(value, default=None):
    """Attempt to convert a value to int, returning a default on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
