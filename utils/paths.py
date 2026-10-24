"""Where Hina keeps per-user data (action log, extra search folders)."""

import os


def user_data_dir():
    """%APPDATA%\ProjectHina (override with HINA_DATA_DIR). Created on demand."""
    base = os.environ.get("HINA_DATA_DIR") or os.path.join(
        os.environ.get("APPDATA") or os.path.expanduser("~"), "ProjectHina"
    )
    os.makedirs(base, exist_ok=True)
    return base
