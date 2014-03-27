import unittest
import asyncio
import aiozmq
import aiozmq.rpc


class PipelineTests(unittest.TestCase):

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

    def make_pipeline_pair(self, handlers_map):

        @asyncio.coroutine
        def create():
            server = yield from aiozmq.rpc.serve_pipeline(
                handlers_map,
                bind='tcp://*:*',
                loop=self.loop)
            client = yield from aiozmq.rpc.connect_pipeline(
                connect=server.transport.bindings(),
                loop=self.loop)
            return client, server

        self.client, self.server = self.loop.run_until_complete(create())
        return self.client, self.server

    def test_simple(self):

        @aiozmq.rpc.method
        def func(arg):
            self.assertEqual(arg, 1)

        client, server = self.make_pipeline_pair({'func': func})

        @asyncio.coroutine
        def communicate():
            yield from client.pipeline.func(1)

        self.loop.run_until_complete(communicate())
