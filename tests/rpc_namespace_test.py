import unittest
import asyncio
import aiozmq
import aiozmq.rpc

from aiozmq._test_util import find_unused_port


class MyHandler(aiozmq.rpc.AttrHandler):

    @aiozmq.rpc.method
    @asyncio.coroutine
    def func(self, arg):
        return arg + 1
        yield


class RootHandler(aiozmq.rpc.AttrHandler):
    ns = MyHandler()


class RpcNamespaceTests(unittest.TestCase):

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

    def close(self, service):
        service.close()
        self.loop.run_until_complete(service.wait_closed())

    def make_rpc_pair(self):
        port = find_unused_port()

        @asyncio.coroutine
        def create():
            server = yield from aiozmq.rpc.serve_rpc(
                RootHandler(),
                bind='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop)
            client = yield from aiozmq.rpc.connect_rpc(
                connect='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop)
            return client, server

        self.client, self.server = self.loop.run_until_complete(create())

        return self.client, self.server

    def test_ns_func(self):
        client, server = self.make_rpc_pair()

        @asyncio.coroutine
        def communicate():
            ret = yield from client.call.ns.func(1)
            self.assertEqual(2, ret)

        self.loop.run_until_complete(communicate())

    def test_not_found(self):
        client, server = self.make_rpc_pair()

        @asyncio.coroutine
        def communicate():
            with self.assertRaisesRegex(aiozmq.rpc.NotFoundError, 'ns1.func'):
                yield from client.call.ns1.func(1)

        self.loop.run_until_complete(communicate())

    def test_bad_handler(self):
        client, server = self.make_rpc_pair()

        @asyncio.coroutine
        def communicate():
            with self.assertRaisesRegex(aiozmq.rpc.NotFoundError,
                                        'ns.func.foo'):
                yield from client.call.ns.func.foo(1)

        self.loop.run_until_complete(communicate())

    def test_missing_namespace_method(self):
        client, server = self.make_rpc_pair()

        @asyncio.coroutine
        def communicate():
            with self.assertRaisesRegex(aiozmq.rpc.NotFoundError, 'ns'):
                yield from client.call.ns(1)

        self.loop.run_until_complete(communicate())
