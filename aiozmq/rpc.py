"""ZeroMQ RPC"""

import abc
import asyncio
import builtins
import os
import random
import struct
import time
import sys
import inspect

import zmq


from collections import ChainMap
from functools import partial
from types import MethodType

from . import interface
from .log import logger

try:
    from .util import _Packer
except ImportError:  # pragma: no cover
    raise ImportError("aiozmq.rpc requires msgpack-python package.")


__all__ = [
    'method',
    'open_client',
    'start_server',
    'Error',
    'GenericError',
    'NotFoundError',
    'AbstractHandler',
    'AttrHandler'
    ]


class Error(Exception):
    """Base RPC exception"""


class GenericError(Error):
    """Error used for all untranslated exceptions from rpc method calls."""

    def __init__(self, exc_type, args):
        super().__init__(exc_type, args)
        self.exc_type = exc_type
        self.arguments = args


class NotFoundError(Error, LookupError):
    """Error raised by server if RPC namespace/method lookup failed."""


class ParametersError(Error, ValueError):
    """Error raised by server when RPC method's parameters could not
    be validated against their annotations."""


class ServiceClosedError(Exception):
    """RPC Service has been closed."""


class AbstractHandler(metaclass=abc.ABCMeta):
    """Abstract class for server-side RPC handlers."""

    __slots__ = ()

    @abc.abstractmethod
    def __getitem__(self, key):
        raise KeyError

    @classmethod
    def __subclasshook__(cls, C):
        if cls is AbstractHandler:
            if any("__getitem__" in B.__dict__ for B in C.__mro__):
                return True
        return NotImplemented


class AttrHandler(AbstractHandler):
    """Base class for RPC handlers via attribute lookup."""

    def __getitem__(self, key):
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError


def method(func):
    """Marks method as RPC endpoint handler.

    The func object may provide arguments and/or return annotations.
    If so annotations should be callable objects and
    they will be used to validate received arguments and/or return value
    """
    func.__rpc__ = {}
    func.__signature__ = sig = inspect.signature(func)
    for name, param in sig.parameters.items():
        ann = param.annotation
        if ann is not param.empty and not callable(ann):
            raise ValueError("Expected {!r} annotation to be callable"
                             .format(name))
    ann = sig.return_annotation
    if ann is not sig.empty and not callable(ann):
        raise ValueError("Expected return annotation to be callable")
    return func


@asyncio.coroutine
def open_client(*, connect=None, bind=None, loop=None,
                error_table=None, translation_table=None):
    """A coroutine that creates and connects/binds RPC client.

    Return value is a client instance.
    """
    # TODO: describe params
    # TODO: add a way to pass exception translator
    # TODO: add a way to pass value translator
    if loop is None:
        loop = asyncio.get_event_loop()

    transp, proto = yield from loop.create_zmq_connection(
        lambda: _ClientProtocol(loop, error_table=error_table,
                                translation_table=translation_table),
        zmq.DEALER, connect=connect, bind=bind)
    return RPCClient(loop, proto)


@asyncio.coroutine
def start_server(handler, *, connect=None, bind=None, loop=None,
                 translation_table=None):
    """A coroutine that creates and connects/binds RPC server instance."""
    # TODO: describe params
    # TODO: add a way to pass value translator
    if loop is None:
        loop = asyncio.get_event_loop()

    transp, proto = yield from loop.create_zmq_connection(
        lambda: _ServerProtocol(loop, handler, translation_table),
        zmq.ROUTER, connect=connect, bind=bind)
    return Service(loop, proto)


class _BaseProtocol(interface.ZmqProtocol):

    def __init__(self, loop, translation_table=None):
        self.loop = loop
        self.transport = None
        self.done_waiters = []
        self.packer = _Packer(translation_table=translation_table)

    def connection_made(self, transport):
        self.transport = transport

    def connection_lost(self, exc):
        self.transport = None
        for waiter in self.done_waiters:
            waiter.set_result(None)


class Service(asyncio.AbstractServer):
    """RPC service.

    Instances of Service (or
    descendants) are returned by coroutines that creates clients or
    servers.

    Implementation of AbstractServer.
    """

    def __init__(self, loop, proto):
        self._loop = loop
        self._proto = proto

    @property
    def transport(self):
        """Return the transport.

        You can use the transport to dynamically bind/unbind,
        connect/disconnect etc.
        """
        transport = self._proto.transport
        if transport is None:
            raise ServiceClosedError()
        return transport

    def close(self):
        if self._proto.transport is None:
            return
        self._proto.transport.close()

    @asyncio.coroutine
    def wait_closed(self):
        if self._proto.transport is None:
            return
        waiter = asyncio.Future(loop=self._loop)
        self._proto.done_waiters.append(waiter)
        yield from waiter


def _fill_error_table():
    # Fill error table with standard exceptions
    error_table = {}
    for name in dir(builtins):
        val = getattr(builtins, name)
        if isinstance(val, type) and issubclass(val, Exception):
            error_table['builtins.'+name] = val
    error_table[__name__ + '.NotFoundError'] = NotFoundError
    error_table[__name__ + '.ParametersError'] = ParametersError
    return error_table


_default_error_table = _fill_error_table()


class _ClientProtocol(_BaseProtocol):
    """Client protocol implementation."""

    REQ_PREFIX = struct.Struct('=HH')
    REQ_SUFFIX = struct.Struct('=Ld')
    RESP = struct.Struct('=HHLd?')

    def __init__(self, loop, *, error_table=None, translation_table=None):
        super().__init__(loop, translation_table=translation_table)
        self.calls = {}
        self.prefix = self.REQ_PREFIX.pack(os.getpid() % 0x10000,
                                           random.randrange(0x10000))
        self.counter = 0
        if error_table is None:
            self.error_table = _default_error_table
        else:
            self.error_table = ChainMap(error_table, _default_error_table)

    def msg_received(self, data):
        try:
            header, banswer = data
            pid, rnd, req_id, timestamp, is_error = self.RESP.unpack(header)
            answer = self.packer.unpackb(banswer)
        except Exception:
            logger.critical("Cannot unpack %r", data, exc_info=sys.exc_info())
            return
        call = self.calls.pop(req_id, None)
        if call is None:
            logger.critical("Unknown answer id: %d (%d %d %f %d) -> %s",
                            req_id, pid, rnd, timestamp, is_error, answer)
            return
        if is_error:
            call.set_exception(self._translate_error(*answer))
        else:
            call.set_result(answer)

    def _translate_error(self, exc_type, exc_args):
        found = self.error_table.get(exc_type)
        if found is None:
            return GenericError(exc_type, tuple(exc_args))
        else:
            return found(*exc_args)

    def _new_id(self):
        self.counter += 1
        if self.counter > 0xffffffff:
            self.counter = 0
        return (self.prefix + self.REQ_SUFFIX.pack(self.counter, time.time()),
                self.counter)

    def call(self, name, args, kwargs):
        bname = name.encode('utf-8')
        bargs = self.packer.packb(args)
        bkwargs = self.packer.packb(kwargs)
        header, req_id = self._new_id()
        assert req_id not in self.calls, (req_id, self.calls)
        fut = asyncio.Future(loop=self.loop)
        self.calls[req_id] = fut
        self.transport.write([header, bname, bargs, bkwargs])
        return fut


class RPCClient(Service):

    def __init__(self, loop, proto):
        super().__init__(loop, proto)

    @property
    def rpc(self):
        """Return object for dynamic RPC calls.

        The usage is:
        ret = yield from client.rpc.ns.func(1, 2)
        """
        return _MethodCall(self._proto)


class _MethodCall:

    __slots__ = ('_proto', '_names')

    def __init__(self, proto, names=()):
        self._proto = proto
        self._names = names

    def __getattr__(self, name):
        return self.__class__(self._proto, self._names + (name,))

    def __call__(self, *args, **kwargs):
        if not self._names:
            raise ValueError('RPC method name is empty')
        return self._proto.call('.'.join(self._names), args, kwargs)


class _ServerProtocol(_BaseProtocol):

    REQ = struct.Struct('=HHLd')
    RESP_PREFIX = struct.Struct('=HH')
    RESP_SUFFIX = struct.Struct('=Ld?')

    def __init__(self, loop, handler, translation_table=None):
        super().__init__(loop, translation_table)
        self.prepare_handler(handler)
        self.handler = handler
        self.prefix = self.RESP_PREFIX.pack(os.getpid() % 0x10000,
                                            random.randrange(0x10000))

    def prepare_handler(self, handler):
        # TODO: check handler and subhandlers for correctness
        # raise exception if needed
        pass

    def msg_received(self, data):
        peer, header, bname, bargs, bkwargs = data
        pid, rnd, req_id, timestamp = self.REQ.unpack(header)

        # TODO: send exception back to transport if lookup is failed
        args = self.packer.unpackb(bargs)
        kwargs = self.packer.unpackb(bkwargs)
        try:
            func = self.dispatch(bname.decode('utf-8'))
            args, kwargs, ret_ann = _check_func_arguments(func, args, kwargs)
        except (NotFoundError, ParametersError) as exc:
            fut = asyncio.Future(loop=self.loop)
            fut.add_done_callback(partial(self.process_call_result,
                                          req_id=req_id, peer=peer))
            fut.set_exception(exc)
        else:
            if asyncio.iscoroutinefunction(func):
                fut = asyncio.async(func(*args, **kwargs), loop=self.loop)
                fut.add_done_callback(partial(self.process_call_result,
                                              req_id=req_id, peer=peer,
                                              return_annotation=ret_ann))
            else:
                fut = asyncio.Future(loop=self.loop)
                fut.add_done_callback(partial(self.process_call_result,
                                              req_id=req_id, peer=peer,
                                              return_annotation=ret_ann))
                try:
                    fut.set_result(func(*args, **kwargs))
                except Exception as exc:
                    fut.set_exception(exc)

    def process_call_result(self, fut, *, req_id, peer,
                            return_annotation=None):
        try:
            ret = fut.result()
            # TODO: allow `ret` to be validated against None
            if return_annotation is not None:
                ret = return_annotation(ret)
            prefix = self.prefix + self.RESP_SUFFIX.pack(req_id,
                                                         time.time(), False)
            self.transport.write([peer, prefix, self.packer.packb(ret)])
        except Exception as exc:
            prefix = self.prefix + self.RESP_SUFFIX.pack(req_id,
                                                         time.time(), True)
            exc_type = exc.__class__
            exc_info = (exc_type.__module__ + '.' + exc_type.__name__,
                        exc.args)
            self.transport.write([peer, prefix, self.packer.packb(exc_info)])

    def dispatch(self, name):
        if not name:
            raise NotFoundError(name)
        namespaces, sep, method = name.rpartition('.')
        handler = self.handler
        if namespaces:
            for part in namespaces.split('.'):
                try:
                    handler = handler[part]
                except KeyError:
                    raise NotFoundError(name)
                else:
                    if not isinstance(handler, AbstractHandler):
                        raise NotFoundError(name)

        try:
            func = handler[method]
        except KeyError:
            raise NotFoundError(name)
        else:
            if isinstance(func, MethodType):
                holder = func.__func__
            else:
                holder = func
            if not hasattr(holder, '__rpc__'):
                raise NotFoundError(name)
            return func


def _check_func_arguments(func, args, kwargs):
    """Utility function for validating function arguments

    Returns validated (args, kwargs, return annotation) tuple
    """
    try:
        sig = inspect.signature(func)
        bargs = sig.bind(*args, **kwargs)
    except TypeError as exc:
        raise ParametersError(repr(exc)) from exc
    else:
        arguments = bargs.arguments
        for name, param in sig.parameters.items():
            if param.annotation is param.empty:
                continue
            val = arguments.get(name, param.default)
            # NOTE: default value always being passed through annotation
            #       is it realy neccessary?
            try:
                arguments[name] = param.annotation(val)
            except (TypeError, ValueError) as exc:
                raise ParametersError('Invalid value for argument {!r}: {!r}'
                                      .format(name, exc)) from exc
        if sig.return_annotation is not sig.empty:
            return bargs.args, bargs.kwargs, sig.return_annotation
        return bargs.args, bargs.kwargs, None
