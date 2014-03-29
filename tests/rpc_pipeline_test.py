import unittest
import asyncio
import aiozmq
import aiozmq.rpc


class MyHandler(aiozmq.rpc.AttrHandler):

    def __init__(self, queue):
        self.queue = queue

    @asyncio.coroutine
    @aiozmq.rpc.method
    def coro(self, arg):
        yield from self.queue.put(arg)

    @aiozmq.rpc.method
    def func(self, arg):
        self.queue.put_nowait(arg)

    @asyncio.coroutine
    @aiozmq.rpc.method
    def add(self, arg: int=1):
        yield from self.queue.put(arg + 1)

    @asyncio.coroutine
    @aiozmq.rpc.method
    def raise_error(self):
        raise RuntimeError('catch me')

    @aiozmq.rpc.method
    def func_error(self):
        raise ValueError

    @aiozmq.rpc.method
    @asyncio.coroutine
    def return_value(self, arg):
        return arg
        yield


class PipelineTests(unittest.TestCase):

    def setUp(self):
        self.loop = aiozmq.ZmqEventLoop()
        asyncio.set_event_loop(None)
        self.client = self.server = None
        self.queue = asyncio.Queue(loop=self.loop)
        self.err_queue = asyncio.Queue(loop=self.loop)
        self.loop.set_exception_handler(self.exception_handler)

    def tearDown(self):
        if self.client is not None:
            self.close(self.client)
        if self.server is not None:
            self.close(self.server)
        self.loop.close()

    def close(self, service):
        service.close()
        self.loop.run_until_complete(service.wait_closed())

    def exception_handler(self, loop, context):
        self.err_queue.put_nowait(context)

    def make_pipeline_pair(self):

        @asyncio.coroutine
        def create():
            server = yield from aiozmq.rpc.serve_pipeline(
                MyHandler(self.queue),
                bind='tcp://*:*',
                loop=self.loop)
            connect = next(iter(server.transport.bindings()))
            client = yield from aiozmq.rpc.connect_pipeline(
                connect=connect,
                loop=self.loop)
            return client, server

        self.client, self.server = self.loop.run_until_complete(create())
        return self.client, self.server

    def test_coro(self):
        client, server = self.make_pipeline_pair()

        @asyncio.coroutine
        def communicate():
            yield from client.notify.coro(1)
            ret = yield from self.queue.get()
            self.assertEqual(1, ret)

            yield from client.notify.coro(2)
            ret = yield from self.queue.get()
            self.assertEqual(2, ret)

        self.loop.run_until_complete(communicate())

    def test_add(self):
        client, server = self.make_pipeline_pair()

        @asyncio.coroutine
        def communicate():
            yield from client.notify.add()
            ret = yield from self.queue.get()
            self.assertEqual(ret, 2)
            yield from client.notify.add(2)
            ret = yield from self.queue.get()
            self.assertEqual(ret, 3)

        self.loop.run_until_complete(communicate())

    def test_raise_error(self):
        client, server = self.make_pipeline_pair()

        @asyncio.coroutine
        def communicate():
            yield from client.notify.raise_error()
            ctx = yield from self.err_queue.get()
            self.assertRegex(ctx['message'],
                             "Call to 'raise_error'.*RuntimeError")
            self.assertIn('exception', ctx)
            self.assertIsInstance(ctx['exception'], RuntimeError)

        self.loop.run_until_complete(communicate())

    def test_bad_handler(self):
        client, server = self.make_pipeline_pair()

        @asyncio.coroutine
        def communicate():
            yield from client.notify.bad_handler()
            ctx = yield from self.err_queue.get()
            self.assertRegex(ctx['message'],
                             "Call to 'bad_handler'.*NotFoundError")

        self.loop.run_until_complete(communicate())

    def test_func(self):
        client, server = self.make_pipeline_pair()

        @asyncio.coroutine
        def communicate():
            yield from client.notify.func(123)
            ret = yield from self.queue.get()
            self.assertEqual(ret, 123)

        self.loop.run_until_complete(communicate())

    def test_func_error(self):
        client, server = self.make_pipeline_pair()

        @asyncio.coroutine
        def communicate():
            yield from client.notify.func_error()
            ctx = yield from self.err_queue.get()
            self.assertRegex(ctx['message'],
                             "Call to 'func_error'.*ValueError")

        self.loop.run_until_complete(communicate())

    def test_default_event_loop(self):
        asyncio.set_event_loop_policy(aiozmq.ZmqEventLoopPolicy())

        @asyncio.coroutine
        def create():
            server = yield from aiozmq.rpc.serve_pipeline(
                MyHandler(self.queue),
                bind='tcp://*:*',
                loop=None)
            connect = next(iter(server.transport.bindings()))
            client = yield from aiozmq.rpc.connect_pipeline(
                connect=connect,
                loop=None)
            return client, server

        self.loop = loop = asyncio.get_event_loop()
        self.client, self.server = loop.run_until_complete(create())
