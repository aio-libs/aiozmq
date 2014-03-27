import unittest
import asyncio
import aiozmq
import aiozmq.rpc


class PubSubTests(unittest.TestCase):

    def setUp(self):
        self.loop = aiozmq.ZmqEventLoop()
        asyncio.set_event_loop(None)
        self.client = self.server = None

    def tearDown(self):
        if self.client:
            self.close(self.client)
        if self.server:
            self.close(self.server)
        self.loop.close()

    def close(self, service):
        service.close()
        self.loop.run_until_complete(service.wait_closed())

    def make_pubsub_pair(self):

        @asyncio.coroutine
        def create():
            server = yield from aiozmq.rpc.serve_pubsub(
                {},
                bind='tcp://*:*',
                loop=self.loop)
            connect = next(iter(server.transport.bindings()))
            client = yield from aiozmq.rpc.connect_pubsub(
                connect=connect,
                loop=self.loop)
            return client, server

        self.client, self.server = self.loop.run_until_complete(create())
        return self.client, self.server

    def test_simple(self):
        client, server = self.make_pubsub_pair()

        @asyncio.coroutine
        def communicate():
            yield from client.publish('my-topic').func(1)

        self.loop.run_until_complete(communicate())
