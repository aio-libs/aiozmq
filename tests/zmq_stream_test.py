import unittest
import asyncio
import aiozmq
import zmq
from unittest import mock

from aiozmq._test_util import check_errno, find_unused_port


class ZmqStreamTests(unittest.TestCase):

    def setUp(self):
        self.loop = aiozmq.ZmqEventLoop()
        asyncio.set_event_loop(None)

    def tearDown(self):
        self.loop.close()

    def test_req_rep(self):
        port = find_unused_port()

        @asyncio.coroutine
        def go():
            s1 = yield from aiozmq.create_zmq_stream(
                zmq.DEALER,
                bind='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop)

            s2 = yield from aiozmq.create_zmq_stream(
                zmq.ROUTER,
                connect='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop)

            s1.write([b'request'])
            req = yield from s2.read()
            self.assertEqual([mock.ANY, b'request'], req)
            s2.write([req[0], b'answer'])
            answer = yield from s1.read()
            self.assertEqual([b'answer'], answer)

        self.loop.run_until_complete(go())

    def test_closed(self):
        port = find_unused_port()

        @asyncio.coroutine
        def go():
            s1 = yield from aiozmq.create_zmq_stream(
                zmq.DEALER,
                bind='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop)

            s2 = yield from aiozmq.create_zmq_stream(
                zmq.ROUTER,
                connect='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop)

            self.assertFalse(s2.at_closing())
            s2.close()
            s1.write([b'request'])
            with self.assertRaises(aiozmq.ZmqStreamClosed):
                yield from s2.read()
            self.assertTrue(s2.at_closing())

        self.loop.run_until_complete(go())

    def test_transport(self):

        @asyncio.coroutine
        def go():
            s1 = yield from aiozmq.create_zmq_stream(
                zmq.DEALER,
                bind='tcp://127.0.0.1:*',
                loop=self.loop)

            self.assertIsInstance(s1.transport, aiozmq.ZmqTransport)
            s1.close()
            with self.assertRaises(aiozmq.ZmqStreamClosed):
                yield from s1.read()
            self.assertIsNone(s1.transport)

        self.loop.run_until_complete(go())

    def test_get_extra_info(self):

        @asyncio.coroutine
        def go():
            s1 = yield from aiozmq.create_zmq_stream(
                zmq.DEALER,
                bind='tcp://127.0.0.1:*',
                loop=self.loop)

            self.assertIsInstance(s1.get_extra_info('zmq_socket'),
                                  zmq.Socket)

        self.loop.run_until_complete(go())

    def test_exception(self):

        @asyncio.coroutine
        def go():
            s1 = yield from aiozmq.create_zmq_stream(
                zmq.DEALER,
                bind='tcp://127.0.0.1:*',
                loop=self.loop)

            self.assertIsNone(s1.exception())

        self.loop.run_until_complete(go())

    def test_default_loop(self):
        asyncio.set_event_loop(self.loop)

        @asyncio.coroutine
        def go():
            s1 = yield from aiozmq.create_zmq_stream(
                zmq.DEALER,
                bind='tcp://127.0.0.1:*')

            s1.close()

        self.loop.run_until_complete(go())

    def test_set_read_buffer_limits1(self):
        @asyncio.coroutine
        def go():
            s1 = yield from aiozmq.create_zmq_stream(
                zmq.DEALER,
                bind='tcp://127.0.0.1:*',
                loop=self.loop)

            s1.set_read_buffer_limits(low=10)
            self.assertEqual(10, s1._low_water)
            self.assertEqual(40, s1._high_water)

            s1.close()

        self.loop.run_until_complete(go())

    def test_set_read_buffer_limits2(self):
        @asyncio.coroutine
        def go():
            s1 = yield from aiozmq.create_zmq_stream(
                zmq.DEALER,
                bind='tcp://127.0.0.1:*',
                loop=self.loop)

            s1.set_read_buffer_limits(high=60)
            self.assertEqual(15, s1._low_water)
            self.assertEqual(60, s1._high_water)

            s1.close()

        self.loop.run_until_complete(go())

    def test_set_read_buffer_limits3(self):
        @asyncio.coroutine
        def go():
            s1 = yield from aiozmq.create_zmq_stream(
                zmq.DEALER,
                bind='tcp://127.0.0.1:*',
                loop=self.loop)

            with self.assertRaises(ValueError):
                s1.set_read_buffer_limits(high=1, low=2)

            s1.close()

        self.loop.run_until_complete(go())

    def test_pause_reading(self):
        port = find_unused_port()

        @asyncio.coroutine
        def go():
            s1 = yield from aiozmq.create_zmq_stream(
                zmq.DEALER,
                bind='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop)

            s2 = yield from aiozmq.create_zmq_stream(
                zmq.ROUTER,
                connect='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop)

            s2.set_read_buffer_limits(high=5)
            s1.write([b'request'])

            yield from asyncio.sleep(0.01, loop=self.loop)
            self.assertTrue(s2._paused)

            msg = yield from s2.read()
            self.assertEqual([mock.ANY, b'request'], msg)
            self.assertFalse(s2._paused)

        self.loop.run_until_complete(go())

    def test_set_exception(self):

        @asyncio.coroutine
        def go():
            s1 = yield from aiozmq.create_zmq_stream(
                zmq.DEALER,
                bind='tcp://127.0.0.1:*',
                loop=self.loop)

            exc = RuntimeError('some exc')
            s1.set_exception(exc)
            self.assertIs(exc, s1.exception())

            with self.assertRaisesRegex(RuntimeError, 'some exc'):
                yield from s1.read()

        self.loop.run_until_complete(go())

    def test_set_exception_with_waiter(self):

        @asyncio.coroutine
        def go():
            s1 = yield from aiozmq.create_zmq_stream(
                zmq.DEALER,
                bind='tcp://127.0.0.1:*',
                loop=self.loop)

            def f():
                yield from s1.read()

            t1 = asyncio.async(f(), loop=self.loop)
            # to run f() up to yield from
            yield from asyncio.sleep(0.001, loop=self.loop)

            self.assertIsNotNone(s1._waiter)

            exc = RuntimeError('some exc')
            s1.set_exception(exc)
            self.assertIs(exc, s1.exception())

            with self.assertRaisesRegex(RuntimeError, 'some exc'):
                yield from s1.read()

            t1.cancel()

        self.loop.run_until_complete(go())

    def test_set_exception_with_cancelled_waiter(self):

        @asyncio.coroutine
        def go():
            s1 = yield from aiozmq.create_zmq_stream(
                zmq.DEALER,
                bind='tcp://127.0.0.1:*',
                loop=self.loop)

            def f():
                yield from s1.read()

            t1 = asyncio.async(f(), loop=self.loop)
            # to run f() up to yield from
            yield from asyncio.sleep(0.001, loop=self.loop)

            self.assertIsNotNone(s1._waiter)
            t1.cancel()

            exc = RuntimeError('some exc')
            s1.set_exception(exc)
            self.assertIs(exc, s1.exception())

            with self.assertRaisesRegex(RuntimeError, 'some exc'):
                yield from s1.read()

        self.loop.run_until_complete(go())

    def test_double_reading(self):
        @asyncio.coroutine
        def go():
            s1 = yield from aiozmq.create_zmq_stream(
                zmq.DEALER,
                bind='tcp://127.0.0.1:*',
                loop=self.loop)

            def f():
                yield from s1.read()

            t1 = asyncio.async(f(), loop=self.loop)
            # to run f() up to yield from
            yield from asyncio.sleep(0.001, loop=self.loop)

            with self.assertRaises(RuntimeError):
                yield from s1.read()

            t1.cancel()

        self.loop.run_until_complete(go())

    def test_close_on_reading(self):
        port = find_unused_port()

        @asyncio.coroutine
        def go():
            s1 = yield from aiozmq.create_zmq_stream(
                zmq.DEALER,
                bind='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop)

            def f():
                yield from s1.read()

            t1 = asyncio.async(f(), loop=self.loop)
            # to run f() up to yield from
            yield from asyncio.sleep(0.001, loop=self.loop)

            s1.close()
            yield from asyncio.sleep(0.001, loop=self.loop)

            with self.assertRaises(aiozmq.ZmqStreamClosed):
                t1.result()

        self.loop.run_until_complete(go())

    def test_close_on_cancelled_reading(self):
        port = find_unused_port()

        @asyncio.coroutine
        def go():
            s1 = yield from aiozmq.create_zmq_stream(
                zmq.DEALER,
                bind='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop)

            def f():
                yield from s1.read()

            t1 = asyncio.async(f(), loop=self.loop)
            # to run f() up to yield from
            yield from asyncio.sleep(0.001, loop=self.loop)

            t1.cancel()
            s1.feed_closing()

            yield from asyncio.sleep(0.001, loop=self.loop)
            with self.assertRaises(asyncio.CancelledError):
                t1.result()

        self.loop.run_until_complete(go())

    def test_feed_cancelled_msg(self):
        port = find_unused_port()

        @asyncio.coroutine
        def go():
            s1 = yield from aiozmq.create_zmq_stream(
                zmq.DEALER,
                bind='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop)

            def f():
                yield from s1.read()

            t1 = asyncio.async(f(), loop=self.loop)
            # to run f() up to yield from
            yield from asyncio.sleep(0.001, loop=self.loop)

            t1.cancel()
            s1.feed_msg([b'data'])

            yield from asyncio.sleep(0.001, loop=self.loop)
            with self.assertRaises(asyncio.CancelledError):
                t1.result()

            self.assertEqual(4, s1._queue_len)
            self.assertEqual((4, [b'data']), s1._queue.popleft())

        self.loop.run_until_complete(go())

    def test_error_on_read(self):
        port = find_unused_port()

        @asyncio.coroutine
        def go():
            s1 = yield from aiozmq.create_zmq_stream(
                zmq.REP,
                bind='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop)
            handler = mock.Mock()
            self.loop.set_exception_handler(handler)
            s1.write([b'data'])
            with self.assertRaises(OSError) as ctx:
                yield from s1.read()
            check_errno(zmq.EFSM, ctx.exception)
            with self.assertRaises(OSError) as ctx2:
                yield from s1.drain()
            check_errno(zmq.EFSM, ctx2.exception)

        self.loop.run_until_complete(go())

    def test_drain(self):
        port = find_unused_port()

        @asyncio.coroutine
        def go():
            s1 = yield from aiozmq.create_zmq_stream(
                zmq.REP,
                bind='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop)
            yield from s1.drain()

        self.loop.run_until_complete(go())
