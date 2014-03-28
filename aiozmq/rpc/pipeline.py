import asyncio
import zmq

from functools import partial

from aiozmq.log import logger

from .base import (
    NotFoundError,
    ParametersError,
    AbstractHandler,
    Service,
    _BaseProtocol,
    )
from .util import (
    _MethodCall,
    _MethodDispatcher,
    _check_func_arguments,
    )


@asyncio.coroutine
def connect_pipeline(*, connect=None, bind=None, loop=None,
                     translation_table=None):
    """A coroutine that creates and connects/binds Pipeline client instance."""
    if loop is None:
        loop = asyncio.get_event_loop()

    transp, proto = yield from loop.create_zmq_connection(
        lambda: _ClientProtocol(loop, translation_table),
        zmq.PUSH, connect=connect, bind=bind)
    return PipelineClient(loop, proto)


@asyncio.coroutine
def serve_pipeline(handler, *, connect=None, bind=None, loop=None,
                   translation_table=None):
    """A coroutine that creates and connects/binds Pipeline server instance."""
    if loop is None:
        loop = asyncio.get_event_loop()

    trans, proto = yield from loop.create_zmq_connection(
        lambda: _ServerProtocol(loop, handler, translation_table),
        zmq.PULL, connect=connect, bind=bind)
    return Service(loop, proto)


class _ClientProtocol(_BaseProtocol):

    def call(self, name, args, kwargs):
        bname = name.encode('utf-8')
        bargs = self.packer.packb(args)
        bkwargs = self.packer.packb(kwargs)
        self.transport.write([bname, bargs, bkwargs])
        fut = asyncio.Future(loop=self.loop)
        fut.set_result(None)
        return fut


class PipelineClient(Service):

    def __init__(self, loop, proto):
        super().__init__(loop, proto)

    @property
    def notify(self):
        """Return object for dynamic Pipeline calls.

        The usage is:
        yield from client.pipeline.ns.func(1, 2)
        """
        return _MethodCall(self._proto)


class _ServerProtocol(_BaseProtocol, _MethodDispatcher):

    def __init__(self, loop, handler, translation_table=None):
        super().__init__(loop, translation_table=translation_table)
        if not isinstance(handler, AbstractHandler):
            raise TypeError('handler should implement AbstractHandler ABC')
        self.handler = handler

    def msg_received(self, data):
        bname, bargs, bkwargs = data

        args = self.packer.unpackb(bargs)
        kwargs = self.packer.unpackb(bkwargs)
        try:
            name = bname.decode('utf-8')
            func = self.dispatch(name)
            args, kwargs, ret_ann = _check_func_arguments(func, args, kwargs)
        except (NotFoundError, ParametersError) as exc:
            fut = asyncio.Future(loop=self.loop)
            fut.add_done_callback(partial(self.process_call_result,
                                          name=name))
            fut.set_exception(exc)
        else:
            if asyncio.iscoroutinefunction(func):
                fut = asyncio.async(func(*args, **kwargs), loop=self.loop)
                fut.add_done_callback(partial(self.process_call_result,
                                              name=name))
            else:
                fut = asyncio.Future(loop=self.loop)
                fut.add_done_callback(partial(self.process_call_result,
                                              name=name))
                try:
                    fut.set_result(func(*args, **kwargs))
                except Exception as exc:
                    fut.set_exception(exc)

    def process_call_result(self, fut, *, name):
        try:
            if fut.result() is not None:
                logger.warn("Pipeline handler %r returned not None", name)
        except Exception as exc:
            self.loop.call_exception_handler({
                'message': 'Call to {!r} caused error: {!r}'.format(name, exc),
                'exception': exc,
                'future': fut,
                'protocol': self,
                'transport': self.transport,
                })
