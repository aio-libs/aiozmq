import abc
import asyncio
import inspect
import pprint
import textwrap
from types import MethodType

from .log import logger
from .packer import _Packer
from aiozmq import interface

if hasattr(asyncio, "ensure_future"):
    ensure_future = asyncio.ensure_future
else:  # Deprecated since Python version 3.4.4.
    ensure_future = getattr(asyncio, "async")


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
        return "<Generic RPC Error {}{}: {}>".format(
            self.exc_type, self.arguments, self.exc_repr
        )


class NotFoundError(Error, LookupError):
    """Error raised by server if RPC namespace/method lookup failed."""


class ParametersError(Error, ValueError):
    """Error raised by server when RPC method's parameters could not
    be validated against the signature."""


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
    """Marks a decorated function as an RPC endpoint handler."""
    func.__rpc__ = {}
    func.__signature__ = inspect.signature(func)
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
        if self._proto.closing:
            return
        self._proto.closing = True
        if self._proto.transport is None:
            return
        self._proto.transport.close()

    async def wait_closed(self):
        if self._proto.transport is None:
            return
        waiter = asyncio.Future(loop=self._loop)
        self._proto.done_waiters.append(waiter)
        await waiter


class _BaseProtocol(interface.ZmqProtocol):
    def __init__(self, loop, *, translation_table=None):
        self.loop = loop
        self.transport = None
        self.done_waiters = []
        self.packer = _Packer(translation_table=translation_table)
        self.pending_waiters = set()
        self.closing = False

    def connection_made(self, transport):
        self.transport = transport

    def connection_lost(self, exc):
        self.transport = None
        for waiter in self.done_waiters:
            waiter.set_result(None)


class _BaseServerProtocol(_BaseProtocol):
    def __init__(
        self,
        loop,
        handler,
        *,
        translation_table=None,
        log_exceptions=False,
        exclude_log_exceptions=(),
        timeout=None
    ):
        super().__init__(loop, translation_table=translation_table)
        if not isinstance(handler, AbstractHandler):
            raise TypeError("handler must implement AbstractHandler")
        self.handler = handler
        self.log_exceptions = log_exceptions
        self.exclude_log_exceptions = exclude_log_exceptions
        self.timeout = timeout

    def connection_lost(self, exc):
        super().connection_lost(exc)
        for waiter in list(self.pending_waiters):
            if not waiter.cancelled():
                waiter.cancel()

    def dispatch(self, name):
        if not name:
            raise NotFoundError(name)
        namespaces, sep, method = name.rpartition(".")
        handler = self.handler
        if namespaces:
            for part in namespaces.split("."):
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
            if not hasattr(holder, "__rpc__"):
                raise NotFoundError(name)
            return func

    def check_args(self, func, args, kwargs):
        """Utility function for validating function arguments

        Returns validated (args, kwargs) tuple
        """
        try:
            sig = inspect.signature(func)
            bargs = sig.bind(*args, **kwargs)
        except TypeError as exc:
            raise ParametersError(repr(exc)) from exc
        else:
            return bargs.args, bargs.kwargs

    def try_log(self, fut, name, args, kwargs):
        try:
            fut.result()
        except Exception as exc:
            if self.log_exceptions:
                for e in self.exclude_log_exceptions:
                    if isinstance(exc, e):
                        return
                logger.exception(
                    textwrap.dedent(
                        """\
                    An exception %r from method %r call occurred.
                    args = %s
                    kwargs = %s
                    """
                    ),
                    exc,
                    name,
                    pprint.pformat(args),
                    pprint.pformat(kwargs),
                )  # noqa

    def add_pending(self, coro):
        fut = ensure_future(coro)
        self.pending_waiters.add(fut)
        return fut

    def discard_pending(self, fut):
        self.pending_waiters.discard(fut)
