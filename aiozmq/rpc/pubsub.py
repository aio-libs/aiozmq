import asyncio
import zmq
from functools import partial
from collections import Iterable

from ..log import logger
from .base import (
    NotFoundError,
    ParametersError,
    AbstractHandler,
    Service,
    _BaseProtocol,
    )
from .util import (
    _MethodDispatcher,
    _check_func_arguments,
    )


@asyncio.coroutine
def connect_pubsub(*, connect=None, bind=None, loop=None,
                   translation_table=None):
    if loop is None:
        loop = asyncio.get_event_loop()

    transp, proto = yield from loop.create_zmq_connection(
        lambda: _ClientProtocol(loop, translation_table=translation_table),
        zmq.PUB, connect=connect, bind=bind)
    return PubSubClient(loop, proto)


@asyncio.coroutine
def serve_pubsub(handler, *, subscribe=None, connect=None, bind=None,
                 loop=None, translation_table=None):
    if loop is None:
        loop = asyncio.get_event_loop()

    transp, proto = yield from loop.create_zmq_connection(
        lambda: _ServerProtocol(loop, handler,
                                translation_table=translation_table),
        zmq.SUB, connect=connect, bind=bind)
    serv = PubSubService(loop, proto)
    if subscribe is not None:
        if isinstance(subscribe, (str, bytes)):
            subscribe = [subscribe]
        else:
            if not isinstance(subscribe, Iterable):
                raise ValueError('bind should be str, bytes or iterable')
        for topic in subscribe:
            serv.subscribe(topic)
    return serv


class _ClientProtocol(_BaseProtocol):

    def call(self, topic, name, args, kwargs):
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


class _ServerProtocol(_BaseProtocol, _MethodDispatcher):

    def __init__(self, loop, handler, translation_table=None):
        super().__init__(loop, translation_table=translation_table)
        self.handler = handler
        if not isinstance(handler, AbstractHandler):
            raise TypeError('handler should implement AbstractHandler ABC')

    def msg_received(self, data):
        btopic, bname, bargs, bkwargs = data

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
                logger.warn("PubSub handler %r returned not None", name)
        except Exception as exc:
            self.loop.call_exception_handler({
                'message': 'Call to {!r} caused error: {!r}'.format(name, exc),
                'exception': exc,
                'future': fut,
                'protocol': self,
                'transport': self.transport,
                })
