"""
Hina's loggers: everything goes to the console, and, once the app calls
enable_file_logging(), also to a rotating file in the user data folder
(%APPDATA%\\ProjectHina\\logs\\hina.log, 1 MB x 3 files). Uncaught errors,
including ones on background threads, are written there too.

Tests never call enable_file_logging(), so they leave no log files behind.
"""

import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler

FORMAT = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
MAX_BYTES = 1_000_000
BACKUPS = 3

_loggers = []
_file_handler = None


def get_logger(name=None):
    """Return a configured logger for the given module name."""
    logger = logging.getLogger(name or __name__)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(FORMAT)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        _loggers.append(logger)
        if _file_handler is not None:
            logger.addHandler(_file_handler)
    return logger


def log_dir():
    from utils.paths import user_data_dir
    path = os.path.join(user_data_dir(), "logs")
    os.makedirs(path, exist_ok=True)
    return path


def log_path():
    """Where the log file is (or will be)."""
    return os.path.join(log_dir(), "hina.log")


def enable_file_logging():
    """Also write every logger to the rotating log file. Safe to call more than once. Returns the path."""
    global _file_handler
    if _file_handler is not None:
        return _file_handler.baseFilename
    try:
        handler = RotatingFileHandler(log_path(), maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8")
    except OSError as exc:  # a read-only or full disk must not stop Hina starting
        get_logger(__name__).warning("Couldn't open the log file: %s", exc)
        return None
    handler.setFormatter(FORMAT)
    _file_handler = handler
    for logger in _loggers:
        logger.addHandler(handler)
    _install_crash_hooks()
    get_logger(__name__).info("Logging to %s", handler.baseFilename)
    return handler.baseFilename


def _install_crash_hooks():
    crash_log = get_logger("crash")
    previous = sys.excepthook

    def on_crash(kind, value, tb):
        crash_log.critical("Uncaught error", exc_info=(kind, value, tb))
        previous(kind, value, tb)

    def on_thread_crash(args):
        if args.exc_type is SystemExit:
            return
        name = args.thread.name if args.thread else "?"
        crash_log.error("Uncaught error in thread %s", name, exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = on_crash
    threading.excepthook = on_thread_crash
