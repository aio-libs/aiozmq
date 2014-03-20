import unittest
import asyncio
import aiozmq, aiozmq.rpc
import time
import zmq

from test import support  # import from standard python test suite


class MyHandler(aiozmq.rpc.Handler):

    @aiozmq.rpc.rpc
    @asyncio.coroutine
    def func(self, arg):
        return arg + 1

    @aiozmq.rpc.rpc
    @asyncio.coroutine
    def exc(self, arg):
        raise RuntimeError("bad arg", arg)


class RpcTests(unittest.TestCase):

    def setUp(self):
        self.loop = aiozmq.ZmqEventLoop()
        asyncio.set_event_loop(None)

    def tearDown(self):
        self.loop.close()

    def make_rpc_pair(self):
        port = support.find_unused_port()

        @asyncio.coroutine
        def create():
            server = yield from aiozmq.rpc.start_server(MyHandler(),
                bind='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop)
            client = yield from aiozmq.rpc.open_client(
                connect='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop)
            return client, server

        client, server = self.loop.run_until_complete(create())
        return client, server

    def test_func(self):
        client, server = self.make_rpc_pair()

        @asyncio.coroutine
        def communicate():
            ret = yield from client.func(1)
            self.assertEqual(2, ret)

        self.loop.run_until_complete(communicate())

    def test_exc(self):
        client, server = self.make_rpc_pair()

        @asyncio.coroutine
        def communicate():
            with self.assertRaises(RuntimeError) as exc:
                yield from client.exc(1)
                self.assertEqual(('bad arg', 1), exc.exception.args)

        self.loop.run_until_complete(communicate())
        
