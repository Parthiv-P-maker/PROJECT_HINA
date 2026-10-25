"""Recent files ("open the PDF I downloaded yesterday") and asking questions about a document (roadmap 3.8)."""

import os
import re
from datetime import datetime

from tools.registry import Param, tool
from utils import documents, file_index
from utils.file_search import search as search_files

# spoken words -> utils.file_index kinds
_KIND_WORDS = {
    "pdf": "pdf", "word": "word", "doc": "word", "document": "word", "excel": "excel",
    "spreadsheet": "excel", "sheet": "excel", "csv": "excel", "powerpoint": "powerpoint",
    "presentation": "powerpoint", "slides": "powerpoint", "ppt": "powerpoint", "image": "image",
    "photo": "image", "picture": "image", "screenshot": "image", "pic": "image", "video": "video",
    "song": "audio", "audio": "audio", "zip": "zip", "archive": "zip", "installer": "installer",
    "setup": "installer", "file": None, "download": None, "thing": None,
}
_KIND = r"(pdf|word|doc|document|excel|spreadsheet|sheet|csv|powerpoint|presentation|slides|ppt|image|photo|" \
        r"picture|screenshot|pic|video|song|audio|zip|archive|installer|setup|file|download|thing)"
_WHEN = r"(today|yesterday|this week|last week)"
_RECENT = re.compile(
    r"^(open|show|find|list|what(?:'s| is| was| are)) (?:me )?(?:the |my |a )?(?:last |latest |newest |most recent |recent )?"
    + _KIND + r"(?: (?:file|doc|document))?s?(?: (?:i|that i|which i) (downloaded|saved|made|created|got|took|edited))?"
    r"(?: (?:from |on )?" + _WHEN + r")?$")
_WHAT_DID = re.compile(r"^what did i (download|save|create|make)(?: " + _WHEN + r")?$")
_RECENT_LIST = {"recent files", "my recent files", "show my recent files", "recent downloads",
                "my recent downloads", "show my recent downloads", "show recent files", "show recent downloads"}


def _parse_recent(text):
    text = text.strip().rstrip("?.! ")
    if text in _RECENT_LIST:
        return "recent list any any " + ("downloads" if "download" in text else "any")
    match = _WHAT_DID.match(text)
    if match:
        where = "downloads" if match.group(1) == "download" else "any"
        return f"recent list any {match.group(2) or 'any'} {where}"
    match = _RECENT.match(text)
    if not match:
        return None
    verb, word, how, when = match.groups()
    kind = _KIND_WORDS.get(word)
    # "open the file" alone is the open_file tool's job; we need a type, a time or "download"
    if kind is None and not when and word != "download" and how != "downloaded":
        return None
    action = "open" if verb == "open" else "list"
    where = "downloads" if word == "download" or how == "downloaded" else "any"
    return f"recent {action} {kind or 'any'} {when or 'any'} {where}"


def _describe_age(mtime):
    when = datetime.fromtimestamp(mtime)
    days = (datetime.now().date() - when.date()).days
    clock = when.strftime("%I:%M %p").lstrip("0")
    return f"today {clock}" if days == 0 else "yesterday" if days == 1 else when.strftime("%d %b")


@tool("recent_files", "Find or open the user's most recent files of a type (PDF, Word, image...), "
                      "e.g. the PDF they downloaded yesterday.",
      {"spec": Param("'<open|list> <pdf|word|excel|powerpoint|image|video|audio|zip|any> "
                     "<today|yesterday|this week|last week|any> <downloads|any>', e.g. 'open pdf yesterday downloads'")},
      command="recent ", parse=_parse_recent, ai=True, priority=6)
def recent_files(ctx):
    parts = (ctx.arg.strip().split() + ["list", "any", "any", "any"])[:5]
    action, kind = parts[0], parts[1]
    when = " ".join(parts[2:4]) if parts[2] in ("this", "last") else parts[2]
    where = parts[4] if parts[2] in ("this", "last") else parts[3]
    since, until = file_index.window(when)
    rows = file_index.search(kind=None if kind == "any" else kind, since=since, until=until,
                             root_word=None if where == "any" else where, limit=5)
    what = ("PDF" if kind == "pdf" else kind if kind != "any" else "file")
    when_text = "" if when == "any" else f" from {when}"
    if not rows:
        return f"I didn't find any {what}s{when_text}" + (" in Downloads" if where == "downloads" else "") + " 📂"
    if action == "open":
        newest = rows[0]
        try:
            ctx.run(newest["name"], lambda: os.startfile(newest["path"]))
        except OSError:
            return f"I couldn't open {newest['name']} 📂"
        return f"Opening {newest['name']} ({_describe_age(newest['mtime'])}) 📂"
    listing = "; ".join(f"{r['name']} ({_describe_age(r['mtime'])})" for r in rows)
    return f"Recent {what}s{when_text}: {listing} 📂"


@tool("refresh_file_index", "Re-scan the user's folders so file search is up to date.",
      command="refresh file index",
      exact_triggers=("refresh file index", "reindex my files", "re-index my files", "rescan my files",
                      "update the file index", "refresh my files"), priority=6)
def refresh_file_index(ctx):
    count = ctx.run("files", file_index.refresh)
    return f"Indexed {count} files 📂" if count else "A re-scan is already running 📂"


# =========================
# QUESTIONS ABOUT A DOCUMENT
# =========================

_LOAD = re.compile(r"^(?:load|open(?: up)?|read|let'?s talk about|ask about|i have questions about)"
                   r"(?: the)?(?: (?:document|doc|pdf|file|report|paper|book))? (.+?)"
                   r"(?: for (?:questions|q and a|qa|reading))?$")
_ASK = re.compile(r"^(?:ask|query) (?:the |my )?(?:document|doc|pdf|file|report|paper|book)[:,]? (.+)$|"
                  r"^(?:according to|in|from) (?:the |my )?(?:document|doc|pdf|file|report|paper|book)[:,]? (.+)$|"
                  r"^what does (?:the |my )?(?:document|doc|pdf|file|report|paper|book) say about (.+)$")
_SUMMARY = re.compile(r"^(?:summari[sz]e|sum up|tldr)(?: the| my| this)? (?:document|doc|pdf|report|paper|book|file)$")
_CLOSE = re.compile(r"^(?:close|forget|unload|done with)(?: the| my| this)? (?:document|doc|pdf|report|paper|book)$")
_STATUS = {"which document is loaded", "what document is open", "which document is open",
           "what pdf is open", "which file is loaded", "what document are we on"}


def _parse_docs(text):
    text = text.strip().rstrip("?.! ")
    if text in _STATUS:
        return "doc status"
    if _SUMMARY.match(text):
        return "doc summary"
    if _CLOSE.match(text):
        return "doc close"
    match = _ASK.match(text)
    if match:
        return "doc ask " + next(g for g in match.groups() if g).strip()
    match = _LOAD.match(text)
    if match:
        name = match.group(1).strip()
        explicit = text.endswith(("for questions", "for q and a", "for qa")) or not text.startswith(("open", "read"))
        reading = text.startswith("read") and os.path.splitext(name)[1].lower() in documents.SUPPORTED
        if explicit or reading:
            # "load my notes" / "read report.pdf" yes; "open notes.txt" opens it, "read my clipboard" isn't a doc
            if name not in ("clipboard", "my clipboard", "the clipboard", "it", "this", "that")                     and not name.endswith(" mode"):
                return "doc load " + name
    return None


def _find_document(name):
    name = re.sub(r"^(?:my|the) ", "", name.strip())
    if os.path.isfile(name):
        return name
    stem, ext = os.path.splitext(name)
    words = [w for w in re.split(r"[\s_-]+", stem) if w]
    hits = [r["path"] for r in file_index.search(words=words, limit=20)
            if os.path.splitext(r["path"])[1].lower() in documents.SUPPORTED
            and (not ext or r["path"].lower().endswith(ext.lower()))]
    if hits:
        return hits[0]
    for path in search_files(name, want="file"):
        if os.path.splitext(path)[1].lower() in documents.SUPPORTED:
            return path
    return None


def _doc_checked(fn):
    try:
        return fn()
    except documents.DocumentError as exc:
        return str(exc)


@tool("document", "Open a document (PDF, Word, PowerPoint, text) for questions, ask it something, "
                  "summarise it, or close it.",
      {"spec": Param("'load <file name>', 'ask <question>', 'summary', 'status' or 'close'")},
      command="doc ", parse=_parse_docs, ai=True, priority=6)
def document(ctx):
    verb, _, rest = ctx.arg.strip().partition(" ")
    rest = rest.strip()

    if verb == "load":
        if not rest:
            return "Which document? Say \"load\" and its name 📄"
        path = _find_document(rest)
        if not path:
            return f"I couldn't find a document called {rest} 📄"

        def load():
            doc = ctx.run(os.path.basename(path), lambda: documents.load(path))
            return f"Loaded {documents.describe(doc)}. Ask me anything about it, like \"ask the document ...\" 📄"
        return _doc_checked(load)

    if verb == "ask":
        if documents.active() is None:
            return "No document is open. Say \"load\" and a file name first 📄"
        return _doc_checked(lambda: f"{documents.ask(rest)} 📄")

    if verb == "summary":
        return _doc_checked(lambda: f"{documents.active().name if documents.active() else ''}: {documents.summarise()} 📄"
                            if documents.active() else documents.summarise())

    if verb == "close":
        was = documents.close()
        return f"Closed {was.name} 📄" if was else "No document was open 📄"

    doc = documents.active()
    return f"I have {documents.describe(doc)} open 📄" if doc else "No document is open 📄"
