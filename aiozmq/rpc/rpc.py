"""ZeroMQ RPC"""

import asyncio
import os
import random
import struct
import time
import sys

import zmq


from collections import ChainMap
from functools import partial

from aiozmq import create_zmq_connection

from .log import logger

from .base import (
    GenericError,
    NotFoundError,
    ParametersError,
    Service,
    ServiceClosedError,
    _BaseProtocol,
    _BaseServerProtocol,
    )
from .util import (
    _MethodCall,
    _fill_error_table,
    )


__all__ = [
    'connect_rpc',
    'serve_rpc',
    ]


@asyncio.coroutine
def connect_rpc(*, connect=None, bind=None, loop=None,
                error_table=None, translation_table=None, timeout=None):
    """A coroutine that creates and connects/binds RPC client.

    Usually for this function you need to use *connect* parameter, but
    ZeroMQ does not forbid to use *bind*.

    error_table -- an optional table for custom exception translators.

    timeout -- an optional timeout for RPC calls. If timeout is not
    None and remote call takes longer than timeout seconds then
    asyncio.TimeoutError will be raised at client side. If the server
    will return an answer after timeout has been raised that answer
    **is ignored**.

    translation_table -- an optional table for custom value translators.

    loop -- an optional parameter to point ZmqEventLoop instance.  If
    loop is None then default event loop will be given by
    asyncio.get_event_loop call.

    Returns a RPCClient instance.
    """
    if loop is None:
        loop = asyncio.get_event_loop()

    transp, proto = yield from create_zmq_connection(
        lambda: _ClientProtocol(loop, error_table=error_table,
                                translation_table=translation_table),
        zmq.DEALER, connect=connect, bind=bind, loop=loop)
    return RPCClient(loop, proto, timeout=timeout)


@asyncio.coroutine
def serve_rpc(handler, *, connect=None, bind=None, loop=None,
              translation_table=None, log_exceptions=False,
              exclude_log_exceptions=()):
    """A coroutine that creates and connects/binds RPC server instance.

    Usually for this function you need to use *bind* parameter, but
    ZeroMQ does not forbid to use *connect*.

    handler -- an object which processes incoming RPC calls.  Usually
               you like to pass AttrHandler instance.

    log_exceptions -- log exceptions from remote calls if True.

    exclude_log_exceptions -- sequence of exception classes than should not
                              be logged.

    translation_table -- an optional table for custom value translators.

    loop -- an optional parameter to point ZmqEventLoop instance.  If
            loop is None then default event loop will be given by
            asyncio.get_event_loop call.

    Returns Service instance.

    """
    if loop is None:
        loop = asyncio.get_event_loop()

    transp, proto = yield from create_zmq_connection(
        lambda: _ServerProtocol(loop, handler,
                                translation_table=translation_table,
                                log_exceptions=log_exceptions,
                                exclude_log_exceptions=exclude_log_exceptions),
        zmq.ROUTER, connect=connect, bind=bind, loop=loop)
    return Service(loop, proto)


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
        elif call.cancelled():
            logger.debug("The future for request #%08x has been cancelled, "
                         "skip the received result.", req_id)
        else:
            if is_error:
                call.set_exception(self._translate_error(*answer))
            else:
                call.set_result(answer)

    def connection_lost(self, exc):
        super().connection_lost(exc)
        for call in self.calls.values():
            if not call.cancelled():
                call.cancel()

    def _translate_error(self, exc_type, exc_args, exc_repr):
        found = self.error_table.get(exc_type)
        if found is None:
            return GenericError(exc_type, exc_args, exc_repr)
        else:
            return found(*exc_args)

    def _new_id(self):
        self.counter += 1
        if self.counter > 0xffffffff:
            self.counter = 0
        return (self.prefix + self.REQ_SUFFIX.pack(self.counter, time.time()),
                self.counter)

    def call(self, name, args, kwargs):
        if self.transport is None:
            raise ServiceClosedError()
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

    def __init__(self, loop, proto, *, timeout):
        super().__init__(loop, proto)
        self._timeout = timeout

    @property
    def call(self):
        """Return object for dynamic RPC calls.

        The usage is:
        ret = yield from client.call.ns.func(1, 2)
        """
        return _MethodCall(self._proto, timeout=self._timeout)

    def with_timeout(self, timeout):
        """Return a new RPCClient instance with overriden timeout"""
        return self.__class__(self._loop, self._proto, timeout=timeout)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        return


class _ServerProtocol(_BaseServerProtocol):

    REQ = struct.Struct('=HHLd')
    RESP_PREFIX = struct.Struct('=HH')
    RESP_SUFFIX = struct.Struct('=Ld?')

    def __init__(self, loop, handler, *,
                 translation_table=None, log_exceptions=False,
                 exclude_log_exceptions=()):
        super().__init__(loop, handler,
                         translation_table=translation_table,
                         log_exceptions=log_exceptions,
                         exclude_log_exceptions=exclude_log_exceptions)
        self.prefix = self.RESP_PREFIX.pack(os.getpid() % 0x10000,
                                            random.randrange(0x10000))

    def msg_received(self, data):
        try:
            *pre, header, bname, bargs, bkwargs = data
            pid, rnd, req_id, timestamp = self.REQ.unpack(header)

            name = bname.decode('utf-8')
            args = self.packer.unpackb(bargs)
            kwargs = self.packer.unpackb(bkwargs)
        except Exception as exc:
            logger.critical("Cannot unpack %r", data, exc_info=sys.exc_info())
            return
        try:
            func = self.dispatch(name)
            args, kwargs, ret_ann = self.check_args(func, args, kwargs)
        except (NotFoundError, ParametersError) as exc:
            fut = asyncio.Future(loop=self.loop)
            fut.add_done_callback(partial(self.process_call_result,
                                          req_id=req_id, pre=pre,
                                          name=name, args=args, kwargs=kwargs))
            fut.set_exception(exc)
        else:
            if asyncio.iscoroutinefunction(func):
                fut = asyncio.async(func(*args, **kwargs), loop=self.loop)
                self.pending_waiters.add(fut)
            else:
                fut = asyncio.Future(loop=self.loop)
                try:
                    fut.set_result(func(*args, **kwargs))
                except Exception as exc:
                    fut.set_exception(exc)
            fut.add_done_callback(partial(self.process_call_result,
                                          req_id=req_id, pre=pre,
                                          return_annotation=ret_ann,
                                          name=name,
                                          args=args,
                                          kwargs=kwargs))

    def process_call_result(self, fut, *, req_id, pre, name,
                            args, kwargs,
                            return_annotation=None):
        self.pending_waiters.discard(fut)
        self.try_log(fut, name, args, kwargs)
        if self.transport is None:
            return
        try:
            ret = fut.result()
            if return_annotation is not None:
                ret = return_annotation(ret)
            prefix = self.prefix + self.RESP_SUFFIX.pack(req_id,
                                                         time.time(), False)
            self.transport.write(pre + [prefix, self.packer.packb(ret)])
        except asyncio.CancelledError:
            return
        except Exception as exc:
            prefix = self.prefix + self.RESP_SUFFIX.pack(req_id,
                                                         time.time(), True)
            exc_type = exc.__class__
            exc_info = (exc_type.__module__ + '.' + exc_type.__name__,
                        exc.args, repr(exc))
            self.transport.write(pre + [prefix, self.packer.packb(exc_info)])
