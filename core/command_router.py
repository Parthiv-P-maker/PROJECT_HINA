from parser import normalize_command


def route_command(raw_command):
    """Normalize the user command text for processing."""
    return normalize_command(raw_command)
