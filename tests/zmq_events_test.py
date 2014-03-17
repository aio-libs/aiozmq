import unittest
import asyncio
import zmqtulip
import zmq

from test import support  # import from standard python test suite


class Protocol(zmqtulip.ZmqProtocol):

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
        self.received.put((data,) + multipart)


class ZmqEventLoopTests(unittest.TestCase):

    def setUp(self):
        self.loop = zmqtulip.new_event_loop()
        asyncio.set_event_loop(None)

    def tearDown(self):
        self.loop.close()

    def test_req_rep(self):
        port = support.find_unused_port()

        @asyncio.coroutine
        def connect_req():
            trq, prq = self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.REQ,
                bind='tcp://127.0.0.1:{}'.format(port))
            self.assertEqual('CONNECTED', pr.state)
            yield from pr.connected
            return trq, prq

        trq, prq = self.loop.run_until_complete(connect_req())

        @asyncio.coroutine
        def connect_rep():
            trp, prp = self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.REP,
                connect='tcp://127.0.0.1:{}'.format(port))
            self.assertEqual('CONNECTED', pr.state)
            yield from pr.connected
            return trp, prp

        trp, prp = self.loop.run_until_complete(connect_rep())

        @asyncio.coroutine
        def communicate():
            trq.write(b'request')
            request = yield from prp.received.get()
            self.assertEqual(b'request', request)
            trp.write(b'answer')
            answer = yield from prq.received.get()
            self.assertEqual(b'answer', answer)

        self.loop.run_until_complete(communicate())

        @asyncio.coroutine
        def closing():
            trq.close()
            trp.close()

            yield from prq.closed
            self.assertEqual('CLOSED', prq.state)
            yield from prp.closed
            self.assertEqual('CLOSED', prp.state)

        self.loop.run_until_complete(closing())
