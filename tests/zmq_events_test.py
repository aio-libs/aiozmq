import unittest
import asyncio
import aiozmq
import time
import zmq

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

    def msg_received(self, data, *multipart):
        assert self.state == 'CONNECTED', self.state
        self.received.put_nowait((data,) + multipart)


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
            tr1.write(b'request')
            request = yield from pr2.received.get()
            self.assertEqual((b'request',), request)
            tr2.write(b'answer')
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
            tr1.write(b'node_id', b'publish')
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

    def xtest_pending_writer(self):
        port = support.find_unused_port()

        @asyncio.coroutine
        def connect_pub():
            tr1, pr1 = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.PUB,
                bind='tcp://127.0.0.1:{}'.format(port))
            yield from pr1.connected
            return tr1, pr1

        tr1, pr1 = self.loop.run_until_complete(connect_pub())

        @asyncio.coroutine
        def connect_sub():
            tr2, pr2 = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.SUB,
                connect='tcp://127.0.0.1:{}'.format(port))
            yield from pr2.connected
            tr2.setsockopt(zmq.SUBSCRIBE, b'node')
            return tr2, pr2

        tr2, pr2 = self.loop.run_until_complete(connect_sub())

        @asyncio.coroutine
        def communicate():
            tr1.setsockopt(zmq.SNDBUF, 5)
            import pdb;pdb.set_trace()
            tr1.write(b'node', b'1'*100)
            tr1.write(b'node', b'2'*100)
            tr1.setsockopt(zmq.SNDBUF, 0)
            tr1.write(b'node', b'3'*100)
            r1 = yield from pr2.received.get()
            self.assertEqual((b'node', b'1'*100,), r1)
            r2 = yield from pr2.received.get()
            self.assertEqual((b'node', b'2'*100,), r2)
            r3 = yield from pr2.received.get()
            self.assertEqual((b'node', b'3'*100,), r3)

        self.loop.run_until_complete(communicate())

        tr1.close()
        tr2.close()
