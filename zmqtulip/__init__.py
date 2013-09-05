# This relies on each of the submodules having an __all__ variable.
from .core import *
from .selector import *

__all__ = ['new_event_loop'] + (core.__all__ + selector.__all__)


def new_event_loop():
    """Create new event loop with zmq selector."""
    from tulip import unix_events
    return unix_events.SelectorEventLoop(selector=ZmqSelector())
