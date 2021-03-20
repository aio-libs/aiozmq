import asyncio
import errno
import os
import sys
import unittest
from unittest import mock

import aiozmq
import zmq
from aiozmq._test_util import check_errno, find_unused_port


class Protocol(aiozmq.ZmqProtocol):
    def __init__(self, loop):
        self.transport = None
        self.connected = asyncio.Future()
        self.closed = asyncio.Future()
        self.state = "INITIAL"
        self.received = asyncio.Queue()
        self.paused = False

    def connection_made(self, transport):
        self.transport = transport
        assert self.state == "INITIAL", self.state
        self.state = "CONNECTED"
        self.connected.set_result(None)

    def connection_lost(self, exc):
        assert self.state == "CONNECTED", self.state
        self.state = "CLOSED"
        self.transport = None
        self.closed.set_result(None)

    def pause_writing(self):
        self.paused = True

    def resume_writing(self):
        self.paused = False

    def msg_received(self, data):
        assert isinstance(data, list), data
        assert self.state == "CONNECTED", self.state
        self.received.put_nowait(data)


class BaseZmqEventLoopTestsMixin:
    async def make_dealer_router(self):
        port = find_unused_port()

        tr1, pr1 = await aiozmq.create_zmq_connection(
            lambda: Protocol(self.loop),
            zmq.DEALER,
            bind="tcp://127.0.0.1:{}".format(port),
        )
        self.assertEqual("CONNECTED", pr1.state)
        await pr1.connected

        tr2, pr2 = await aiozmq.create_zmq_connection(
            lambda: Protocol(self.loop),
            zmq.ROUTER,
            connect="tcp://127.0.0.1:{}".format(port),
        )
        self.assertEqual("CONNECTED", pr2.state)
        await pr2.connected

        return tr1, pr1, tr2, pr2

    async def make_pub_sub(self):
        port = find_unused_port()

        tr1, pr1 = await aiozmq.create_zmq_connection(
            lambda: Protocol(self.loop),
            zmq.PUB,
            bind="tcp://127.0.0.1:{}".format(port),
        )
        self.assertEqual("CONNECTED", pr1.state)
        await pr1.connected

        tr2, pr2 = await aiozmq.create_zmq_connection(
            lambda: Protocol(self.loop),
            zmq.SUB,
            connect="tcp://127.0.0.1:{}".format(port),
        )
        self.assertEqual("CONNECTED", pr2.state)
        await pr2.connected

        return tr1, pr1, tr2, pr2

    def test_req_rep(self):
        async def connect_req():
            tr1, pr1 = await aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.REQ,
                bind="inproc://test",
            )
            self.assertEqual("CONNECTED", pr1.state)
            await pr1.connected
            return tr1, pr1

        tr1, pr1 = self.loop.run_until_complete(connect_req())

        async def connect_rep():
            tr2, pr2 = await aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.REP,
                connect="inproc://test",
            )
            self.assertEqual("CONNECTED", pr2.state)
            await pr2.connected
            return tr2, pr2

        tr2, pr2 = self.loop.run_until_complete(connect_rep())
        # Without this, this test hangs for some reason.
        tr2._zmq_sock.getsockopt(zmq.EVENTS)

        async def communicate():
            tr1.write([b"request"])
            request = await pr2.received.get()
            self.assertEqual([b"request"], request)
            tr2.write([b"answer"])
            answer = await pr1.received.get()
            self.assertEqual([b"answer"], answer)

        self.loop.run_until_complete(communicate())

        async def closing():
            tr1.close()
            tr2.close()

            await pr1.closed
            self.assertEqual("CLOSED", pr1.state)
            await pr2.closed
            self.assertEqual("CLOSED", pr2.state)

        self.loop.run_until_complete(closing())

    def test_pub_sub(self):
        async def go():
            tr1, pr1, tr2, pr2 = await self.make_pub_sub()
            tr2.setsockopt(zmq.SUBSCRIBE, b"node_id")

            for i in range(5):
                tr1.write([b"node_id", b"publish"])
                try:
                    request = await asyncio.wait_for(pr2.received.get(), 0.1)
                    self.assertEqual([b"node_id", b"publish"], request)
                    break
                except asyncio.TimeoutError:
                    pass
            else:
                raise AssertionError("Cannot get message in subscriber")

            tr1.close()
            tr2.close()
            await pr1.closed
            self.assertEqual("CLOSED", pr1.state)
            await pr2.closed
            self.assertEqual("CLOSED", pr2.state)

        self.loop.run_until_complete(go())

    def test_getsockopt(self):
        port = find_unused_port()

        async def coro():
            tr, pr = await aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.DEALER,
                bind="tcp://127.0.0.1:{}".format(port),
            )
            await pr.connected
            self.assertEqual(zmq.DEALER, tr.getsockopt(zmq.TYPE))
            return tr, pr

        self.loop.run_until_complete(coro())

    def test_dealer_router(self):
        async def go():
            tr1, pr1, tr2, pr2 = await self.make_dealer_router()
            tr1.write([b"request"])
            request = await pr2.received.get()
            self.assertEqual([mock.ANY, b"request"], request)
            tr2.write([request[0], b"answer"])
            answer = await pr1.received.get()
            self.assertEqual([b"answer"], answer)

            tr1.close()
            tr2.close()

            await pr1.closed
            self.assertEqual("CLOSED", pr1.state)
            await pr2.closed
            self.assertEqual("CLOSED", pr2.state)

        self.loop.run_until_complete(go())

    def test_binds(self):
        port1 = find_unused_port()
        port2 = find_unused_port()
        addr1 = "tcp://127.0.0.1:{}".format(port1)
        addr2 = "tcp://127.0.0.1:{}".format(port2)

        async def connect():
            tr, pr = await aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.REQ,
                bind=[addr1, addr2],
            )
            await pr.connected

            self.assertEqual({addr1, addr2}, tr.bindings())

            addr3 = await tr.bind("tcp://127.0.0.1:*")
            self.assertEqual({addr1, addr2, addr3}, tr.bindings())
            await tr.unbind(addr2)
            self.assertEqual({addr1, addr3}, tr.bindings())
            self.assertIn(addr1, tr.bindings())
            self.assertRegex(
                repr(tr.bindings()), r"{tcp://127.0.0.1:.\d+, tcp://127.0.0.1:\d+}"
            )
            tr.close()

        self.loop.run_until_complete(connect())

    def test_connects(self):
        port1 = find_unused_port()
        port2 = find_unused_port()
        port3 = find_unused_port()
        addr1 = "tcp://127.0.0.1:{}".format(port1)
        addr2 = "tcp://127.0.0.1:{}".format(port2)
        addr3 = "tcp://127.0.0.1:{}".format(port3)

        async def go():
            tr, pr = await aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.REQ,
                connect=[addr1, addr2],
            )
            await pr.connected

            self.assertEqual({addr1, addr2}, tr.connections())
            await tr.connect(addr3)
            self.assertEqual({addr1, addr3, addr2}, tr.connections())
            await tr.disconnect(addr1)
            self.assertEqual({addr2, addr3}, tr.connections())
            tr.close()

        self.loop.run_until_complete(go())

    def test_zmq_socket(self):
        zmq_sock = zmq.Context.instance().socket(zmq.PUB)

        async def connect():
            tr, pr = await aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop), zmq.PUB, zmq_sock=zmq_sock
            )
            await pr.connected
            return tr, pr

        tr, pr = self.loop.run_until_complete(connect())
        self.assertIs(zmq_sock, tr._zmq_sock)
        self.assertFalse(zmq_sock.closed)
        tr.close()

    def test_zmq_socket_invalid_type(self):
        zmq_sock = zmq.Context.instance().socket(zmq.PUB)

        async def connect():
            tr, pr = await aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop), zmq.SUB, zmq_sock=zmq_sock
            )
            await pr.connected
            return tr, pr

        with self.assertRaises(ValueError):
            self.loop.run_until_complete(connect())
        self.assertFalse(zmq_sock.closed)

    def test_create_zmq_connection_ZMQError(self):
        zmq_sock = zmq.Context.instance().socket(zmq.PUB)
        zmq_sock.close()

        async def connect():
            tr, pr = await aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop), zmq.SUB, zmq_sock=zmq_sock
            )
            await pr.connected
            return tr, pr

        with self.assertRaises(OSError) as ctx:
            self.loop.run_until_complete(connect())
        self.assertIn(ctx.exception.errno, (zmq.ENOTSUP, zmq.ENOTSOCK))

    def test_create_zmq_connection_invalid_bind(self):
        async def connect():
            tr, pr = await aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop), zmq.SUB, bind=2
            )

        with self.assertRaises(ValueError):
            self.loop.run_until_complete(connect())

    def test_create_zmq_connection_invalid_connect(self):
        async def connect():
            tr, pr = await aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop), zmq.SUB, connect=2
            )

        with self.assertRaises(ValueError):
            self.loop.run_until_complete(connect())

    @unittest.skipIf(sys.platform == "win32", "Windows calls abort() on bad socket")
    def test_create_zmq_connection_closes_socket_on_bad_bind(self):
        async def connect():
            tr, pr = await aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop), zmq.SUB, bind="badaddr"
            )
            await pr.connected
            return tr, pr

        with self.assertRaises(OSError):
            self.loop.run_until_complete(connect())

    @unittest.skipIf(sys.platform == "win32", "Windows calls abort() on bad socket")
    def test_create_zmq_connection_closes_socket_on_bad_connect(self):
        async def connect():
            with self.assertRaises(OSError):
                await aiozmq.create_zmq_connection(
                    lambda: Protocol(self.loop),
                    zmq.SUB,
                    connect="badaddr",
                )

        self.loop.run_until_complete(connect())

    def test_create_zmq_connection_dns_in_connect(self):
        port = find_unused_port()

        async def connect():
            addr = "tcp://localhost:{}".format(port)
            tr, pr = await aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop), zmq.SUB, connect=addr
            )
            await pr.connected

            self.assertEqual({addr}, tr.connections())
            tr.close()

        self.loop.run_until_complete(connect())

    def test_getsockopt_badopt(self):
        port = find_unused_port()

        async def connect():
            tr, pr = await aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.SUB,
                connect="tcp://127.0.0.1:{}".format(port),
            )
            await pr.connected
            return tr, pr

        tr, pr = self.loop.run_until_complete(connect())

        with self.assertRaises(OSError) as ctx:
            tr.getsockopt(1111)  # invalid option
        self.assertEqual(zmq.EINVAL, ctx.exception.errno)

    def test_setsockopt_badopt(self):
        port = find_unused_port()

        async def connect():
            tr, pr = await aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.SUB,
                connect="tcp://127.0.0.1:{}".format(port),
            )
            await pr.connected
            return tr, pr

        tr, pr = self.loop.run_until_complete(connect())

        with self.assertRaises(OSError) as ctx:
            tr.setsockopt(1111, 1)  # invalid option
        self.assertEqual(zmq.EINVAL, ctx.exception.errno)

    def test_unbind_from_nonbinded_addr(self):
        port = find_unused_port()
        addr = "tcp://127.0.0.1:{}".format(port)

        async def connect():
            tr, pr = await aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop), zmq.SUB, bind=addr
            )
            await pr.connected

            self.assertEqual({addr}, tr.bindings())
            with self.assertRaises(OSError) as ctx:
                await tr.unbind("ipc:///some-addr")  # non-bound addr

            # TODO: check travis build and remove skip when test passed.
            if ctx.exception.errno == zmq.EAGAIN and os.environ.get("TRAVIS"):
                raise unittest.SkipTest(
                    "Travis has a bug, it returns " "EAGAIN for unknown endpoint"
                )
            self.assertIn(ctx.exception.errno, (errno.ENOENT, zmq.EPROTONOSUPPORT))
            self.assertEqual({addr}, tr.bindings())

        self.loop.run_until_complete(connect())

    def test_disconnect_from_nonbinded_addr(self):
        port = find_unused_port()
        addr = "tcp://127.0.0.1:{}".format(port)

        async def go():
            tr, pr = await aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop), zmq.SUB, connect=addr
            )
            await pr.connected

            self.assertEqual({addr}, tr.connections())
            with self.assertRaises(OSError) as ctx:
                await tr.disconnect("ipc:///some-addr")  # non-bound addr

            # TODO: check travis build and remove skip when test passed.
            if ctx.exception.errno == zmq.EAGAIN and os.environ.get("TRAVIS"):
                raise unittest.SkipTest(
                    "Travis has a bug, it returns " "EAGAIN for unknown endpoint"
                )
            self.assertIn(ctx.exception.errno, (errno.ENOENT, zmq.EPROTONOSUPPORT))
            self.assertEqual({addr}, tr.connections())

        self.loop.run_until_complete(go())

    def test_subscriptions_of_invalid_socket(self):
        async def connect():
            tr, pr = await aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.PUSH,
                bind="tcp://127.0.0.1:*",
            )
            await pr.connected
            return tr, pr

        tr, pr = self.loop.run_until_complete(connect())
        self.assertRaises(NotImplementedError, tr.subscribe, b"a")
        self.assertRaises(NotImplementedError, tr.unsubscribe, b"a")
        self.assertRaises(NotImplementedError, tr.subscriptions)

    def test_double_subscribe(self):
        async def connect():
            tr, pr = await aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.SUB,
                bind="tcp://127.0.0.1:*",
            )
            await pr.connected
            return tr, pr

        tr, pr = self.loop.run_until_complete(connect())
        tr.subscribe(b"val")
        self.assertEqual({b"val"}, tr.subscriptions())

        tr.subscribe(b"val")
        self.assertEqual({b"val"}, tr.subscriptions())

    def test_double_unsubscribe(self):
        async def connect():
            tr, pr = await aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.SUB,
                bind="tcp://127.0.0.1:*",
            )
            await pr.connected
            return tr, pr

        try:
            tr, pr = self.loop.run_until_complete(connect())
            tr.subscribe(b"val")
            self.assertEqual({b"val"}, tr.subscriptions())

            tr.unsubscribe(b"val")
            self.assertFalse(tr.subscriptions())
            tr.unsubscribe(b"val")
            self.assertFalse(tr.subscriptions())
        except OSError as exc:
            if exc.errno == errno.ENOTSOCK:
                # I'm sad but ZMQ sometimes throws that error
                raise unittest.SkipTest("Malformed answer")

    def test_unsubscribe_unknown_filter(self):
        async def connect():
            tr, pr = await aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.SUB,
                bind="tcp://127.0.0.1:*",
            )
            await pr.connected
            return tr, pr

        tr, pr = self.loop.run_until_complete(connect())

        tr.unsubscribe(b"val")
        self.assertFalse(tr.subscriptions())
        tr.unsubscribe(b"val")
        self.assertFalse(tr.subscriptions())

    def test_endpoint_is_not_a_str(self):
        async def go():
            tr, pr = await aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.PUSH,
                bind="tcp://127.0.0.1:*",
            )
            await pr.connected

            with self.assertRaises(TypeError):
                await tr.bind(123)

            with self.assertRaises(TypeError):
                await tr.unbind(123)

            with self.assertRaises(TypeError):
                await tr.connect(123)

            with self.assertRaises(TypeError):
                await tr.disconnect(123)

        self.loop.run_until_complete(go())

    def test_transfer_big_data(self):
        async def go():
            tr1, pr1, tr2, pr2 = await self.make_dealer_router()

            start = 65
            cnt = 26
            data = [chr(i).encode("ascii") * 1000 for i in range(start, start + cnt)]

            for i in range(2000):
                tr1.write(data)

            request = await pr2.received.get()
            self.assertEqual([mock.ANY] + data, request)

            tr1.close()
            tr2.close()

        self.loop.run_until_complete(go())

    def test_transfer_big_data_send_after_closing(self):
        async def go():
            tr1, pr1, tr2, pr2 = await self.make_dealer_router()

            start = 65
            cnt = 26
            data = [chr(i).encode("ascii") * 1000 for i in range(start, start + cnt)]

            self.assertFalse(pr1.paused)

            for i in range(10000):
                tr1.write(data)

            self.assertTrue(tr1._buffer)
            self.assertTrue(pr1.paused)
            tr1.close()

            for i in range(10000):
                request = await pr2.received.get()
                self.assertEqual([mock.ANY] + data, request)
            tr2.close()

        self.loop.run_until_complete(go())

    def test_default_event_loop(self):
        asyncio.set_event_loop(self.loop)
        port = find_unused_port()
        tr1, pr1 = self.loop.run_until_complete(
            aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.REQ,
                bind="tcp://127.0.0.1:{}".format(port),
            )
        )
        self.assertIs(self.loop, tr1._loop)
        tr1.close()

    def test_close_closing(self):
        port = find_unused_port()
        tr1, pr1 = self.loop.run_until_complete(
            aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.REQ,
                bind="tcp://127.0.0.1:{}".format(port),
            )
        )
        tr1.close()
        self.assertTrue(tr1._closing)
        tr1.close()
        self.assertTrue(tr1._closing)

    def test_pause_reading(self):
        port = find_unused_port()
        tr1, pr1 = self.loop.run_until_complete(
            aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.REQ,
                bind="tcp://127.0.0.1:{}".format(port),
            )
        )
        self.assertFalse(tr1._paused)
        tr1.pause_reading()
        self.assertTrue(tr1._paused)
        tr1.resume_reading()
        self.assertFalse(tr1._paused)
        tr1.close()

    def test_pause_reading_closed(self):
        port = find_unused_port()
        tr1, pr1 = self.loop.run_until_complete(
            aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.REQ,
                bind="tcp://127.0.0.1:{}".format(port),
            )
        )
        tr1.close()
        with self.assertRaises(RuntimeError):
            tr1.pause_reading()

    def test_pause_reading_paused(self):
        port = find_unused_port()
        tr1, pr1 = self.loop.run_until_complete(
            aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.REQ,
                bind="tcp://127.0.0.1:{}".format(port),
            )
        )
        tr1.pause_reading()
        self.assertTrue(tr1._paused)
        with self.assertRaises(RuntimeError):
            tr1.pause_reading()
        tr1.close()

    def test_resume_reading_not_paused(self):
        port = find_unused_port()
        tr1, pr1 = self.loop.run_until_complete(
            aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.REQ,
                bind="tcp://127.0.0.1:{}".format(port),
            )
        )
        with self.assertRaises(RuntimeError):
            tr1.resume_reading()
        tr1.close()

    @mock.patch("aiozmq.core.logger")
    def test_warning_on_connection_lost(self, m_log):
        port = find_unused_port()
        tr1, pr1 = self.loop.run_until_complete(
            aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.REQ,
                bind="tcp://127.0.0.1:{}".format(port),
            )
        )
        self.assertEqual(0, tr1._conn_lost)
        tr1.LOG_THRESHOLD_FOR_CONNLOST_WRITES = 2
        tr1.close()
        self.assertEqual(1, tr1._conn_lost)
        tr1.write([b"data"])
        self.assertEqual(2, tr1._conn_lost)
        self.assertFalse(m_log.warning.called)
        tr1.write([b"data"])
        self.assertEqual(3, tr1._conn_lost)
        m_log.warning.assert_called_with("write to closed ZMQ socket.")

    def test_close_on_error(self):
        port = find_unused_port()
        tr1, pr1 = self.loop.run_until_complete(
            aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.REQ,
                bind="tcp://127.0.0.1:{}".format(port),
            )
        )
        handler = mock.Mock()
        self.loop.set_exception_handler(handler)
        sock = tr1.get_extra_info("zmq_socket")
        sock.close()
        tr1.write([b"data"])
        self.assertTrue(tr1._closing)
        handler.assert_called_with(
            self.loop,
            {
                "protocol": pr1,
                "exception": mock.ANY,
                "transport": tr1,
                "message": "Fatal write error on zmq socket transport",
            },
        )
        # expecting 'Socket operation on non-socket'
        if sys.platform == "darwin":
            errno = 38
        else:
            errno = 88
        check_errno(errno, handler.call_args[0][1]["exception"])

    def test_double_force_close(self):
        port = find_unused_port()
        tr1, pr1 = self.loop.run_until_complete(
            aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.REQ,
                bind="tcp://127.0.0.1:{}".format(port),
            )
        )
        handler = mock.Mock()
        self.loop.set_exception_handler(handler)
        err = RuntimeError("error")
        tr1._fatal_error(err)
        tr1._fatal_error(err)
        self.loop.run_until_complete(pr1.closed)

    def test___repr__(self):
        port = find_unused_port()

        async def coro():
            tr, pr = await aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.DEALER,
                bind="tcp://127.0.0.1:{}".format(port),
            )
            await pr.connected
            self.assertRegex(
                repr(tr),
                "<ZmqTransport sock=<[^>]+> "
                "type=DEALER read=idle write=<idle, bufsize=0>>",
            )
            tr.close()

        self.loop.run_until_complete(coro())

    def test_extra_zmq_type(self):
        port = find_unused_port()

        async def coro():
            tr, pr = await aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.DEALER,
                bind="tcp://127.0.0.1:{}".format(port),
            )
            await pr.connected

            self.assertEqual(zmq.DEALER, tr.get_extra_info("zmq_type"))
            tr.close()

        self.loop.run_until_complete(coro())

    @unittest.skipIf(
        zmq.zmq_version_info() < (4,)
        or zmq.pyzmq_version_info()
        < (
            14,
            4,
        ),
        "Socket monitor requires libzmq >= 4 and pyzmq >= 14.4",
    )
    def test_implicit_monitor_disable(self):
        async def go():

            tr, pr = await aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop), zmq.DEALER
            )
            await pr.connected

            await tr.enable_monitor()

            tr.close()
            await pr.closed

            self.assertIsNone(tr._monitor)

        self.loop.run_until_complete(go())

    @unittest.skipIf(
        zmq.zmq_version_info() < (4,)
        or zmq.pyzmq_version_info()
        < (
            14,
            4,
        ),
        "Socket monitor requires libzmq >= 4 and pyzmq >= 14.4",
    )
    def test_force_close_monitor(self):
        async def go():

            tr, pr = await aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop), zmq.DEALER
            )
            await pr.connected

            await tr.enable_monitor()

            tr.abort()
            await pr.closed

            self.assertIsNone(tr._monitor)

        self.loop.run_until_complete(go())


class ZmqEventLoopTests(BaseZmqEventLoopTestsMixin, unittest.TestCase):
    def setUp(self):
        self.loop = aiozmq.ZmqEventLoop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()
        asyncio.set_event_loop(None)
        # zmq.Context.instance().term()


class ZmqLooplessTests(BaseZmqEventLoopTestsMixin, unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()
        asyncio.set_event_loop(None)
        # zmq.Context.instance().term()

    def test_unsubscribe_from_fd_on_error(self):
        port = find_unused_port()
        tr1, pr1 = self.loop.run_until_complete(
            aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.REQ,
                bind="tcp://127.0.0.1:{}".format(port),
            )
        )
        handler = mock.Mock()
        self.loop.set_exception_handler(handler)
        sock = tr1.get_extra_info("zmq_socket")
        sock.close()
        tr1.write([b"data"])
        with self.assertRaises(KeyError):
            self.loop._selector.get_key(tr1._fd)


class ZmqEventLoopExternalContextTests(unittest.TestCase):
    def setUp(self):
        self.ctx = zmq.Context()
        self.loop = aiozmq.ZmqEventLoop(zmq_context=self.ctx)
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()
        asyncio.set_event_loop(None)
        self.ctx.term()

    def test_using_external_zmq_context(self):
        port = find_unused_port()

        async def go():

            st, sp = await aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.ROUTER,
                bind="tcp://127.0.0.1:{}".format(port),
            )
            await sp.connected
            addr = list(st.bindings())[0]

            ct, cp = await aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop), zmq.DEALER, connect=addr
            )
            await cp.connected

            ct.close()
            await cp.closed
            st.close()
            await sp.closed

        self.loop.run_until_complete(go())
