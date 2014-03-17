# This relies on each of the submodules having an __all__ variable.
import warnings

from .core import *
from .selector import *
from .events import *
from .interface import *

__all__ = ['new_event_loop'] + (core.__all__ + selector.__all__ +
                                interface.__all__ + events.__all__)


__version__ = '0.0.2'


def new_event_loop():
    """Create new event loop with zmq selector."""
    warnings.warn(
        "This function will be removed in future versions.  "
        "Use 'asyncio.set_event_loop_policy(ZmqEventLoopPolicy()) instead.",
        DeprecationWarning, stacklevel=2
        )
    return ZmqEventLoop()
