import abc
import asyncio
import inspect
import pprint
import textwrap

from aiozmq import interface
from types import MethodType

from .packer import _Packer
from .log import logger


class Error(Exception):
    """Base RPC exception"""


class GenericError(Error):
    """Error for all untranslated exceptions from rpc method calls."""

    def __init__(self, exc_type, args, exc_repr):
        super().__init__(exc_type, args, exc_repr)
        self.exc_type = exc_type
        self.arguments = args
        self.exc_repr = exc_repr

    def __repr__(self):
        return '<Generic RPC Error {}{}: {}>'.format(self.exc_type,
                                                     self.arguments,
                                                     self.exc_repr)


class NotFoundError(Error, LookupError):
    """Error raised by server if RPC namespace/method lookup failed."""


class ParametersError(Error, ValueError):
    """Error raised by server when RPC method's parameters could not
    be validated against their annotations."""


class ServiceClosedError(Error):
    """RPC Service is closed."""


class AbstractHandler(metaclass=abc.ABCMeta):
    """Abstract class for server-side RPC handlers."""

    __slots__ = ()

    @abc.abstractmethod
    def __getitem__(self, key):
        raise KeyError

    @classmethod
    def __subclasshook__(cls, C):
        if issubclass(C, (str, bytes)):
            return False
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
    """Marks a decorated function as RPC endpoint handler.

    The func object may provide arguments and/or return annotations.
    If so annotations should be callable objects and
    they will be used to validate received arguments and/or return value.
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
        self._closing = False

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
        if self._closing:
            return
        self._closing = True
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


class _BaseProtocol(interface.ZmqProtocol):

    def __init__(self, loop, *, translation_table=None):
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


class _BaseServerProtocol(_BaseProtocol):

    def __init__(self, loop, handler, *,
                 translation_table=None, log_exceptions=False,
                 exclude_log_exceptions=()):
        super().__init__(loop, translation_table=translation_table)
        if not isinstance(handler, AbstractHandler):
            raise TypeError('handler must implement AbstractHandler ABC')
        self.handler = handler
        self.log_exceptions = log_exceptions
        self.exclude_log_exceptions = exclude_log_exceptions
        self.pending_waiters = set()

    def connection_lost(self, exc):
        super().connection_lost(exc)
        for waiter in list(self.pending_waiters):
            if not waiter.cancelled():
                waiter.cancel()

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

    def check_args(self, func, args, kwargs):
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
            marker = object()
            for name, param in sig.parameters.items():
                if param.annotation is param.empty:
                    continue
                val = arguments.get(name, marker)
                if val is marker:
                    continue  # Skip default value
                try:
                    arguments[name] = param.annotation(val)
                except (TypeError, ValueError) as exc:
                    raise ParametersError(
                        'Invalid value for argument {!r}: {!r}'
                        .format(name, exc)) from exc
            if sig.return_annotation is not sig.empty:
                return bargs.args, bargs.kwargs, sig.return_annotation
            return bargs.args, bargs.kwargs, None

    def try_log(self, fut, name, args, kwargs):
        try:
            fut.result()
        except Exception as exc:
            if self.log_exceptions:
                for e in self.exclude_log_exceptions:
                    if isinstance(exc, e):
                        return
                logger.exception(textwrap.dedent("""\
                    An exception from method %r call occurred.
                    args = %s
                    kwargs = %s
                    """),
                    name, pprint.pformat(args), pprint.pformat(kwargs))  # noqa
