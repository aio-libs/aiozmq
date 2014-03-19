import asyncio
import zmq
import msgpack

from . import events
from . import interface

__all__ = [
    'ns',
    'method',
    'make_client',
    'make_server',
    ]


def ns(obj):
    """ Marks object as RPC namespace """
    return obj


def method(fun):
    """ Marks method as RPC endpoint handler.

    Also validates function params using annotations.
    """
    # TODO: fun with flag;
    #       parse annotations and create(?) checker;
    #       (also validate annotations);
    return fun

# TODO: make exceptions classes


@asyncio.coroutine
def make_client(connect=None, bind=None, *, loop=None):
    """A coroutine that creates and connects/binds RPC client

    Return value is a client instance.
    """
    # TODO: describe params
    if connect and bind:
        raise ValueError("Either connect or bind must be specified, not both")
    if not connect and not bind:
        raise ValueError("Either connect or bind must be specified")

    client = _Client(loop=loop)
    if connect:
        yield from client.connect(connect)
    else:
        yield from client.bind(bind)
    return client


@asyncio.coroutine
def make_server(handler, connect, bind, *, loop=None):
    """A coroutine that creates and connects/binds RPC server instance
    """
    # TODO: describe params
    if connect and bind:
        raise ValueError("Either connect or bind must be specified, not both")
    if not connect and not bind:
        raise ValueError("Either connect or bind must be specified")

    server = _Server(handler, loop=loop)
    if connect:
        yield from server.connect(connect)
    else:
        yield from server.bind(bind)
    return server


# TODO: implement protocol -- two parts:
#           read & write
#           ie: decode msg & encode msg


class ClientProtocol(interface.ZmqProtocol):
    """Client protocol implementation
    """

    def msg_received(self, data, *multipart):
        try:
            unpacked = msgpack.loads(data, encoding='utf-8', use_list=True)
        except ValueError as err:
            pass



# TODO: get rid of _Client; do all this in make_client
#       and return ResourceWrapper
#       do the same with _Server
class _Client:
    """ZeroMQ RPC Client
    """

    def __init__(self, loop=None):
        if loop is None:
            loop = events.ZmqEventLoop()
        self._loop = loop

    @asyncio.coroutine
    def connect(self, connect):
        create = self._loop.create_zmq_connection
        transport, protocol = yield from create(ClientProtocol,
                                                zmq_type=zmq.DEALER,
                                                connect=connect)
        self._transport = transport
        self._protocol = protocol

    @asyncio.coroutine
    def bind(self, bind):
        create = self._loop.create_zmq_connection
        transport, protocol = yield from create(ClientProtocol,
                                                zmq_type=zmq.DEALER,
                                                bind=bind)
        self._transport = transport
        self._protocol = protocol

    def __getattr__(self, name):
        pass
        # make and return wrapper;


class _Server:
    """ZeroMQ RPC Server
    """

    def __init__(self, handler *, loop=None):
        if loop is None:
            loop = events.ZmqEventLoop()
        self._loop = loop
        self._handler = handler

    @asyncio.coroutine
    def connect(self, connect):
        pass

    @asyncio.coroutine
    def bind(self, bind):
        pass

    def run(self):
        pass
        # listen for connections;


class ResourceWrapper:

    def __init__(self):
        pass

    def __getattr__(self, name):
        pass

    def __call__(self, *agrs, **kwargs):
        pass
