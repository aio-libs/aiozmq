import unittest
import asyncio
import aiozmq
import aiozmq.rpc
import time


class MyHandler(aiozmq.rpc.AttrHandler):

    def __init__(self, queue):
        super().__init__()
        self.queue = queue

    @aiozmq.rpc.method
    @asyncio.coroutine
    def coro(self, arg):
        yield from self.queue.put(arg)


class PubSubTests(unittest.TestCase):

    def setUp(self):
        self.loop = aiozmq.ZmqEventLoop()
        asyncio.set_event_loop(None)
        self.client = self.server = None
        self.queue = asyncio.Queue(loop=self.loop)

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
                MyHandler(self.queue),
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

        server.subscribe('my-topic')
        # Sorry, sleep is required to get rid of sporadic hangs
        # without that 0MQ not always establishes tcp connection
        # and waiting for message from sub socket hangs.
        time.sleep(0.1)

        @asyncio.coroutine
        def communicate():
            yield from client.publish('my-topic').coro(1)
            ret = yield from self.queue.get()
            self.assertEqual(ret, 1)

        self.loop.run_until_complete(communicate())
