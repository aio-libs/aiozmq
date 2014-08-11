import asyncio
import zmq
from functools import partial
from collections import Iterable

from aiozmq import create_zmq_connection

from .log import logger
from .base import (
    NotFoundError,
    ParametersError,
    Service,
    ServiceClosedError,
    _BaseProtocol,
    _BaseServerProtocol,
    )


@asyncio.coroutine
def connect_pubsub(*, connect=None, bind=None, loop=None,
                   translation_table=None):
    """A coroutine that creates and connects/binds pubsub client.

    Usually for this function you need to use connect parameter, but
    ZeroMQ does not forbid to use bind.

    translation_table -- an optional table for custom value translators.

    loop -- an optional parameter to point ZmqEventLoop.  If loop is
            None then default event loop will be given by
            asyncio.get_event_loop() call.

    Returns PubSubClient instance.

    """
    if loop is None:
        loop = asyncio.get_event_loop()

    transp, proto = yield from create_zmq_connection(
        lambda: _ClientProtocol(loop, translation_table=translation_table),
        zmq.PUB, connect=connect, bind=bind, loop=loop)
    return PubSubClient(loop, proto)


@asyncio.coroutine
def serve_pubsub(handler, *, subscribe=None, connect=None, bind=None,
                 loop=None, translation_table=None, log_exceptions=False,
                 exclude_log_exceptions=()):
    """A coroutine that creates and connects/binds pubsub server instance.

    Usually for this function you need to use *bind* parameter, but
    ZeroMQ does not forbid to use *connect*.

    handler -- an object which processes incoming pipeline calls.
               Usually you like to pass AttrHandler instance.

    log_exceptions -- log exceptions from remote calls if True.

    subscribe -- subscription specification.  Subscribe server to
                 topics.  Allowed parameters are str, bytes, iterable
                 of str or bytes.

    translation_table -- an optional table for custom value translators.

    exclude_log_exceptions -- sequence of exception classes than should not
                              be logged.

    loop -- an optional parameter to point ZmqEventLoop.  If loop is
            None then default event loop will be given by
            asyncio.get_event_loop() call.

    Returns PubSubService instance.
    Raises OSError on system error.
    Raises TypeError if arguments have inappropriate type.

    """
    if loop is None:
        loop = asyncio.get_event_loop()

    transp, proto = yield from create_zmq_connection(
        lambda: _ServerProtocol(loop, handler,
                                translation_table=translation_table,
                                log_exceptions=log_exceptions,
                                exclude_log_exceptions=exclude_log_exceptions),
        zmq.SUB, connect=connect, bind=bind, loop=loop)
    serv = PubSubService(loop, proto)
    if subscribe is not None:
        if isinstance(subscribe, (str, bytes)):
            subscribe = [subscribe]
        else:
            if not isinstance(subscribe, Iterable):
                raise TypeError('bind should be str, bytes or iterable')
        for topic in subscribe:
            serv.subscribe(topic)
    return serv


class _ClientProtocol(_BaseProtocol):

    def call(self, topic, name, args, kwargs):
        if self.transport is None:
            raise ServiceClosedError()
        if topic is None:
            btopic = b''
        elif isinstance(topic, str):
            btopic = topic.encode('utf-8')
        elif isinstance(topic, bytes):
            btopic = topic
        else:
            raise TypeError('topic argument should be None, str or bytes '
                            '({!r})'.format(topic))
        bname = name.encode('utf-8')
        bargs = self.packer.packb(args)
        bkwargs = self.packer.packb(kwargs)
        self.transport.write([btopic, bname, bargs, bkwargs])
        fut = asyncio.Future(loop=self.loop)
        fut.set_result(None)
        return fut


class PubSubClient(Service):

    def __init__(self, loop, proto):
        super().__init__(loop, proto)

    def publish(self, topic):
        """Return object for dynamic PubSub calls.

        The usage is:
        yield from client.publish('my_topic').ns.func(1, 2)

        topic argument may be None otherwise must be isntance of str or bytes
        """
        return _MethodCall(self._proto, topic)


class PubSubService(Service):

    def subscribe(self, topic):
        """Subscribe to the topic.

        topic argument must be str or bytes.
        Raises TypeError in other cases
        """
        if isinstance(topic, bytes):
            btopic = topic
        elif isinstance(topic, str):
            btopic = topic.encode('utf-8')
        else:
            raise TypeError('topic should be str or bytes, got {!r}'
                            .format(topic))
        self.transport.subscribe(btopic)

    def unsubscribe(self, topic):
        """Unsubscribe from the topic.

        topic argument must be str or bytes.
        Raises TypeError in other cases
        """
        if isinstance(topic, bytes):
            btopic = topic
        elif isinstance(topic, str):
            btopic = topic.encode('utf-8')
        else:
            raise TypeError('topic should be str or bytes, got {!r}'
                            .format(topic))
        self.transport.unsubscribe(btopic)


class _MethodCall:

    __slots__ = ('_proto', '_topic', '_names')

    def __init__(self, proto, topic, names=()):
        self._proto = proto
        self._topic = topic
        self._names = names

    def __getattr__(self, name):
        return self.__class__(self._proto, self._topic,
                              self._names + (name,))

    def __call__(self, *args, **kwargs):
        if not self._names:
            raise ValueError("PubSub method name is empty")
        return self._proto.call(self._topic, '.'.join(self._names),
                                args, kwargs)


class _ServerProtocol(_BaseServerProtocol):

    def msg_received(self, data):
        btopic, bname, bargs, bkwargs = data

        args = self.packer.unpackb(bargs)
        kwargs = self.packer.unpackb(bkwargs)
        try:
            name = bname.decode('utf-8')
            func = self.dispatch(name)
            args, kwargs, ret_ann = self.check_args(func, args, kwargs)
        except (NotFoundError, ParametersError) as exc:
            fut = asyncio.Future(loop=self.loop)
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
                                      name=name, args=args, kwargs=kwargs))

    def process_call_result(self, fut, *, name, args, kwargs):
        self.pending_waiters.discard(fut)
        try:
            if fut.result() is not None:
                logger.warning("PubSub handler %r returned not None", name)
        except asyncio.CancelledError:
            return
        except (NotFoundError, ParametersError) as exc:
            logger.exception("Call to %r caused error: %r", name, exc)
        except Exception:
            self.try_log(fut, name, args, kwargs)
