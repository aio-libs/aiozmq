import asyncio
import zmq

from .base import (
    NotFoundError,
    ParametersError,
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
    serv = Service(loop, proto)
    return serv


class _ClientProtocol(_BaseProtocol):

    def call(self, topic, name, args, kwargs):
        assert topic is None or isinstance(topic, (str, bytes))
        if topic is None:
            btopic = b''
        elif isinstance(topic, str):
            btopic = topic.encode('utf-8')
        else:   # bytes
            btopic = topic
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
        self.prepare_handler(handler)
        self.handler = handler

    def prepare_handler(self, handler):
        pass

    def msg_received(self, data):
        print(data)
