"""
Hina's long-term memory in SQLite (stdlib sqlite3), in the user data dir
(%APPDATA%\\ProjectHina\\hina_memory.db, or HINA_DATA_DIR):

  turns    every exchange: user text, Hina's reply, time, "command" or "chat"
  summary  one rolling summary of turns too old for the AI prompt
  facts    things the user asked Hina to remember ("remember that ...")
  reminders  "remind me at 6 to call mom" (core/reminders.py)
  list_items "add milk to my shopping list" (tools/planner.py)

Each call opens its own short-lived connection, so any thread may use it.
Private mode (settings.json "private_mode") stops turns and facts being written;
reading and deleting still work.
"""

import json
import os
import re
import sqlite3
import threading
from contextlib import closing
from datetime import datetime

from utils.logger import get_logger
from utils.paths import user_data_dir

logger = get_logger(__name__)

DB_FILE = "hina_memory.db"
COMMAND, CHAT = "command", "chat"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    user TEXT NOT NULL,
    reply TEXT NOT NULL,
    kind TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS summary (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    text TEXT NOT NULL,
    upto INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    source TEXT NOT NULL,
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    due TEXT NOT NULL,
    text TEXT NOT NULL,
    created TEXT NOT NULL,
    fired INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS list_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    list TEXT NOT NULL,
    text TEXT NOT NULL,
    created TEXT NOT NULL
);
"""

_lock = threading.RLock()


def db_path():
    return os.path.join(user_data_dir(), DB_FILE)


def _connect():
    conn = sqlite3.connect(db_path(), timeout=5)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)  # cheap no-op once the tables exist
    columns = {row[1] for row in conn.execute("PRAGMA table_info(facts)")}
    if "embedding" not in columns:  # added with semantic recall (roadmap 1.6)
        conn.execute("ALTER TABLE facts ADD COLUMN embedding TEXT")
        conn.commit()
    return conn


def _write(sql, params=()):
    with _lock, closing(_connect()) as conn, conn:
        return conn.execute(sql, params).lastrowid


def _rows(sql, params=()):
    with closing(_connect()) as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _now():
    return datetime.now().isoformat(timespec="seconds")


def is_private():
    """True while private mode is on in settings (nothing new is recorded)."""
    try:
        from ui_qt import settings as settings_mod  # pure Python, no Qt
        return bool(settings_mod.load().get("private_mode"))
    except Exception as exc:
        logger.warning("Couldn't read private mode setting: %s", exc)
        return False


# =========================
# CONVERSATION TURNS
# =========================

def record_turn(user, reply, kind=COMMAND):
    """Store one exchange. Returns its id, or None (private mode, empty input, or a DB error)."""
    if not (user or "").strip() or is_private():
        return None
    try:
        return _write("INSERT INTO turns (ts, user, reply, kind) VALUES (?, ?, ?, ?)",
                      (_now(), user.strip(), (reply or "").strip(), kind))
    except sqlite3.Error as exc:  # history must never break a command
        logger.warning("Couldn't record turn: %s", exc)
        return None


def recent_turns(limit=10, after_id=0):
    """The newest `limit` turns with id > after_id, oldest first."""
    try:
        rows = _rows("SELECT * FROM turns WHERE id > ? ORDER BY id DESC LIMIT ?", (after_id, limit))
    except sqlite3.Error as exc:
        logger.warning("Couldn't read history: %s", exc)
        return []
    return rows[::-1]


def turn_count():
    return _rows("SELECT COUNT(*) AS n FROM turns")[0]["n"]


def clear_history():
    with _lock, closing(_connect()) as conn, conn:
        conn.execute("DELETE FROM turns")
        conn.execute("DELETE FROM summary")


def get_summary():
    """(summary text, id of the last turn it covers); ("", 0) if there is none."""
    rows = _rows("SELECT text, upto FROM summary WHERE id = 1")
    return (rows[0]["text"], rows[0]["upto"]) if rows else ("", 0)


def set_summary(text, upto):
    _write("INSERT OR REPLACE INTO summary (id, text, upto) VALUES (1, ?, ?)", (text, upto))


def unsummarised_turns(keep=10):
    """Turns not covered by the summary yet, minus the newest `keep` (those stay verbatim)."""
    _, upto = get_summary()
    rows = _rows("SELECT * FROM turns WHERE id > ? ORDER BY id", (upto,))
    return rows[:-keep] if keep else rows


# =========================
# LONG-TERM FACTS
# =========================

_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "is", "are", "was", "were", "be", "am", "i", "im",
    "me", "my", "mine", "you", "your", "it", "its", "of", "to", "in", "on", "at", "for",
    "with", "that", "this", "about", "do", "does", "did", "what", "who", "how", "when",
    "where", "why", "which", "can", "could", "would", "should", "will", "have", "has",
    "had", "not", "no", "so", "if", "then", "than", "just", "really", "please", "hina",
    "tell", "know", "remember", "forget", "like", "any", "some", "all", "there", "they",
}
_WORD = re.compile(r"[a-z0-9]+")


def keywords(text):
    """Content words of `text`, lightly stemmed ("dogs" -> "dog")."""
    out = set()
    for word in _WORD.findall((text or "").lower().replace("'", "")):
        if len(word) < 3 or word in _STOPWORDS:
            continue
        out.add(word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word)
    return out


def add_fact(text, source="user"):
    """Store a fact. Returns its id (an existing one for a duplicate), or None in private mode."""
    text = (text or "").strip().rstrip(".").strip()
    if not text or is_private():
        return None
    for fact in list_facts():
        if fact["text"].lower() == text.lower():
            return fact["id"]
    return _write("INSERT INTO facts (text, source, created) VALUES (?, ?, ?)", (text, source, _now()))


def set_fact_embedding(fact_id, vector):
    """Cache a fact's embedding (a list of floats) so it is only computed once."""
    _write("UPDATE facts SET embedding = ? WHERE id = ?", (json.dumps(vector), fact_id))


def list_facts():
    return _rows("SELECT * FROM facts ORDER BY id")


def delete_facts(ids):
    ids = list(ids)
    if ids:
        with _lock, closing(_connect()) as conn, conn:
            conn.executemany("DELETE FROM facts WHERE id = ?", [(i,) for i in ids])
    return len(ids)


def delete_fact(fact_id):
    return delete_facts([fact_id])


def clear_facts():
    return delete_facts(f["id"] for f in list_facts())


def find_facts(query):
    """Facts that contain every content word of `query` ("forget my birthday")."""
    wanted = keywords(query)
    if not wanted:
        return []
    return [f for f in list_facts() if wanted <= keywords(f["text"])]


def relevant_facts(text, limit=5, always_if_at_most=6):
    """Facts sharing words with `text`, best first. With only a few facts, all of them."""
    facts = list_facts()
    if len(facts) <= always_if_at_most:
        return facts
    wanted = keywords(text)
    scored = [(len(wanted & keywords(f["text"])), f) for f in facts]
    hits = [f for score, f in sorted(scored, key=lambda s: (-s[0], -s[1]["id"])) if score]
    return hits[:limit]



# =========================
# REMINDERS AND LISTS (not affected by private mode: the user asked for them explicitly)
# =========================

def add_reminder(due, text):
    return _write("INSERT INTO reminders (due, text, created) VALUES (?, ?, ?)",
                  (due.isoformat(timespec="seconds"), text, _now()))


def pending_reminders():
    """Reminders that haven't gone off, soonest first."""
    return _rows("SELECT * FROM reminders WHERE fired = 0 ORDER BY due, id")


def mark_reminder_fired(reminder_id):
    _write("UPDATE reminders SET fired = 1 WHERE id = ?", (reminder_id,))


def delete_reminders(ids):
    ids = list(ids)
    if ids:
        with _lock, closing(_connect()) as conn, conn:
            conn.executemany("DELETE FROM reminders WHERE id = ?", [(i,) for i in ids])
    return len(ids)


def add_list_item(list_name, text):
    return _write("INSERT INTO list_items (list, text, created) VALUES (?, ?, ?)", (list_name, text, _now()))


def list_items(list_name):
    return _rows("SELECT * FROM list_items WHERE list = ? ORDER BY id", (list_name,))


def list_names():
    """[(list name, item count)], biggest first."""
    rows = _rows("SELECT list, COUNT(*) AS n FROM list_items GROUP BY list ORDER BY n DESC, list")
    return [(r["list"], r["n"]) for r in rows]


def delete_list_items(ids):
    ids = list(ids)
    if ids:
        with _lock, closing(_connect()) as conn, conn:
            conn.executemany("DELETE FROM list_items WHERE id = ?", [(i,) for i in ids])
    return len(ids)
