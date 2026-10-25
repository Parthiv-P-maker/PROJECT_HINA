"""The Windows clipboard as plain text (pywin32). Tools call it through this module so tests can fake it."""

from utils.logger import get_logger

logger = get_logger(__name__)


def get_text():
    """The clipboard's text, or "" if it holds no text (an image, files, nothing)."""
    try:
        import win32clipboard
        win32clipboard.OpenClipboard()
        try:
            if not win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                return ""
            return win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT) or ""
        finally:
            win32clipboard.CloseClipboard()
    except Exception as exc:
        logger.warning("Reading the clipboard failed: %s", exc)
        return ""


def set_text(text):
    """Replace the clipboard with `text`. Returns True on success."""
    try:
        import win32clipboard
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
        finally:
            win32clipboard.CloseClipboard()
        return True
    except Exception as exc:
        logger.warning("Writing the clipboard failed: %s", exc)
        return False
