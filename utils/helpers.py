import re


def clean_text(text):
    """Strip non-ascii characters and normalize text for speech."""
    return re.sub(r"[^\x00-\x7F]+", "", str(text)).strip()


def try_parse_int(value, default=None):
    """Attempt to convert a value to int, returning a default on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
