import unittest
import asyncio
import aiozmq
import aiozmq.rpc

from aiozmq._test_util import find_unused_port


class MyHandler(aiozmq.rpc.AttrHandler):
    @aiozmq.rpc.method
    async def func(self, arg):
        return arg + 1


class RootHandler(aiozmq.rpc.AttrHandler):
    ns = MyHandler()


class RpcNamespaceTestsMixin:
    def close(self, service):
        service.close()
        self.loop.run_until_complete(service.wait_closed())

    def make_rpc_pair(self):
        port = find_unused_port()

        async def create():
            server = await aiozmq.rpc.serve_rpc(
                RootHandler(), bind="tcp://127.0.0.1:{}".format(port)
            )
            client = await aiozmq.rpc.connect_rpc(
                connect="tcp://127.0.0.1:{}".format(port)
            )
            return client, server

        self.client, self.server = self.loop.run_until_complete(create())

        return self.client, self.server

    def test_ns_func(self):
        client, server = self.make_rpc_pair()

        async def communicate():
            ret = await client.call.ns.func(1)
            self.assertEqual(2, ret)

        self.loop.run_until_complete(communicate())

    def test_not_found(self):
        client, server = self.make_rpc_pair()

        async def communicate():
            with self.assertRaisesRegex(aiozmq.rpc.NotFoundError, "ns1.func"):
                await client.call.ns1.func(1)

        self.loop.run_until_complete(communicate())

    def test_bad_handler(self):
        client, server = self.make_rpc_pair()

        async def communicate():
            with self.assertRaisesRegex(aiozmq.rpc.NotFoundError, "ns.func.foo"):
                await client.call.ns.func.foo(1)

        self.loop.run_until_complete(communicate())

    def test_missing_namespace_method(self):
        client, server = self.make_rpc_pair()

        async def communicate():
            with self.assertRaisesRegex(aiozmq.rpc.NotFoundError, "ns"):
                await client.call.ns(1)

        self.loop.run_until_complete(communicate())


class LoopRpcNamespaceTests(unittest.TestCase, RpcNamespaceTestsMixin):
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
        asyncio.set_event_loop(None)
        # zmq.Context.instance().term()


class LooplessRpcNamespaceTests(unittest.TestCase, RpcNamespaceTestsMixin):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(None)
        self.client = self.server = None

    def tearDown(self):
        if self.client is not None:
            self.close(self.client)
        if self.server is not None:
            self.close(self.server)
        self.loop.close()
        asyncio.set_event_loop(None)
        # zmq.Context.instance().term()
