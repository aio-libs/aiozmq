import re
import sys
from collections import namedtuple

import zmq

from .core import ZmqEventLoop, ZmqEventLoopPolicy, create_zmq_connection
from .interface import ZmqTransport, ZmqProtocol
from .selector import ZmqSelector
from .stream import (ZmqStream, ZmqStreamProtocol, ZmqStreamClosed,
                     create_zmq_stream)


__all__ = ('ZmqSelector', 'ZmqEventLoop', 'ZmqEventLoopPolicy',
           'ZmqTransport', 'ZmqProtocol',
           'ZmqStream', 'ZmqStreamProtocol', 'create_zmq_stream',
           'ZmqStreamClosed',
           'create_zmq_connection',
           'version_info', 'version')

__version__ = '0.6.0'

version = __version__ + ' , Python ' + sys.version


VersionInfo = namedtuple('VersionInfo',
                         'major minor micro releaselevel serial')


def _parse_version(ver):
    RE = (r'^(?P<major>\d+)\.(?P<minor>\d+)\.'
          '(?P<micro>\d+)((?P<releaselevel>[a-z]+)(?P<serial>\d+)?)?$')
    match = re.match(RE, ver)
    try:
        major = int(match.group('major'))
        minor = int(match.group('minor'))
        micro = int(match.group('micro'))
        levels = {'c': 'candidate',
                  'a': 'alpha',
                  'b': 'beta',
                  None: 'final'}
        releaselevel = levels[match.group('releaselevel')]
        serial = int(match.group('serial')) if match.group('serial') else 0
        return VersionInfo(major, minor, micro, releaselevel, serial)
    except Exception:
        raise ImportError("Invalid package version {}".format(ver))


version_info = _parse_version(__version__)


if zmq.zmq_version_info()[0] < 3:  # pragma no cover
    raise ImportError("aiozmq doesn't support libzmq < 3.0")


# make pyflakes happy
(ZmqSelector, ZmqEventLoop, ZmqEventLoopPolicy, ZmqTransport, ZmqProtocol,
 ZmqStream, ZmqStreamProtocol, ZmqStreamClosed, create_zmq_stream,
 create_zmq_connection)
