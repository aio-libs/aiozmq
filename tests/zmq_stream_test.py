import unittest
import asyncio
import aiozmq
import zmq
from unittest import mock

from aiozmq._test_util import find_unused_port


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
            s1 = yield from aiozmq.create_zmq_connection(
                zmq.DEALER,
                bind='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop)

            s2 = yield from aiozmq.create_zmq_connection(
                zmq.ROUTER,
                connect='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop)

            s1.write([b'request'])
            req = yield from s2.read()
            self.assertEqual((mock.ANY, b'request',), req)
            s2.write([req[0], b'answer'])
            answer = yield from s1.read()
            self.assertEqual((b'answer',), answer)

        self.loop.run_until_complete(go())

    def test_closed(self):
        port = find_unused_port()

        @asyncio.coroutine
        def go():
            s1 = yield from aiozmq.create_zmq_connection(
                zmq.DEALER,
                bind='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop)

            s2 = yield from aiozmq.create_zmq_connection(
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
        port = find_unused_port()

        @asyncio.coroutine
        def go():
            s1 = yield from aiozmq.create_zmq_connection(
                zmq.DEALER,
                bind='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop)

            self.assertIsInstance(s1.transport, aiozmq.ZmqTransport)
            s1.close()
            with self.assertRaises(aiozmq.ZmqStreamClosed):
                yield from s1.read()
            self.assertIsNone(s1.transport)

        self.loop.run_until_complete(go())

    def test_get_extra_info(self):
        port = find_unused_port()

        @asyncio.coroutine
        def go():
            s1 = yield from aiozmq.create_zmq_connection(
                zmq.DEALER,
                bind='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop)

            self.assertIsInstance(s1.get_extra_info('zmq_socket'),
                                  zmq.Socket)

        self.loop.run_until_complete(go())

    def test_exception(self):
        port = find_unused_port()

        @asyncio.coroutine
        def go():
            s1 = yield from aiozmq.create_zmq_connection(
                zmq.DEALER,
                bind='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop)

            self.assertIsNone(s1.exception())

        self.loop.run_until_complete(go())
