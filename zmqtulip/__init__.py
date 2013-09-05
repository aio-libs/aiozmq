# This relies on each of the submodules having an __all__ variable.
from .selector import *

__all__ = ['new_event_loop'] + (selector.__all__)


def new_event_loop():
    """Create new event loop with zmq selector."""
    from tulip import unix_events
    return unix_events.SelectorEventLoop(selector=ZmqSelector())
