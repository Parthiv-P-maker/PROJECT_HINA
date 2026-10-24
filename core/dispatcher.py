import random

from core.conversation import UNKNOWN_REPLIES as _UNKNOWN_REPLIES
from tools import registry
from tools.registry import DispatchResult  # noqa: F401  (gui and tests import it from here)


def dispatch_command(command, output_var=None, output_label=None, app=None):
    """Run a normalized command through the tool that owns it (see tools/)."""
    result = registry.dispatch(
        command, output_var=output_var, output_label=output_label, app=app)
    if result is None:
        return DispatchResult(reply=random.choice(_UNKNOWN_REPLIES))
    return result
