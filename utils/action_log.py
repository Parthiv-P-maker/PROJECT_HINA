"""Append-only action log: one JSON object per line (timestamp, action, target, outcome)."""

import json
import os
from datetime import datetime

from utils.logger import get_logger
from utils.paths import user_data_dir

logger = get_logger(__name__)


def log_path():
    return os.path.join(user_data_dir(), "action_log.jsonl")


def log_action(action, target, outcome):
    entry = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "action": action,
        "target": target or "",
        "outcome": outcome,
    }
    try:
        with open(log_path(), "a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:  # logging must never break an action
        logger.warning("Couldn't write action log: %s", exc)
    return entry
