import unittest
import asyncio
import aiozmq
import aiozmq.rpc
import msgpack

from aiozmq._test_util import find_unused_port, RpcMixin


class Point:

    def __init__(self, x, y):
        self.x = x
        self.y = y

    def __eq__(self, other):
        if isinstance(other, Point):
            return (self.x, self.y) == (other.x, other.y)
        return NotImplemented


translation_table = {
    0: (Point,
        lambda value: msgpack.packb((value.x, value.y)),
        lambda binary: Point(*msgpack.unpackb(binary))),
}


class MyHandler(aiozmq.rpc.AttrHandler):

    @aiozmq.rpc.method
    @asyncio.coroutine
    def func(self, point):
        assert isinstance(point, Point)
        return point
        yield


class RpcTranslatorsMixin(RpcMixin):

    def make_rpc_pair(self, *, error_table=None):
        port = find_unused_port()

        @asyncio.coroutine
        def create():
            server = yield from aiozmq.rpc.serve_rpc(
                MyHandler(),
                bind='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop,
                translation_table=translation_table)
            client = yield from aiozmq.rpc.connect_rpc(
                connect='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop, error_table=error_table,
                translation_table=translation_table)
            return client, server

        self.client, self.server = self.loop.run_until_complete(create())

        return self.client, self.server

    def test_simple(self):
        client, server = self.make_rpc_pair()
        pt = Point(1, 2)

        @asyncio.coroutine
        def communicate():
            ret = yield from client.call.func(pt)
            self.assertEqual(ret, pt)

        self.loop.run_until_complete(communicate())


class LoopRpcTranslatorsTests(unittest.TestCase, RpcTranslatorsMixin):

    def setUp(self):
        self.loop = aiozmq.ZmqEventLoop()
        asyncio.set_event_loop(None)
        self.client = self.server = None

    def tearDown(self):
        self.close_service(self.client)
        self.close_service(self.server)
        self.loop.close()
        asyncio.set_event_loop(None)
        # zmq.Context.instance().term()


class LooplessRpcTranslatorsTests(unittest.TestCase, RpcTranslatorsMixin):

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(None)
        self.client = self.server = None

    def tearDown(self):
        self.close_service(self.client)
        self.close_service(self.server)
        self.loop.close()
        asyncio.set_event_loop(None)
        # zmq.Context.instance().term()
