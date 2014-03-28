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

    @aiozmq.rpc.method
    def func(self, arg:int):
        self.queue.put_nowait(arg + 1)

    @aiozmq.rpc.method
    def func_raise_error(self):
        raise RuntimeError


class PubSubTests(unittest.TestCase):

    def setUp(self):
        self.loop = aiozmq.ZmqEventLoop()
        asyncio.set_event_loop(None)
        self.client = self.server = None
        self.queue = asyncio.Queue(loop=self.loop)
        self.err_queue = asyncio.Queue(loop=self.loop)
        self.loop.set_exception_handler(self.exc_handler)

    def tearDown(self):
        if self.client:
            self.close(self.client)
        if self.server:
            self.close(self.server)
        self.loop.close()

    def close(self, service):
        service.close()
        self.loop.run_until_complete(service.wait_closed())

    def exc_handler(self, loop, context):
        self.err_queue.put_nowait(context)

    def make_pubsub_pair(self, subscribe=None):

        @asyncio.coroutine
        def create():
            server = yield from aiozmq.rpc.serve_pubsub(
                MyHandler(self.queue),
                subscribe=subscribe,
                bind='tcp://*:*',
                loop=self.loop)
            connect = next(iter(server.transport.bindings()))
            client = yield from aiozmq.rpc.connect_pubsub(
                connect=connect,
                loop=self.loop)
            return client, server

        self.client, self.server = self.loop.run_until_complete(create())
        return self.client, self.server

    def test_coro(self):
        client, server = self.make_pubsub_pair('my-topic')

        # Sorry, sleep is required to get rid of sporadic hangs
        # without that 0MQ not always establishes tcp connection
        # and waiting for message from sub socket hangs.
        time.sleep(0.1)

        @asyncio.coroutine
        def communicate():
            yield from client.publish('my-topic').coro(1)
            ret = yield from self.queue.get()
            self.assertEqual(ret, 1)

            yield from client.publish('other-topic').coro(1)
            self.assertTrue(self.queue.empty())

        self.loop.run_until_complete(communicate())

    def test_coro__multiple_topics(self):
        client, server = self.make_pubsub_pair(('topic1', 'topic2'))

        # see test_coro
        time.sleep(0.1)

        @asyncio.coroutine
        def communicate():
            yield from client.publish('topic1').coro(1)
            ret = yield from self.queue.get()
            self.assertEqual(ret, 1)

            yield from client.publish('topic2').coro(1)
            ret = yield from self.queue.get()
            self.assertEqual(ret, 1)

        self.loop.run_until_complete(communicate())

    def test_coro__subscribe_to_all(self):
        client, server = self.make_pubsub_pair('')

        # see test_coro
        time.sleep(0.1)

        @asyncio.coroutine
        def communicate():
            yield from client.publish('sometopic').coro(123)
            ret = yield from self.queue.get()
            self.assertEqual(ret, 123)

            yield from client.publish(None).coro('abc')
            ret = yield from self.queue.get()
            self.assertEqual(ret, 'abc')

            yield from client.publish('').coro(1)
            ret = yield from self.queue.get()
            self.assertEqual(ret, 1)

        self.loop.run_until_complete(communicate())

    def test_call_error(self):
        client, server = self.make_pubsub_pair()

        with self.assertRaisesRegex(ValueError, "PubSub method name is empty"):
            client.publish('topic')()

    def test_not_found(self):
        client, server = self.make_pubsub_pair('my-topic')

        # see test_coro
        time.sleep(0.1)

        @asyncio.coroutine
        def communicate():
            yield from client.publish('my-topic').bad.method(1, 2)
            ret = yield from self.err_queue.get()
            self.assertRegex(ret['message'],
                             "Call to 'bad.method'.*NotFoundError")

        self.loop.run_until_complete(communicate())

    def test_func(self):
        client, server = self.make_pubsub_pair('my-topic')

        # see test_coro
        time.sleep(0.1)

        @asyncio.coroutine
        def communicate():
            yield from client.publish('my-topic').func(1)
            ret = yield from self.queue.get()
            self.assertEqual(ret, 2)

        self.loop.run_until_complete(communicate())

    def test_func__arg_error(self):
        client, server = self.make_pubsub_pair('my-topic')

        # see test_coro
        time.sleep(0.1)

        @asyncio.coroutine
        def communicate():
            yield from client.publish('my-topic').func('abc')
            self.assertTrue(self.queue.empty())
            ret = yield from self.err_queue.get()
            self.assertRegex(ret['message'],
                             "Call to 'func'.*ParametersError")

        self.loop.run_until_complete(communicate())

    def test_func_raises_error(self):
        client, server = self.make_pubsub_pair('my-topic')

        # see test_coro
        time.sleep(0.1)

        @asyncio.coroutine
        def communicate():
            yield from client.publish('my-topic').func_raise_error()
            ret = yield from self.err_queue.get()
            self.assertRegex(ret['message'],
                             "Call to 'func_raise_error'.*RuntimeError")

        self.loop.run_until_complete(communicate())
