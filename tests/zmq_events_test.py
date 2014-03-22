import unittest
import asyncio
import aiozmq
import time
import zmq
from unittest import mock

from test import support  # import from standard python test suite


class Protocol(aiozmq.ZmqProtocol):

    def __init__(self, loop):
        self.transport = None
        self.connected = asyncio.Future(loop=loop)
        self.closed = asyncio.Future(loop=loop)
        self.state = 'INITIAL'
        self.received = asyncio.Queue(loop=loop)

    def connection_made(self, transport):
        self.transport = transport
        assert self.state == 'INITIAL', self.state
        self.state = 'CONNECTED'
        self.connected.set_result(None)

    def connection_lost(self, exc):
        assert self.state == 'CONNECTED', self.state
        self.state = 'CLOSED'
        self.closed.set_result(None)
        self.transport = None

    def pause_writing(self):
        pass

    def resume_writing(self):
        pass

    def msg_received(self, data):
        assert isinstance(data, tuple), data
        assert self.state == 'CONNECTED', self.state
        self.received.put_nowait(data)


class ZmqEventLoopTests(unittest.TestCase):

    def setUp(self):
        self.loop = aiozmq.ZmqEventLoop()
        asyncio.set_event_loop(None)

    def tearDown(self):
        self.loop.close()

    def test_req_rep(self):
        port = support.find_unused_port()

        @asyncio.coroutine
        def connect_req():
            tr1, pr1 = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.REQ,
                bind='tcp://127.0.0.1:{}'.format(port))
            self.assertEqual('CONNECTED', pr1.state)
            yield from pr1.connected
            return tr1, pr1

        tr1, pr1 = self.loop.run_until_complete(connect_req())

        @asyncio.coroutine
        def connect_rep():
            tr2, pr2 = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.REP,
                connect='tcp://127.0.0.1:{}'.format(port))
            self.assertEqual('CONNECTED', pr2.state)
            yield from pr2.connected
            return tr2, pr2

        tr2, pr2 = self.loop.run_until_complete(connect_rep())

        @asyncio.coroutine
        def communicate():
            tr1.write([b'request'])
            request = yield from pr2.received.get()
            self.assertEqual((b'request',), request)
            tr2.write([b'answer'])
            answer = yield from pr1.received.get()
            self.assertEqual((b'answer',), answer)

        self.loop.run_until_complete(communicate())

        @asyncio.coroutine
        def closing():
            tr1.close()
            tr2.close()

            yield from pr1.closed
            self.assertEqual('CLOSED', pr1.state)
            yield from pr2.closed
            self.assertEqual('CLOSED', pr2.state)

        self.loop.run_until_complete(closing())

    def test_pub_sub(self):
        port = support.find_unused_port()

        @asyncio.coroutine
        def connect_pub():
            tr1, pr1 = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.PUB,
                bind='tcp://127.0.0.1:{}'.format(port))
            self.assertEqual('CONNECTED', pr1.state)
            yield from pr1.connected
            return tr1, pr1

        tr1, pr1 = self.loop.run_until_complete(connect_pub())

        @asyncio.coroutine
        def connect_sub():
            tr2, pr2 = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.SUB,
                connect='tcp://127.0.0.1:{}'.format(port))
            self.assertEqual('CONNECTED', pr2.state)
            yield from pr2.connected
            tr2.setsockopt(zmq.SUBSCRIBE, b'node_id')
            return tr2, pr2

        tr2, pr2 = self.loop.run_until_complete(connect_sub())

        @asyncio.coroutine
        def communicate():
            tr1.write([b'node_id', b'publish'])
            request = yield from pr2.received.get()
            self.assertEqual((b'node_id', b'publish'), request)

        # Sorry, sleep is required to get rid of sporadic hungs
        # without that 0MQ not always establishes tcp connection
        # and waiting for message from sub socket hungs.
        time.sleep(0.1)
        self.loop.run_until_complete(communicate())

        @asyncio.coroutine
        def closing():
            tr1.close()
            tr2.close()

            yield from pr1.closed
            self.assertEqual('CLOSED', pr1.state)
            yield from pr2.closed
            self.assertEqual('CLOSED', pr2.state)

        self.loop.run_until_complete(closing())

    def test_getsockopt(self):
        port = support.find_unused_port()

        @asyncio.coroutine
        def coro():
            tr, pr = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.DEALER,
                bind='tcp://127.0.0.1:{}'.format(port))
            yield from pr.connected
            self.assertEqual(zmq.DEALER, tr.getsockopt(zmq.TYPE))
            return tr, pr

        self.loop.run_until_complete(coro())

    def test_dealer_router(self):
        port = support.find_unused_port()

        @asyncio.coroutine
        def connect_req():
            tr1, pr1 = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.DEALER,
                bind='tcp://127.0.0.1:{}'.format(port))
            self.assertEqual('CONNECTED', pr1.state)
            yield from pr1.connected
            return tr1, pr1

        tr1, pr1 = self.loop.run_until_complete(connect_req())

        @asyncio.coroutine
        def connect_rep():
            tr2, pr2 = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.ROUTER,
                connect='tcp://127.0.0.1:{}'.format(port))
            self.assertEqual('CONNECTED', pr2.state)
            yield from pr2.connected
            return tr2, pr2

        tr2, pr2 = self.loop.run_until_complete(connect_rep())

        @asyncio.coroutine
        def communicate():
            tr1.write([b'request'])
            request = yield from pr2.received.get()
            self.assertEqual((mock.ANY, b'request',), request)
            tr2.write([request[0], b'answer'])
            answer = yield from pr1.received.get()
            self.assertEqual((b'answer',), answer)

        self.loop.run_until_complete(communicate())

        @asyncio.coroutine
        def closing():
            tr1.close()
            tr2.close()

            yield from pr1.closed
            self.assertEqual('CLOSED', pr1.state)
            yield from pr2.closed
            self.assertEqual('CLOSED', pr2.state)

        self.loop.run_until_complete(closing())

    def test_binds(self):
        port1 = support.find_unused_port()
        port2 = support.find_unused_port()
        addr1 = 'tcp://127.0.0.1:{}'.format(port1)
        addr2 = 'tcp://127.0.0.1:{}'.format(port2)

        @asyncio.coroutine
        def connect():
            tr, pr = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.REQ,
                bind=[addr1, addr2])
            yield from pr.connected
            return tr, pr

        tr, pr = self.loop.run_until_complete(connect())
        self.assertEqual({addr1, addr2}, tr.listeners())

        addr3 = tr.bind('tcp://*:*')
        self.assertEqual({addr1, addr2, addr3}, tr.listeners())
        tr.unbind(addr2)
        self.assertEqual({addr1, addr3}, tr.listeners())
        tr.close()

    def test_connects(self):
        port1 = support.find_unused_port()
        port2 = support.find_unused_port()
        port3 = support.find_unused_port()
        addr1 = 'tcp://127.0.0.1:{}'.format(port1)
        addr2 = 'tcp://127.0.0.1:{}'.format(port2)
        addr3 = 'tcp://127.0.0.1:{}'.format(port3)

        @asyncio.coroutine
        def connect():
            tr, pr = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.REQ,
                connect=[addr1, addr2])
            yield from pr.connected
            return tr, pr

        tr, pr = self.loop.run_until_complete(connect())
        self.assertEqual({addr1, addr2}, tr.connections())
        tr.connect(addr3)
        self.assertEqual({addr1, addr3, addr2}, tr.connections())
        tr.disconnect(addr1)
        self.assertEqual({addr2, addr3}, tr.connections())
        tr.close()
