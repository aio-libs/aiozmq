import unittest
import asyncio
import aiozmq, aiozmq.rpc

from functools import partial
from pickle import dumps, loads, HIGHEST_PROTOCOL
from aiozmq._test_utils import find_unused_port


class Point:

    def __init__(self, x, y):
        self.x = x
        self.y = y

    def __eq__(self, other):
        if isinstance(other, Point):
            return (self.x, self.y) == (other.x, other.y)
        return NotImplemented


translators = {
    0: (Point, partial(dumps, protocol=HIGHEST_PROTOCOL), loads),
}


class MyHandler(aiozmq.rpc.AttrHandler):

    @aiozmq.rpc.method
    @asyncio.coroutine
    def func(self, point):
        assert isinstance(point, Point)
        return point
        yield


class RpcTranslatorsTests(unittest.TestCase):

    def setUp(self):
        self.loop = aiozmq.ZmqEventLoop()
        asyncio.set_event_loop(None)
        self.client = self.server = None

    def tearDown(self):
        if self.client is not None:
            self.close(self.client)
        if self.server is not None:
            self.close(self.server)
        self.loop.close()

    def close(self, server):
        server.close()
        self.loop.run_until_complete(server.wait_closed())

    def make_rpc_pair(self, *, error_table=None):
        port = find_unused_port()

        @asyncio.coroutine
        def create():
            server = yield from aiozmq.rpc.start_server(
                MyHandler(),
                bind='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop,
                translators=translators)
            client = yield from aiozmq.rpc.open_client(
                connect='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop, error_table=error_table,
                translators=translators)
            return client, server

        self.client, self.server = self.loop.run_until_complete(create())

        return self.client, self.server

    def test_simple(self):
        client, server = self.make_rpc_pair()
        pt = Point(1, 2)

        @asyncio.coroutine
        def communicate():
            ret = yield from client.rpc.func(pt)
            self.assertEqual(ret, pt)

        self.loop.run_until_complete(communicate())
