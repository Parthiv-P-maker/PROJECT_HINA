"""
A small index of the user's files (roadmap 3.8): name, type, folder and modified time
of everything under the search roots (Desktop, Documents, Downloads, plus the
folders added in settings), in SQLite next to the other user data.

It makes "open the PDF I downloaded yesterday" instant instead of a disk walk.
The windows refresh it in the background at startup (start_background_refresh);
a query on an empty index builds it on the spot.
"""

import os
import sqlite3
import threading
import time
from contextlib import closing
from datetime import datetime, timedelta

from utils.logger import get_logger
from utils.paths import user_data_dir

logger = get_logger(__name__)

DB_FILE = "file_index.db"
MAX_SECONDS = 45            # a refresh gives up after this; the next one continues
REFRESH_AFTER = timedelta(hours=6)

KINDS = {
    "pdf": (".pdf",),
    "word": (".docx", ".doc", ".odt", ".rtf"),
    "excel": (".xlsx", ".xls", ".csv", ".ods"),
    "powerpoint": (".pptx", ".ppt", ".odp"),
    "image": (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".heic"),
    "video": (".mp4", ".mkv", ".mov", ".avi", ".webm"),
    "audio": (".mp3", ".wav", ".m4a", ".flac", ".ogg"),
    "zip": (".zip", ".rar", ".7z", ".tar", ".gz"),
    "text": (".txt", ".md"),
    "code": (".py", ".js", ".ts", ".java", ".c", ".cpp", ".cs", ".html", ".css", ".ipynb"),
    "installer": (".exe", ".msi"),
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    ext TEXT NOT NULL,
    root TEXT NOT NULL,
    mtime REAL NOT NULL,
    size INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS files_mtime ON files (mtime);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

_lock = threading.Lock()
_refreshing = threading.Lock()
_started = threading.Event()


def db_path():
    return os.path.join(user_data_dir(), DB_FILE)


def _connect():
    conn = sqlite3.connect(db_path(), timeout=5)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def kind_of(ext):
    ext = ext.lower()
    return next((kind for kind, exts in KINDS.items() if ext in exts), "other")


def _roots():
    from utils.file_search import search_roots
    return search_roots()


def refresh(roots=None):
    """Re-scan the roots. Returns the number of files indexed (0 if a refresh is already running)."""
    if not _refreshing.acquire(blocking=False):
        return 0
    try:
        from utils.file_search import _walk
        roots = _roots() if roots is None else roots
        start, rows = time.time(), []
        for root in roots:
            for dirpath, _, filenames in _walk(root):
                for name in filenames:
                    path = os.path.join(dirpath, name)
                    try:
                        stat = os.stat(path)
                    except OSError:
                        continue
                    rows.append((path, name, os.path.splitext(name)[1].lower(), str(root),
                                 stat.st_mtime, stat.st_size))
                if time.time() - start > MAX_SECONDS:
                    logger.info("File index refresh hit its time limit at %d files", len(rows))
                    break
        with _lock, closing(_connect()) as conn, conn:
            conn.execute("DELETE FROM files")
            conn.executemany("INSERT OR REPLACE INTO files VALUES (?, ?, ?, ?, ?, ?)", rows)
            conn.execute("INSERT OR REPLACE INTO meta VALUES ('refreshed', ?)", (datetime.now().isoformat(),))
        logger.info("Indexed %d files in %.1fs", len(rows), time.time() - start)
        return len(rows)
    finally:
        _refreshing.release()


def last_refresh():
    with closing(_connect()) as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = 'refreshed'").fetchone()
    return datetime.fromisoformat(row["value"]) if row else None


def count():
    with closing(_connect()) as conn:
        return conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]


def start_background_refresh():
    """Refresh in the background if the index is old or empty (the windows call this at startup)."""
    if _started.is_set():
        return
    _started.set()
    stamp = last_refresh()
    if stamp is None or datetime.now() - stamp > REFRESH_AFTER:
        threading.Thread(target=refresh, name="hina-file-index", daemon=True).start()


def search(kind=None, since=None, until=None, root_word=None, words=(), limit=10):
    """Newest-first rows matching a type ("pdf"), a time window, a root ("downloads") and name words."""
    if count() == 0:
        refresh()
    sql, args = "SELECT * FROM files WHERE 1 = 1", []
    if kind and kind in KINDS:
        exts = KINDS[kind]
        sql += f" AND ext IN ({', '.join('?' * len(exts))})"
        args += list(exts)
    if since:
        sql += " AND mtime >= ?"
        args.append(since.timestamp())
    if until:
        sql += " AND mtime < ?"
        args.append(until.timestamp())
    if root_word:  # "downloads": anywhere in the path, so OneDrive\Downloads and sub-folders count
        sql += " AND LOWER(path) LIKE ?"
        args.append(f"%{root_word.lower()}%")
    for word in words:
        sql += " AND LOWER(name) LIKE ?"
        args.append(f"%{word.lower()}%")
    sql += " ORDER BY mtime DESC LIMIT ?"
    args.append(limit)
    with closing(_connect()) as conn:
        rows = [dict(r) for r in conn.execute(sql, args).fetchall()]
    return [r for r in rows if os.path.exists(r["path"])]


def window(when, now=None):
    """(since, until) for 'today', 'yesterday', 'this week', 'last week'; (None, None) otherwise."""
    now = now or datetime.now()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if when == "today":
        return midnight, None
    if when == "yesterday":
        return midnight - timedelta(days=1), midnight
    if when == "this week":
        return midnight - timedelta(days=now.weekday()), None
    if when == "last week":
        start = midnight - timedelta(days=now.weekday() + 7)
        return start, start + timedelta(days=7)
    return None, None
