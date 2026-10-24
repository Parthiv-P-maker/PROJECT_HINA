"""
Hina's tool registry. Each command is defined once, in one of these modules,
with `@tool(...)`; see tools/README.md. Importing the package registers them all.
"""

from tools import registry  # noqa: F401
from tools import system, chat, files, apps, web, session  # noqa: F401
