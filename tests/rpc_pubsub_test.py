import unittest
import asyncio
import aiozmq
import aiozmq.rpc

from aiozmq._test_utils import find_unused_port


class MyHandler(aiozmq.rpc.AttrHandler):

    def __init__(self, queue):
        super().__init__()
        self.queue = queue

    @aiozmq.rpc.method
    @asyncio.coroutine
    def start(self):
        yield from self.queue.put('started')

    @aiozmq.rpc.method
    @asyncio.coroutine
    def coro(self, arg):
        yield from self.queue.put(arg)

    @aiozmq.rpc.method
    def func(self, arg: int):
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

            if subscribe is not None:
                if not isinstance(subscribe, (str, bytes)):
                    pub = subscribe[0]
                else:
                    pub = subscribe
                for i in range(3):
                    try:
                        yield from client.publish(pub).start()
                        ret = yield from asyncio.wait_for(self.queue.get(),
                                                          0.1, loop=self.loop)
                        self.assertEqual(ret, 'started')
                        break
                    except asyncio.TimeoutError:
                        self.assertLess(i, 3)
                else:
                    self.fail('Cannot connect')
            return client, server

        self.client, self.server = self.loop.run_until_complete(create())
        return self.client, self.server

    def test_coro(self):
        client, server = self.make_pubsub_pair('my-topic')

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

        @asyncio.coroutine
        def communicate():
            yield from client.publish('my-topic').bad.method(1, 2)
            ret = yield from self.err_queue.get()
            self.assertRegex(ret['message'],
                             "Call to 'bad.method'.*NotFoundError")

        self.loop.run_until_complete(communicate())

    def test_func(self):
        client, server = self.make_pubsub_pair('my-topic')

        @asyncio.coroutine
        def communicate():
            yield from client.publish('my-topic').func(1)
            ret = yield from self.queue.get()
            self.assertEqual(ret, 2)

        self.loop.run_until_complete(communicate())

    def test_func__arg_error(self):
        client, server = self.make_pubsub_pair('my-topic')

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

        @asyncio.coroutine
        def communicate():
            yield from client.publish('my-topic').func_raise_error()
            ret = yield from self.err_queue.get()
            self.assertRegex(ret['message'],
                             "Call to 'func_raise_error'.*RuntimeError")

        self.loop.run_until_complete(communicate())

    def test_subscribe_to_bytes(self):
        client, server = self.make_pubsub_pair(b'my-topic')

        @asyncio.coroutine
        def communicate():
            yield from client.publish(b'my-topic').func_raise_error()
            ret = yield from self.err_queue.get()
            self.assertRegex(ret['message'],
                             "Call to 'func_raise_error'.*RuntimeError")

        self.loop.run_until_complete(communicate())

    def test_subscribe_to_invalid(self):
        @asyncio.coroutine
        def go():
            server = yield from aiozmq.rpc.serve_pubsub(
                MyHandler(self.queue),
                bind='tcp://*:*',
                loop=self.loop)
            self.assertRaises(TypeError, server.subscribe, 123)

        self.loop.run_until_complete(go())

    def test_unsubscribe(self):
        @asyncio.coroutine
        def go():
            server = yield from aiozmq.rpc.serve_pubsub(
                MyHandler(self.queue),
                bind='tcp://*:*',
                loop=self.loop)
            self.assertRaises(TypeError, server.subscribe, 123)

            server.subscribe('topic')
            server.unsubscribe('topic')
            self.assertNotIn('topic', server.transport.subscriptions())

            server.subscribe(b'btopic')
            server.unsubscribe(b'btopic')
            self.assertNotIn(b'btopic', server.transport.subscriptions())

            self.assertRaises(TypeError, server.unsubscribe, 123)

        self.loop.run_until_complete(go())

    def test_default_event_loop(self):
        port = find_unused_port()

        asyncio.set_event_loop_policy(aiozmq.ZmqEventLoopPolicy())
        self.addCleanup(asyncio.set_event_loop_policy, None)
        self.addCleanup(asyncio.set_event_loop, None)
        queue = asyncio.Queue()

        @asyncio.coroutine
        def create():
            server = yield from aiozmq.rpc.serve_pubsub(
                MyHandler(queue),
                bind='tcp://127.0.0.1:{}'.format(port),
                loop=None,
                subscribe='topic')
            client = yield from aiozmq.rpc.connect_pubsub(
                connect='tcp://127.0.0.1:{}'.format(port),
                loop=None)
            return client, server

        self.loop = loop = asyncio.get_event_loop()
        self.client, self.server = loop.run_until_complete(create())

        @asyncio.coroutine
        def communicate():
            for i in range(3):
                try:
                    yield from self.client.publish('topic').start()
                    ret = yield from asyncio.wait_for(queue.get(),
                                                      0.1)
                    self.assertEqual(ret, 'started')
                    break
                except asyncio.TimeoutError:
                    self.assertLess(i, 3)
            else:
                self.fail('Cannot connect')

            yield from self.client.publish('topic').func(1)
            ret = yield from queue.get()
            self.assertEqual(2, ret)

        loop.run_until_complete(communicate())
