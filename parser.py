import re

from tools import registry

_POLITE_PREFIX = re.compile(r"^(?:(?:please|can you|could you|would you|hey hina|hina)[ ,]+)+")


def normalize_command(command):
    """Strip polite filler, then let the tool registry map the text to a normalized command."""
    command = command.lower().strip()
    command = _POLITE_PREFIX.sub("", command).strip()
    normalized = registry.normalize(command)
    return command if normalized is None else normalized
