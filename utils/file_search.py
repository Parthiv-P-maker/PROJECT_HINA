"""Scoped, capped file/folder search (replaces walking all of C:\\)."""

import os
import time
from pathlib import Path

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "site-packages",
    "appdata", "$recycle.bin", "windows", "program files", "program files (x86)",
}
MAX_SECONDS = 8
MAX_DEPTH = 6


def search_roots():
    """Folders worth searching: the user's common folders plus the project's parent."""
    home = Path.home()
    names = ["Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music", "Projects"]
    roots = [home / n for n in names]
    roots += [home / "OneDrive" / n for n in ("Desktop", "Documents")]
    roots.append(Path(__file__).resolve().parents[2])
    seen, result = set(), []
    for root in roots:
        key = str(root).lower()
        if key not in seen and root.is_dir():
            seen.add(key)
            result.append(root)
    return result


def _walk(root):
    root_depth = len(Path(root).parts)
    for dirpath, dirnames, filenames in os.walk(root):
        depth = len(Path(dirpath).parts) - root_depth
        dirnames[:] = [
            d for d in dirnames
            if d.lower() not in SKIP_DIRS and not d.startswith(".")
        ] if depth < MAX_DEPTH else []
        yield dirpath, dirnames, filenames


def search(name, want="file", exact=False, limit=5):
    """
    Return up to `limit` matching paths for `want` in {"file", "folder"}.
    Exact matches are tried first (case-insensitive); stops after MAX_SECONDS.
    """
    needle = (name or "").strip().lower()
    if not needle:
        return []

    deadline = time.time() + MAX_SECONDS
    exact_hits, partial_hits = [], []

    for root in search_roots():
        for dirpath, dirnames, filenames in _walk(root):
            if time.time() > deadline:
                return (exact_hits + partial_hits)[:limit]
            entries = filenames if want == "file" else dirnames
            for entry in entries:
                low = entry.lower()
                if low == needle:
                    exact_hits.append(os.path.join(dirpath, entry))
                elif not exact and needle in low:
                    partial_hits.append(os.path.join(dirpath, entry))
            if len(exact_hits) >= limit:
                return exact_hits[:limit]
    return (exact_hits + partial_hits)[:limit]
