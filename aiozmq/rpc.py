"""ZeroMQ RPC"""

import asyncio
import builtins
import zmq
import msgpack
import struct
import time
import sys

from . import events
from . import interface
from .log import logger

__all__ = [
    'Handler',
    'rpc',
    'open_client',
    'start_server',
    'RPCError',
    'GenericRPCError',
    'UnknownNamespace'
    ]


class RPCError(Exception):
    """Base RPC exception"""


class GenericRPCError(RPCError):
    """Error used for all untranslated exceptions from rpc method calls."""

    def __init__(self, exc_type, args):
        super().__init__(exc_type, args)
        self.exc_type = exc_type
        self.arguments = args


class RPCLookupError(RPCError):
    """Error raised by server when RPC namespace/method lookup failed."""


class UnknownNamespace(RPCLookupError):
    """RPC namespace not found."""


class UnknownMethod(RPCLookupError):
    """RPC method not found."""


class Handler:
    """Base class for server-side RPC handlers.

    Do not use metaclass to allowing easy multiple inheritance
    (can be used as mixin).
    Thereof checking for correctnes of RPC nested namespaces and
    methods is done at start_server call.
    """

    def __init__(self, subhandlers=None):
        if subhandlers is None:
            subhandlers = {}
        self.subhandlers = subhandlers
        self.rpc_methods = {}


def rpc(func):
    """Marks method as RPC endpoint handler.

    Also validates function params using annotations.
    """
    # TODO: fun with flag;
    #       parse annotations and create(?) checker;
    #       (also validate annotations);
    func.__rpc__ = {}  # TODO: assign to trafaret?
    return func


@asyncio.coroutine
def open_client(*, connect=None, bind=None, loop=None):
    """A coroutine that creates and connects/binds RPC client

    Return value is a client instance.
    """
    # TODO: describe params
    if loop is None:
        loop = asyncio.get_event_loop()

    transp, proto = yield from loop.create_zmq_connection(
        lambda: _ClientProtocol(loop), zmq.ROUTER, connect=connect, bind=bind)
    return _Client(proto)


class _ClientProtocol(interface.ZmqProtocol):
    """Client protocol implementation."""

    REQ_PREFIX = struct.Struct('HH')
    REQ_SUFFIX = struct.Struct('Ld')
    RESP = struct.Struct('HHLd?')

    def __init__(self, loop):
        self.loop = loop
        self.transport = None
        self.calls = {}
        self.prefix = self.REQ_PREFIX.pack('HH',
            os.getpid() % 65536, random.randrange(65536))
        self.counter = 0
        self.error_table = self._fill_error_table()

    def _fill_error_table(self):
        # Fill error table with standard exceptions
        error_table = {}
        for name in dir(builtins):
            val = getattr(builtins, name)
            if issubclass(val, Exception):
                error_table['builtins.'+name] = val
        return error_table

    def connection_made(self, transport):
        self.transport = transport

    def connection_lost(self, exc):
        self.transport = None

    def msg_received(self, data):
        try:
            header, packed_answer = data
            pid, rnd, req_id, timestamp, is_error = self.RESP.unpackb(header)
            answer = msgpack.unpackb(packed_answer,
                                     encoding='utf-8', use_list=True)
        except Exception as exc:
            logger.critical("Cannot unpack %r", data, exc_info=sys.exc_info())
            return
        call = self.calls.pop(req_id, None)
        if call is None:
            logger.critical("Unknown answer id: %d (%d %d %f %d) -> %s",
                            req_id, pid, rnd, timestamp, is_error, answer)
            return
        if iserror:
            call.set_exception(self._translate_error(answer))
        else:
            call.set_result(answer)

    def _translate_error(self, exc_type, exc_args):
        found = self.error_table.get(exc_type)
        if found is None:
            return GenericRPCError(exc_type, exc_args)
        else:
            return found(*exc_args)

    def _new_id(self):
        self.counter += 1
        if self.counter > 0xffffffff:
            self.counter = 0
        return (self.prefix + self.REQ_SUFFIX.pack(self.counter, time.time()),
                self.counter)

    def call(self, name, args, kwargs):
        packed_name = name.encode('utf-8')
        packed_args = msgpack.dumps(args)
        packed_kwargs = msgpack.dumps(kwargs)
        header, req_id = self._new_id()
        assert req_id not in self.calls, (req_id, self.calls)
        fut = asyncio.Future(loop=self.loop)
        self.calls[req_id] = fut
        self.transport.write([header, packed_name, packed_args, packed_kwargs])
        return fut


class _Client:
    def __init__(self, proto, names=()):
        self._proto = proto
        self._names = names

    def __getattr__(self, name):
        return self.__class__(connection, self._names + (name,))

    def __call__(self, *args, **kwargs):
        if not self._names:
            raise ValueError('RPC method name is empty')
        return self._proto.call('.'.join(self.names), args, kwargs)



@asyncio.coroutine
def start_server(handler, *, connect=None, bind=None, loop=None):
    """A coroutine that creates and connects/binds RPC server instance."""
    # TODO: describe params

    transp, proto = yield from loop.create_zmq_connection(
        lambda: _ServerProtocol(loop, handler),
        zmq.DEALER, connect=connect, bind=bind)

    return None


class _RPCServer(asyncio.AbstractServer):

    def __init__(self, loop, proto):
        self.loop = loop
        self.proto = proto

    def close(self):
        if self.proto.transport is None:
            return
        self.proto.transport.close()

    @task.coroutine
    def wait_closed(self):
        if self.proto.transport is None:
            return
        waiter = asyncio.Future(loop=self.loop)
        self.proto.done_waiters.append(waiter)
        yield from waiter


class _ServerProtocol(ZmqProtocol):

    REQ = struct.Struct('HHLd')
    RESP_PREFIX = struct.Struct('HH')
    RESP_SUFFIX = struct.Struct('Ld?')

    def __init__(self, loop, handler):
        self.loop = loop
        self.prepare_handler(handler)
        self.handler = handler
        self.done_waiters = []
        self.prefix = self.REQ_PREFIX.pack('HH',
            os.getpid() % 65536, random.randrange(65536))

    def prepare_handler(self, handler):
        # TODO: check handler and subhandlers for correctness
        # raise exception if needed
        pass

    def connection_made(self, transport):
        self.transport = transport

    def connection_lost(self, exc):
        self.transport = None
        for waiter in self.done_waiters:
            waiter.set_result(None)

    def msg_received(self, data):
        header, packed_name, packed_args, packed_kwargs = data
        pid, rnd, timestamp, req_id = self.REQ.unpack(header)

        # TODO: send exception back to transport if lookup is failed
        coro = self.dispatch(packed_name.decode('utf-8'))

        args = msgpack.unpackb(packed_args, encoding='utf-8', use_list=True)
        kwargs = msgpack.unpackb(packed_kwargs, encoding='utf-8', use_list=True)
        fut = asyncio.async(coro(*args, **kwargs), loop=self.loop)
        fut.add_done_callback(process_result)

        def process_result(res_fut):
            try:
                ret = res_fut.result()
                prefix = self.prefix + self.RESP_SUFFIX.pack(req_id,
                                                             time.time(), False)
                self.wransport.write([prefix, msgpack.packb(ret)])
            except Exception as exc:
                prefix = self.prefix + self.RESP_SUFFIX.pack(req_id,
                                                             time.time(), True)
                exc_type = exc.__class__
                exc_info = (exc_type.__module__ + '.' + exc_type.__name__,
                            exc.args)
                self.transport.write([prefix, msgpack.packb(exc_info)])

    def dispatch(self, name):
        namespaces, sep, method = name.rpartition('.')
        handler = self.handler
        for namespace in namespaces:
            try:
                handler = handler.subhandlers[namespace]
            except KeyError:
                raise UnknownNamespace(name)

        try:
            func = handler.rpc_methods[method]
        except KeyError:
            raise UnknownMethod(name)
        else:
            # TODO: validate trafaret
            return func
