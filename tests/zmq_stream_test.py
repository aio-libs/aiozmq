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

            s2.close()
            s1.write([b'request'])
            req = yield from s2.read()
            self.assertEqual((mock.ANY, b'request',), req)
            s2.write([req[0], b'answer'])
            answer = yield from s1.read()
            self.assertEqual((b'answer',), answer)

        self.loop.run_until_complete(go())
