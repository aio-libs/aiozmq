import unittest
import asyncio
import aiozmq
import aiozmq.rpc
import datetime
import logging
import time
from unittest import mock
import zmq
import msgpack
import struct

from aiozmq import create_zmq_connection
from aiozmq._test_util import find_unused_port, log_hook, RpcMixin
from aiozmq.rpc.log import logger


class MyException(Exception):
    pass


class MyHandler(aiozmq.rpc.AttrHandler):
    def __init__(self, loop):
        self.loop = loop

    @aiozmq.rpc.method
    def func(self, arg):
        return arg + 1

    @aiozmq.rpc.method
    async def coro(self, arg):
        return arg + 1

    @aiozmq.rpc.method
    def exc(self, arg):
        raise RuntimeError("bad arg", arg)

    @aiozmq.rpc.method
    async def exc_coro(self, arg):
        raise RuntimeError("bad arg 2", arg)

    @aiozmq.rpc.method
    def add(self, a1, a2):
        return a1 + a2

    @aiozmq.rpc.method
    def generic_exception(self):
        raise MyException("additional", "data")

    @aiozmq.rpc.method
    async def slow_call(self):
        await asyncio.sleep(0.2)

    @aiozmq.rpc.method
    @asyncio.coroutine
    def fut(self):
        return asyncio.Future()

    @aiozmq.rpc.method
    async def cancelled_fut(self):
        ret = asyncio.Future()
        ret.cancel()
        return ret

    @aiozmq.rpc.method
    def exc2(self, arg):
        raise ValueError("bad arg", arg)

    @aiozmq.rpc.method
    async def not_so_fast(self):
        await asyncio.sleep(0.001)
        return "ok"


class Protocol(aiozmq.ZmqProtocol):
    def __init__(self, loop):
        self.transport = None
        self.connected = asyncio.Future()
        self.closed = asyncio.Future()
        self.state = "INITIAL"
        self.received = asyncio.Queue()

    def connection_made(self, transport):
        self.transport = transport
        assert self.state == "INITIAL", self.state
        self.state = "CONNECTED"
        self.connected.set_result(None)

    def connection_lost(self, exc):
        assert self.state == "CONNECTED", self.state
        self.state = "CLOSED"
        self.closed.set_result(None)
        self.transport = None

    def pause_writing(self):
        pass

    def resume_writing(self):
        pass

    def msg_received(self, data):
        assert isinstance(data, tuple), data
        assert self.state == "CONNECTED", self.state
        self.received.put_nowait(data)


class RpcTestsMixin(RpcMixin):
    @classmethod
    def setUpClass(self):
        root_logger = logging.getLogger()
        self.log_level = logger.getEffectiveLevel()
        root_logger.setLevel(logging.DEBUG)

    @classmethod
    def tearDownClass(self):
        root_logger = logging.getLogger()
        root_logger.setLevel(self.log_level)

    def make_rpc_pair(
        self,
        *,
        error_table=None,
        timeout=None,
        log_exceptions=False,
        exclude_log_exceptions=(),
        use_loop=True
    ):
        async def create():
            port = find_unused_port()
            server = await aiozmq.rpc.serve_rpc(
                MyHandler(self.loop),
                bind="tcp://127.0.0.1:{}".format(port),
                loop=self.loop if use_loop else None,
                log_exceptions=log_exceptions,
                exclude_log_exceptions=exclude_log_exceptions,
            )
            client = await aiozmq.rpc.connect_rpc(
                connect="tcp://127.0.0.1:{}".format(port),
                loop=self.loop if use_loop else None,
                error_table=error_table,
                timeout=timeout,
            )

            return client, server

        self.client, self.server = self.loop.run_until_complete(create())

        return self.client, self.server

    def test_func(self):
        client, server = self.make_rpc_pair()

        async def communicate():
            ret = await client.call.func(1)
            self.assertEqual(2, ret)
            client.close()
            await client.wait_closed()

        self.loop.run_until_complete(communicate())

    def test_exc(self):
        client, server = self.make_rpc_pair()

        async def communicate():
            with self.assertRaises(RuntimeError) as exc:
                await client.call.exc(1)
            self.assertEqual(("bad arg", 1), exc.exception.args)

        self.loop.run_until_complete(communicate())

    def test_not_found(self):
        client, server = self.make_rpc_pair()

        async def communicate():
            with self.assertRaises(aiozmq.rpc.NotFoundError) as exc:
                await client.call.unknown_method(1, 2, 3)
            self.assertEqual(("unknown_method",), exc.exception.args)

        self.loop.run_until_complete(communicate())

    def test_coro(self):
        client, server = self.make_rpc_pair()

        async def communicate():
            ret = await client.call.coro(2)
            self.assertEqual(3, ret)

        self.loop.run_until_complete(communicate())

    def test_exc_coro(self):
        client, server = self.make_rpc_pair()

        async def communicate():
            with self.assertRaises(RuntimeError) as exc:
                await client.call.exc_coro(1)
            self.assertEqual(("bad arg 2", 1), exc.exception.args)

        self.loop.run_until_complete(communicate())

    def test_datetime_translators(self):
        client, server = self.make_rpc_pair()

        async def communicate():
            ret = await client.call.add(
                datetime.date(2014, 3, 21), datetime.timedelta(days=2)
            )
            self.assertEqual(datetime.date(2014, 3, 23), ret)

        self.loop.run_until_complete(communicate())

    def test_not_found_empty_name(self):
        client, server = self.make_rpc_pair()

        async def communicate():
            with self.assertRaises(ValueError) as exc:
                await client.call(1, 2, 3)
            self.assertEqual(("RPC method name is empty",), exc.exception.args)

        self.loop.run_until_complete(communicate())

    def test_not_found_empty_name_on_server(self):
        client, server = self.make_rpc_pair()

        async def communicate():
            with self.assertRaises(aiozmq.rpc.NotFoundError) as exc:
                await client._proto.call("", (), {})
            self.assertEqual(("",), exc.exception.args)

        self.loop.run_until_complete(communicate())

    def test_generic_exception(self):
        client, server = self.make_rpc_pair()

        async def communicate():
            with self.assertRaises(aiozmq.rpc.GenericError) as exc:
                await client.call.generic_exception()
            self.assertEqual(
                (
                    "rpc_test.MyException",
                    ("additional", "data"),
                    "MyException('additional', 'data')",
                ),
                exc.exception.args,
            )
            self.assertEqual(
                "<Generic RPC Error "
                "rpc_test.MyException('additional', 'data'): "
                "MyException('additional', 'data')>",
                repr(exc.exception),
            )

        self.loop.run_until_complete(communicate())

    def test_exception_translator(self):
        client, server = self.make_rpc_pair(
            error_table={__name__ + ".MyException": MyException}
        )

        async def communicate():
            with self.assertRaises(MyException) as exc:
                await client.call.generic_exception()
            self.assertEqual(("additional", "data"), exc.exception.args)

        self.loop.run_until_complete(communicate())

    def test_default_event_loop(self):
        asyncio.set_event_loop_policy(aiozmq.ZmqEventLoopPolicy())
        self.addCleanup(asyncio.set_event_loop_policy, None)

        self.addCleanup(self.loop.close)
        self.loop = loop = asyncio.get_event_loop()
        client, server = self.make_rpc_pair(use_loop=False)

        async def communicate():
            ret = await client.call.func(1)
            self.assertEqual(2, ret)

        loop.run_until_complete(communicate())

    def test_service_transport(self):
        client, server = self.make_rpc_pair()

        self.assertIsInstance(client.transport, aiozmq.ZmqTransport)
        self.assertIsInstance(server.transport, aiozmq.ZmqTransport)

        client.close()
        self.loop.run_until_complete(client.wait_closed())
        with self.assertRaises(aiozmq.rpc.ServiceClosedError):
            client.transport

        server.close()
        self.loop.run_until_complete(server.wait_closed())
        with self.assertRaises(aiozmq.rpc.ServiceClosedError):
            server.transport

    def test_client_timeout(self):
        client, server = self.make_rpc_pair()

        async def communicate():
            with log_hook("aiozmq.rpc", self.err_queue):
                with self.assertRaises(asyncio.TimeoutError):
                    with client.with_timeout(0.1) as timedout:
                        await timedout.call.slow_call()

                t0 = time.monotonic()
                with self.assertRaises(asyncio.TimeoutError):
                    await client.with_timeout(0.1).call.slow_call()
                t1 = time.monotonic()
                self.assertTrue(0.08 <= t1 - t0 <= 0.12, t1 - t0)

                # NB: dont check log records, they are not necessary present

        self.loop.run_until_complete(communicate())

    def test_client_override_global_timeout(self):
        client, server = self.make_rpc_pair(timeout=10)

        async def communicate():
            with self.assertRaises(asyncio.TimeoutError):
                with client.with_timeout(0.1) as timedout:
                    await timedout.call.slow_call()

            t0 = time.monotonic()
            with self.assertRaises(asyncio.TimeoutError):
                await client.with_timeout(0.1).call.slow_call()
            t1 = time.monotonic()
            self.assertTrue(0.08 <= t1 - t0 <= 0.12, t1 - t0)
            server.close()
            client.close()
            await asyncio.gather(server.wait_closed(), client.wait_closed())

        self.loop.run_until_complete(communicate())

    def test_type_of_handler(self):
        async def go():
            with self.assertRaises(TypeError):
                await aiozmq.rpc.serve_rpc("Bad Handler", bind="tcp://127.0.0.1:*")

        self.loop.run_until_complete(go())

    def test_unknown_format_at_server(self):
        async def go():
            port = find_unused_port()
            server = await aiozmq.rpc.serve_rpc(
                MyHandler(self.loop),
                bind="tcp://127.0.0.1:{}".format(port),
            )
            tr, pr = await create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.DEALER,
                connect="tcp://127.0.0.1:{}".format(port),
            )

            await asyncio.sleep(0.001)

            with log_hook("aiozmq.rpc", self.err_queue):
                tr.write([b"invalid", b"structure"])

                ret = await self.err_queue.get()
                self.assertEqual(logging.CRITICAL, ret.levelno)
                self.assertEqual("Cannot unpack %r", ret.msg)
                self.assertEqual(([mock.ANY, b"invalid", b"structure"],), ret.args)
                self.assertIsNotNone(ret.exc_info)

            self.assertTrue(pr.received.empty())
            server.close()

        self.loop.run_until_complete(go())

    def test_malformed_args(self):
        async def go():
            port = find_unused_port()
            server = await aiozmq.rpc.serve_rpc(
                MyHandler(self.loop),
                bind="tcp://127.0.0.1:{}".format(port),
            )
            tr, pr = await create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.DEALER,
                connect="tcp://127.0.0.1:{}".format(port),
            )

            with log_hook("aiozmq.rpc", self.err_queue):
                tr.write([struct.pack("=HHLd", 1, 2, 3, 4), b"bad args", b"bad_kwargs"])

                ret = await self.err_queue.get()
                self.assertEqual(logging.CRITICAL, ret.levelno)
                self.assertEqual("Cannot unpack %r", ret.msg)
                self.assertEqual(
                    ([mock.ANY, mock.ANY, b"bad args", b"bad_kwargs"],), ret.args
                )
                self.assertIsNotNone(ret.exc_info)

            self.assertTrue(pr.received.empty())
            server.close()

        self.loop.run_until_complete(go())

    def test_malformed_kwargs(self):
        async def go():
            port = find_unused_port()
            server = await aiozmq.rpc.serve_rpc(
                MyHandler(self.loop),
                bind="tcp://127.0.0.1:{}".format(port),
            )
            tr, pr = await create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.DEALER,
                connect="tcp://127.0.0.1:{}".format(port),
            )

            with log_hook("aiozmq.rpc", self.err_queue):
                tr.write(
                    [
                        struct.pack("=HHLd", 1, 2, 3, 4),
                        msgpack.packb((1, 2)),
                        b"bad_kwargs",
                    ]
                )

                ret = await self.err_queue.get()
                self.assertEqual(logging.CRITICAL, ret.levelno)
                self.assertEqual("Cannot unpack %r", ret.msg)
                self.assertEqual(
                    ([mock.ANY, mock.ANY, mock.ANY, b"bad_kwargs"],), ret.args
                )
                self.assertIsNotNone(ret.exc_info)

            self.assertTrue(pr.received.empty())
            server.close()

        self.loop.run_until_complete(go())

    def test_unknown_format_at_client(self):
        async def go():
            port = find_unused_port()
            tr, pr = await create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.DEALER,
                bind="tcp://127.0.0.1:{}".format(port),
            )

            client = await aiozmq.rpc.connect_rpc(
                connect="tcp://127.0.0.1:{}".format(port)
            )

            with log_hook("aiozmq.rpc", self.err_queue):
                tr.write([b"invalid", b"structure"])

                ret = await self.err_queue.get()
                self.assertEqual(logging.CRITICAL, ret.levelno)
                self.assertEqual("Cannot unpack %r", ret.msg)
                self.assertEqual(([b"invalid", b"structure"],), ret.args)
                self.assertIsNotNone(ret.exc_info)

            client.close()

        self.loop.run_until_complete(go())

    def test_malformed_answer_at_client(self):
        async def go():
            port = find_unused_port()

            tr, pr = await create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.DEALER,
                bind="tcp://127.0.0.1:{}".format(port),
            )

            client = await aiozmq.rpc.connect_rpc(
                connect="tcp://127.0.0.1:{}".format(port)
            )

            with log_hook("aiozmq.rpc", self.err_queue):
                tr.write([struct.pack("=HHLd?", 1, 2, 3, 4, True), b"bad_answer"])

                ret = await self.err_queue.get()
                self.assertEqual(logging.CRITICAL, ret.levelno)
                self.assertEqual("Cannot unpack %r", ret.msg)
                self.assertEqual(([mock.ANY, b"bad_answer"],), ret.args)
                self.assertIsNotNone(ret.exc_info)

            client.close()
            tr.close()

        self.loop.run_until_complete(go())

    def test_unknown_req_id_at_client(self):
        async def go():
            port = find_unused_port()
            tr, pr = await create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.DEALER,
                bind="tcp://127.0.0.1:{}".format(port),
            )

            client = await aiozmq.rpc.connect_rpc(
                connect="tcp://127.0.0.1:{}".format(port)
            )

            with log_hook("aiozmq.rpc", self.err_queue):
                tr.write(
                    [struct.pack("=HHLd?", 1, 2, 34435, 4, True), msgpack.packb((1, 2))]
                )

                ret = await self.err_queue.get()
                self.assertEqual(logging.CRITICAL, ret.levelno)
                self.assertEqual("Unknown answer id: %d (%d %d %f %d) -> %s", ret.msg)
                self.assertEqual((mock.ANY, 1, 2, 4.0, True, (1, 2)), ret.args)
                self.assertIsNone(ret.exc_info)

            client.close()

        self.loop.run_until_complete(go())

    def test_overflow_client_counter(self):
        client, server = self.make_rpc_pair()

        async def communicate():
            client._proto.counter = 0xFFFFFFFF
            ret = await client.call.func(1)
            self.assertEqual(2, ret)
            self.assertEqual(0, client._proto.counter)
            client.close()
            await client.wait_closed()
            server.close()

        self.loop.run_until_complete(communicate())

    def test_log_exceptions(self):
        client, server = self.make_rpc_pair(log_exceptions=True)

        async def communicate():
            with log_hook("aiozmq.rpc", self.err_queue):
                with self.assertRaises(RuntimeError) as exc:
                    await client.call.exc(1)
                self.assertEqual(("bad arg", 1), exc.exception.args)

                ret = await self.err_queue.get()
                self.assertEqual(logging.ERROR, ret.levelno)
                self.assertEqual(
                    "An exception %r from method %r "
                    "call occurred.\n"
                    "args = %s\nkwargs = %s\n",
                    ret.msg,
                )
                self.assertEqual((mock.ANY, "exc", "(1,)", "{}"), ret.args)
                self.assertIsNotNone(ret.exc_info)

        self.loop.run_until_complete(communicate())

    def test_call_closed_rpc(self):
        client, server = self.make_rpc_pair()

        async def communicate():
            client.close()
            await client.wait_closed()
            with self.assertRaises(aiozmq.rpc.ServiceClosedError):
                await client.call.func()

        self.loop.run_until_complete(communicate())

    def test_call_closed_rpc_cancelled(self):
        client, server = self.make_rpc_pair()

        async def communicate():
            server.close()
            waiter = client.call.func()
            server.close()
            await server.wait_closed()
            client.close()
            await client.wait_closed()
            with self.assertRaises(asyncio.CancelledError):
                await waiter

        self.loop.run_until_complete(communicate())

    def test_server_close(self):
        client, server = self.make_rpc_pair()

        async def communicate():
            waiter = client.call.fut()
            await asyncio.sleep(0.01)
            self.assertEqual(1, len(server._proto.pending_waiters))
            task = next(iter(server._proto.pending_waiters))
            self.assertIsInstance(task, asyncio.Task)
            server.close()
            await server.wait_closed()
            await asyncio.sleep(0.01)
            self.assertEqual(0, len(server._proto.pending_waiters))
            del waiter

        self.loop.run_until_complete(communicate())

    @mock.patch("aiozmq.rpc.base.logger")
    def test_exclude_log_exceptions(self, m_log):
        client, server = self.make_rpc_pair(
            log_exceptions=True, exclude_log_exceptions=(MyException,)
        )

        async def communicate():
            with self.assertRaises(RuntimeError):
                await client.call.exc(1)
            m_log.exception.assert_called_with(
                "An exception %r from method %r call occurred.\n"
                "args = %s\nkwargs = %s\n",
                mock.ANY,
                mock.ANY,
                mock.ANY,
                mock.ANY,
            )
            m_log.reset_mock()
            with self.assertRaises(ValueError):
                await client.call.exc2()
            self.assertFalse(m_log.called)

        self.loop.run_until_complete(communicate())

    def test_client_restore_after_timeout(self):
        client, server = self.make_rpc_pair()

        async def communicate():
            with log_hook("aiozmq.rpc", self.err_queue):

                ret = await client.call.func(1)
                self.assertEqual(2, ret)

                with self.assertRaises(asyncio.TimeoutError):
                    await client.with_timeout(0.1).call.slow_call()

                ret = await client.call.func(2)
                self.assertEqual(3, ret)

                with self.assertRaises(asyncio.TimeoutError):
                    await client.with_timeout(0.1).call.slow_call()

                ret = await client.call.func(3)
                self.assertEqual(4, ret)

        self.loop.run_until_complete(communicate())

    def test_client_restore_after_timeout2(self):
        client, server = self.make_rpc_pair()

        async def communicate():
            with log_hook("aiozmq.rpc", self.err_queue):

                ret = await client.call.func(1)
                self.assertEqual(2, ret)

                with self.assertRaises(asyncio.TimeoutError):
                    await client.with_timeout(0.1).call.slow_call()

                await asyncio.sleep(0.3)

                ret = await client.call.func(2)
                self.assertEqual(3, ret)

                with self.assertRaises(asyncio.TimeoutError):
                    await client.with_timeout(0.1).call.slow_call()

                ret = await client.call.func(3)
                self.assertEqual(4, ret)

        self.loop.run_until_complete(communicate())

    def xtest_wait_closed(self):
        client, server = self.make_rpc_pair()

        async def go():
            f1 = client.call.not_so_fast()
            client.close()
            client.wait_closed()
            r = await f1
            self.assertEqual("ok", r)

        self.loop.run_until_complete(go())


class LoopRpcTests(unittest.TestCase, RpcTestsMixin):
    def setUp(self):
        self.loop = aiozmq.ZmqEventLoop()
        asyncio.set_event_loop(self.loop)
        self.client = self.server = None
        self.err_queue = asyncio.Queue()

    def tearDown(self):
        self.close_service(self.client)
        self.close_service(self.server)
        self.loop.close()
        asyncio.set_event_loop(None)
        # zmq.Context.instance().term()


class LoopLessRpcTests(unittest.TestCase, RpcTestsMixin):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.client = self.server = None
        self.err_queue = asyncio.Queue()

    def tearDown(self):
        self.close_service(self.client)
        self.close_service(self.server)
        self.loop.close()
        asyncio.set_event_loop(None)
        # zmq.Context.instance().term()


class AbstractHandlerTests(unittest.TestCase):
    def test___getitem__(self):
        class MyHandler(aiozmq.rpc.AbstractHandler):
            def __getitem__(self, key):
                return super().__getitem__(key)

        with self.assertRaises(KeyError):
            MyHandler()[1]

    def test_subclass(self):
        self.assertTrue(issubclass(dict, aiozmq.rpc.AbstractHandler))
        self.assertIsInstance({}, aiozmq.rpc.AbstractHandler)
        self.assertFalse(issubclass(object, aiozmq.rpc.AbstractHandler))
        self.assertNotIsInstance(object(), aiozmq.rpc.AbstractHandler)
        self.assertNotIsInstance("string", aiozmq.rpc.AbstractHandler)
        self.assertNotIsInstance(b"bytes", aiozmq.rpc.AbstractHandler)


class TestLogger(unittest.TestCase):
    def test_logger_name(self):
        self.assertEqual("aiozmq.rpc", logger.name)
