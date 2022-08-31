import unittest
import asyncio
import aiozmq
import aiozmq.rpc
import logging

from unittest import mock
from aiozmq._test_util import find_unused_port, log_hook, RpcMixin


class MyHandler(aiozmq.rpc.AttrHandler):
    def __init__(self, queue, loop):
        super().__init__()
        self.queue = queue
        self.loop = loop

    @aiozmq.rpc.method
    async def start(self):
        await self.queue.put("started")

    @aiozmq.rpc.method
    async def coro(self, arg):
        await self.queue.put(arg)

    @aiozmq.rpc.method
    def func(self, arg: int):
        self.queue.put_nowait(arg + 1)

    @aiozmq.rpc.method
    def func_raise_error(self):
        raise RuntimeError

    @aiozmq.rpc.method
    def suspicious(self, arg: int):
        self.queue.put_nowait(arg + 1)
        return 3

    @aiozmq.rpc.method
    async def fut(self):
        f = asyncio.Future()
        await self.queue.put(f)
        await f


class PubSubTestsMixin(RpcMixin):
    @classmethod
    def setUpClass(self):
        logger = logging.getLogger()
        self.log_level = logger.getEffectiveLevel()
        logger.setLevel(logging.DEBUG)

    @classmethod
    def tearDownClass(self):
        logger = logging.getLogger()
        logger.setLevel(self.log_level)

    def make_pubsub_pair(
        self,
        subscribe=None,
        log_exceptions=False,
        exclude_log_exceptions=(),
        use_loop=True,
    ):

        loop = self.loop if use_loop else asyncio.get_event_loop()

        async def create():
            server = await aiozmq.rpc.serve_pubsub(
                MyHandler(self.queue, self.loop),
                subscribe=subscribe,
                bind="tcp://127.0.0.1:*",
                loop=self.loop if use_loop else None,
                log_exceptions=log_exceptions,
                exclude_log_exceptions=exclude_log_exceptions,
            )
            connect = next(iter(server.transport.bindings()))
            client = await aiozmq.rpc.connect_pubsub(
                connect=connect, loop=self.loop if use_loop else None
            )

            if subscribe is not None:
                if not isinstance(subscribe, (str, bytes)):
                    pub = subscribe[0]
                else:
                    pub = subscribe
                for i in range(3):
                    try:
                        await client.publish(pub).start()
                        ret = await asyncio.wait_for(self.queue.get(), 0.1)
                        self.assertEqual(ret, "started")
                        break
                    except asyncio.TimeoutError:
                        self.assertLess(i, 3)
                else:
                    self.fail("Cannot connect")
            return client, server

        self.client, self.server = loop.run_until_complete(create())
        return self.client, self.server

    def test_coro(self):
        client, server = self.make_pubsub_pair("my-topic")

        async def communicate():
            await client.publish("my-topic").coro(1)
            ret = await self.queue.get()
            self.assertEqual(ret, 1)

            await client.publish("other-topic").coro(1)
            self.assertTrue(self.queue.empty())

        self.loop.run_until_complete(communicate())

    def test_coro__multiple_topics(self):
        client, server = self.make_pubsub_pair(("topic1", "topic2"))

        async def communicate():
            await client.publish("topic1").coro(1)
            ret = await self.queue.get()
            self.assertEqual(ret, 1)

            await client.publish("topic2").coro(1)
            ret = await self.queue.get()
            self.assertEqual(ret, 1)

        self.loop.run_until_complete(communicate())

    def test_coro__subscribe_to_all(self):
        client, server = self.make_pubsub_pair("")

        async def communicate():
            await client.publish("sometopic").coro(123)
            ret = await self.queue.get()
            self.assertEqual(ret, 123)

            await client.publish(None).coro("abc")
            ret = await self.queue.get()
            self.assertEqual(ret, "abc")

            await client.publish("").coro(1)
            ret = await self.queue.get()
            self.assertEqual(ret, 1)

        self.loop.run_until_complete(communicate())

    def test_call_error(self):
        client, server = self.make_pubsub_pair()

        with self.assertRaisesRegex(ValueError, "PubSub method name is empty"):
            client.publish("topic")()

    def test_not_found(self):
        client, server = self.make_pubsub_pair("my-topic")

        async def communicate():
            with log_hook("aiozmq.rpc", self.err_queue):
                await client.publish("my-topic").bad.method(1, 2)

                ret = await self.err_queue.get()
                self.assertEqual(logging.ERROR, ret.levelno)
                self.assertEqual("Call to %r caused error: %r", ret.msg)
                self.assertEqual(("bad.method", mock.ANY), ret.args)
                self.assertIsNotNone(ret.exc_info)

        self.loop.run_until_complete(communicate())

    def test_func(self):
        client, server = self.make_pubsub_pair("my-topic")

        async def communicate():
            await client.publish("my-topic").func(1)
            ret = await self.queue.get()
            self.assertEqual(ret, 2)

        self.loop.run_until_complete(communicate())

    def test_func__arg_error(self):
        client, server = self.make_pubsub_pair("my-topic")

        async def communicate():
            with log_hook("aiozmq.rpc", self.err_queue):
                await client.publish("my-topic").func("abc")

                ret = await self.err_queue.get()
                self.assertEqual(logging.ERROR, ret.levelno)
                self.assertEqual("Call to %r caused error: %r", ret.msg)
                self.assertEqual(("func", mock.ANY), ret.args)
                self.assertIsNotNone(ret.exc_info)

                self.assertTrue(self.queue.empty())

        self.loop.run_until_complete(communicate())

    def test_func_raises_error(self):
        client, server = self.make_pubsub_pair("my-topic", log_exceptions=True)

        async def communicate():
            with log_hook("aiozmq.rpc", self.err_queue):
                await client.publish("my-topic").func_raise_error()

                ret = await self.err_queue.get()
                self.assertEqual(logging.ERROR, ret.levelno)
                self.assertEqual(
                    "An exception %r from method %r call occurred.\n"
                    "args = %s\nkwargs = %s\n",
                    ret.msg,
                )
                self.assertEqual((mock.ANY, "func_raise_error", "()", "{}"), ret.args)
                self.assertIsNotNone(ret.exc_info)

        self.loop.run_until_complete(communicate())

    def test_subscribe_to_bytes(self):
        client, server = self.make_pubsub_pair(b"my-topic")

        async def communicate():
            await client.publish(b"my-topic").func(1)
            ret = await self.queue.get()
            self.assertEqual(ret, 2)

        self.loop.run_until_complete(communicate())

    def test_subscribe_to_invalid(self):
        async def go():
            server = await aiozmq.rpc.serve_pubsub(
                MyHandler(self.queue, self.loop),
                bind="tcp://127.0.0.1:*",
            )
            self.assertRaises(TypeError, server.subscribe, 123)

        self.loop.run_until_complete(go())

    def test_unsubscribe(self):
        async def go():
            server = await aiozmq.rpc.serve_pubsub(
                MyHandler(self.queue, self.loop),
                bind="tcp://127.0.0.1:*",
            )
            self.assertRaises(TypeError, server.subscribe, 123)

            server.subscribe("topic")
            server.unsubscribe("topic")
            self.assertNotIn("topic", server.transport.subscriptions())

            server.subscribe(b"btopic")
            server.unsubscribe(b"btopic")
            self.assertNotIn(b"btopic", server.transport.subscriptions())

            self.assertRaises(TypeError, server.unsubscribe, 123)

        self.loop.run_until_complete(go())

    def test_default_event_loop(self):
        asyncio.set_event_loop_policy(aiozmq.ZmqEventLoopPolicy())
        self.addCleanup(asyncio.set_event_loop_policy, None)

        self.addCleanup(self.loop.close)
        self.loop = loop = asyncio.get_event_loop()
        # should use the default loop, not closed one
        self.queue = asyncio.Queue()
        self.client, self.server = self.make_pubsub_pair(
            use_loop=False, subscribe="topic"
        )

        async def communicate():

            await self.client.publish("topic").func(1)
            ret = await self.queue.get()
            self.assertEqual(2, ret)

        loop.run_until_complete(communicate())

    def test_serve_bad_subscription(self):
        port = find_unused_port()

        async def create():
            with self.assertRaises(TypeError):
                await aiozmq.rpc.serve_pubsub(
                    {},
                    bind="tcp://127.0.0.1:{}".format(port),
                    subscribe=123,
                )

        self.loop.run_until_complete(create())

    def test_publish_to_invalid_topic(self):
        client, server = self.make_pubsub_pair("")

        async def communicate():
            with self.assertRaises(TypeError):
                await client.publish(123).coro(123)

        self.loop.run_until_complete(communicate())

    def test_warning_if_remote_return_not_None(self):
        client, server = self.make_pubsub_pair("topic")

        async def communicate():
            with log_hook("aiozmq.rpc", self.err_queue):
                await client.publish("topic").suspicious(1)
                ret = await self.queue.get()
                self.assertEqual(2, ret)

                ret = await self.err_queue.get()
                self.assertEqual(logging.WARNING, ret.levelno)
                self.assertEqual("PubSub handler %r returned not None", ret.msg)
                self.assertEqual(("suspicious",), ret.args)
                self.assertIsNone(ret.exc_info)

        self.loop.run_until_complete(communicate())

    def test_call_closed_pubsub(self):
        client, server = self.make_pubsub_pair()

        async def communicate():
            client.close()
            await client.wait_closed()
            with self.assertRaises(aiozmq.rpc.ServiceClosedError):
                await client.publish("ab").func()

        self.loop.run_until_complete(communicate())

    def test_server_close(self):
        client, server = self.make_pubsub_pair("my-topic")

        async def communicate():
            client.publish("my-topic").fut()
            fut = await self.queue.get()
            self.assertEqual(1, len(server._proto.pending_waiters))
            task = next(iter(server._proto.pending_waiters))
            self.assertIsInstance(task, asyncio.Task)
            server.close()
            await server.wait_closed()
            await asyncio.sleep(0.1)
            self.assertEqual(0, len(server._proto.pending_waiters))
            fut.cancel()

        self.loop.run_until_complete(communicate())


class LoopPubSubTests(unittest.TestCase, PubSubTestsMixin):
    def setUp(self):
        self.loop = aiozmq.ZmqEventLoop()
        asyncio.set_event_loop(self.loop)
        self.client = self.server = None
        self.queue = asyncio.Queue()
        self.err_queue = asyncio.Queue()

    def tearDown(self):
        self.close_service(self.client)
        self.close_service(self.server)
        self.loop.close()
        asyncio.set_event_loop(None)
        # zmq.Context.instance().term()


class LooplessPubSubTests(unittest.TestCase, PubSubTestsMixin):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.client = self.server = None
        self.queue = asyncio.Queue()
        self.err_queue = asyncio.Queue()

    def tearDown(self):
        self.close_service(self.client)
        self.close_service(self.server)
        self.loop.close()
        asyncio.set_event_loop(None)
        # zmq.Context.instance().term()
