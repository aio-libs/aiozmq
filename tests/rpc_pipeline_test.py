import unittest
import asyncio
import aiozmq
import aiozmq.rpc
import logging

from unittest import mock
from aiozmq._test_util import log_hook, RpcMixin


class MyHandler(aiozmq.rpc.AttrHandler):
    def __init__(self, queue, loop):
        self.queue = queue
        self.loop = loop

    @aiozmq.rpc.method
    async def coro(self, arg):
        await self.queue.put(arg)

    @aiozmq.rpc.method
    def func(self, arg):
        self.queue.put_nowait(arg)

    @aiozmq.rpc.method
    async def add(self, arg: int = 1):
        await self.queue.put(arg + 1)

    @aiozmq.rpc.method
    def func_error(self):
        raise ValueError

    @aiozmq.rpc.method
    def suspicious(self, arg: int):
        self.queue.put_nowait(arg)
        return 3

    @aiozmq.rpc.method
    async def fut(self):
        f = asyncio.Future()
        await self.queue.put(f)
        await f


class PipelineTestsMixin(RpcMixin):
    @classmethod
    def setUpClass(self):
        logger = logging.getLogger()
        self.log_level = logger.getEffectiveLevel()
        logger.setLevel(logging.DEBUG)

    @classmethod
    def tearDownClass(self):
        logger = logging.getLogger()
        logger.setLevel(self.log_level)

    def exception_handler(self, loop, context):
        self.err_queue.put_nowait(context)

    def make_pipeline_pair(
        self, log_exceptions=False, exclude_log_exceptions=(), use_loop=True
    ):
        async def create():
            server = await aiozmq.rpc.serve_pipeline(
                MyHandler(self.queue, self.loop),
                bind="tcp://127.0.0.1:*",
                loop=self.loop if use_loop else None,
                log_exceptions=log_exceptions,
                exclude_log_exceptions=exclude_log_exceptions,
            )
            connect = next(iter(server.transport.bindings()))
            client = await aiozmq.rpc.connect_pipeline(
                connect=connect if use_loop else None
            )
            return client, server

        self.client, self.server = self.loop.run_until_complete(create())
        return self.client, self.server

    def test_coro(self):
        client, server = self.make_pipeline_pair()

        async def communicate():
            await client.notify.coro(1)
            ret = await self.queue.get()
            self.assertEqual(1, ret)

            await client.notify.coro(2)
            ret = await self.queue.get()
            self.assertEqual(2, ret)

        self.loop.run_until_complete(communicate())

    def test_add(self):
        client, server = self.make_pipeline_pair()

        async def communicate():
            await client.notify.add()
            ret = await self.queue.get()
            self.assertEqual(ret, 2)
            await client.notify.add(2)
            ret = await self.queue.get()
            self.assertEqual(ret, 3)

        self.loop.run_until_complete(communicate())

    def test_bad_handler(self):
        client, server = self.make_pipeline_pair()

        async def communicate():
            with log_hook("aiozmq.rpc", self.err_queue):
                await client.notify.bad_handler()

                ret = await self.err_queue.get()
                self.assertEqual(logging.ERROR, ret.levelno)
                self.assertEqual("Call to %r caused error: %r", ret.msg)
                self.assertEqual(("bad_handler", mock.ANY), ret.args)
                self.assertIsNotNone(ret.exc_info)

        self.loop.run_until_complete(communicate())

    def test_func(self):
        client, server = self.make_pipeline_pair()

        async def communicate():
            await client.notify.func(123)
            ret = await self.queue.get()
            self.assertEqual(ret, 123)

        self.loop.run_until_complete(communicate())

    def test_func_error(self):
        client, server = self.make_pipeline_pair(log_exceptions=True)

        async def communicate():
            with log_hook("aiozmq.rpc", self.err_queue):
                await client.notify.func_error()

                ret = await self.err_queue.get()
                self.assertEqual(logging.ERROR, ret.levelno)
                self.assertEqual(
                    "An exception %r from method %r "
                    "call occurred.\n"
                    "args = %s\nkwargs = %s\n",
                    ret.msg,
                )
                self.assertEqual((mock.ANY, "func_error", "()", "{}"), ret.args)
                self.assertIsNotNone(ret.exc_info)

        self.loop.run_until_complete(communicate())

    def test_default_event_loop(self):
        asyncio.set_event_loop_policy(aiozmq.ZmqEventLoopPolicy())
        self.addCleanup(asyncio.set_event_loop_policy, None)

        self.addCleanup(self.loop.close)
        self.loop = asyncio.get_event_loop()
        self.client, self.server = self.make_pipeline_pair(use_loop=False)
        self.assertIs(self.client._loop, self.loop)
        self.assertIs(self.server._loop, self.loop)

    def test_warning_if_remote_return_not_None(self):
        client, server = self.make_pipeline_pair()

        async def communicate():
            with log_hook("aiozmq.rpc", self.err_queue):
                await client.notify.suspicious(1)
                ret = await self.queue.get()
                self.assertEqual(1, ret)

                ret = await self.err_queue.get()
                self.assertEqual(logging.WARNING, ret.levelno)
                self.assertEqual("Pipeline handler %r returned not None", ret.msg)
                self.assertEqual(("suspicious",), ret.args)
                self.assertIsNone(ret.exc_info)

        async def dummy():
            pass

        self.loop.run_until_complete(communicate())
        self.loop.run_until_complete(dummy())

    def test_call_closed_pipeline(self):
        client, server = self.make_pipeline_pair()

        async def communicate():
            client.close()
            await client.wait_closed()
            with self.assertRaises(aiozmq.rpc.ServiceClosedError):
                await client.notify.func()

        self.loop.run_until_complete(communicate())

    def test_server_close(self):
        client, server = self.make_pipeline_pair()

        async def communicate():
            client.notify.fut()
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


class LoopPipelineTests(unittest.TestCase, PipelineTestsMixin):
    def setUp(self):
        self.loop = aiozmq.ZmqEventLoop()
        asyncio.set_event_loop(self.loop)
        self.client = self.server = None
        self.queue = asyncio.Queue()
        self.err_queue = asyncio.Queue()
        self.loop.set_exception_handler(self.exception_handler)

    def tearDown(self):
        self.close_service(self.client)
        self.close_service(self.server)
        self.loop.close()
        asyncio.set_event_loop(None)
        # zmq.Context.instance().term()


class LooplessPipelineTests(unittest.TestCase, PipelineTestsMixin):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.client = self.server = None
        self.queue = asyncio.Queue()
        self.err_queue = asyncio.Queue()
        self.loop.set_exception_handler(self.exception_handler)

    def tearDown(self):
        self.close_service(self.client)
        self.close_service(self.server)
        self.loop.close()
        asyncio.set_event_loop(None)
        # zmq.Context.instance().term()
