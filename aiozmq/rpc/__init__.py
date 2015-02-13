"""ZeroMQ RPC/Pipeline/PubSub services"""

try:
    from msgpack import version as msgpack_version
except ImportError:  # pragma: no cover
    msgpack_version = (0,)

from .base import (
    method,
    AbstractHandler,
    AttrHandler,
    Error,
    GenericError,
    NotFoundError,
    ParametersError,
    ServiceClosedError,
    Service,
    )
from .rpc import (
    connect_rpc,
    serve_rpc,
    )
from .pipeline import (
    connect_pipeline,
    serve_pipeline,
    )
from .pubsub import (
    connect_pubsub,
    serve_pubsub,
    )

from .log import logger

_MSGPACK_VERSION = (0, 4, 0)
_MSGPACK_VERSION_STR = '.'.join(map(str, _MSGPACK_VERSION))

if msgpack_version < _MSGPACK_VERSION:  # pragma: no cover
    raise ImportError("aiozmq.rpc requires msgpack-python package"
                      " (version >= {})".format(_MSGPACK_VERSION_STR))


__all__ = [
    'method',
    'connect_rpc',
    'serve_rpc',
    'connect_pipeline',
    'serve_pipeline',
    'connect_pubsub',
    'serve_pubsub',
    'logger',
    'Error',
    'GenericError',
    'NotFoundError',
    'ParametersError',
    'AbstractHandler',
    'ServiceClosedError',
    'AttrHandler',
    'Service',
    ]
