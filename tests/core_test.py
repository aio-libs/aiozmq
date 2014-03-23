"""tests for core.py"""
import asyncio
import unittest
import unittest.mock
import zmq
import aiozmq
import aiozmq.core


class CoreTests(unittest.TestCase):

    def setUp(self):
        self.loop = aiozmq.ZmqEventLoop()
        self.ctx = aiozmq.Context(loop=self.loop)
        asyncio.set_event_loop(None)

    def tearDown(self):
        self.loop.close()

    def test_context_global_event_loop(self):
        asyncio.set_event_loop(self.loop)
        try:
            ctx = aiozmq.Context()
            self.assertIs(ctx._loop, self.loop)
        finally:
            asyncio.set_event_loop(None)

    def test_context_socket(self):
        ctx = aiozmq.Context(loop=self.loop)
        self.assertIs(ctx._loop, self.loop)

        socket = ctx.socket(zmq.PUB)
        socket.close()
        self.assertIsInstance(socket, aiozmq.core.Socket)
        self.assertIs(socket._loop, self.loop)

    @unittest.mock.patch('aiozmq.core.zmq.Socket')
    def test_recv_err(self, zmqSocket):
        err = zmq.ZMQError()
        err.errno = -1
        zmqSocket.recv.side_effect = err

        def recv(sock):
            try:
                yield from sock.recv()
            except zmq.ZMQError as e:
                return e

        sock = self.ctx.socket(zmq.PUB)
        res = self.loop.run_until_complete(recv(sock))
        self.assertEqual(res, err)
        sock.close()

    def test_send_checks(self):
        sock = self.ctx.socket(zmq.PUSH)

        self.assertRaises(AssertionError, sock.send, 'test')
        self.assertIsNone(sock.send(b''))


class CoreIntegrationalTests(unittest.TestCase):

    def setUp(self):
        self.loop = aiozmq.ZmqEventLoop()
        self.srv_ctx = aiozmq.Context(loop=self.loop)
        self.c_ctx = aiozmq.Context(loop=self.loop)
        asyncio.set_event_loop(None)

    def tearDown(self):
        self.loop.close()

    def test_recv(self):
        # server
        srv_sock = self.srv_ctx.socket(zmq.PUSH)
        srv_sock.bind('ipc:///tmp/zmqtest')
        srv_sock.send(b'test data')

        # client
        client_sock = self.c_ctx.socket(zmq.PULL)
        client_sock.connect('ipc:///tmp/zmqtest')

        @asyncio.coroutine
        def get_data(sock):
            return (yield from sock.recv())

        self.assertEqual(
            b'test data',
            self.loop.run_until_complete(get_data(client_sock)))

    def test_recv_cancelled(self):
        # client
        client_sock = self.c_ctx.socket(zmq.PULL)
        client_sock.connect('ipc:///tmp/zmqtest')

        @asyncio.coroutine
        def get_data(sock):
            return (yield from sock.recv())

        task = asyncio.Task(get_data(client_sock), loop=self.loop)
        self.loop.call_later(0.1, task.cancel)
        self.assertRaises(
            asyncio.CancelledError,
            self.loop.run_until_complete, task)

    def test_recv_noblock(self):
        client_sock = self.c_ctx.socket(zmq.PULL)
        client_sock.connect('ipc:///tmp/zmqtest')

        @asyncio.coroutine
        def get_data(sock):
            return (yield from sock.recv(zmq.NOBLOCK))

        self.assertRaises(
            zmq.ZMQError, self.loop.run_until_complete, get_data(client_sock))

    def test_recv_pyobj(self):
        # server
        srv_sock = self.srv_ctx.socket(zmq.PUSH)
        srv_sock.bind('ipc:///tmp/zmqtest')
        srv_sock.send_pyobj(('rec1', 'rec2'))

        # client
        client_sock = self.c_ctx.socket(zmq.PULL)
        client_sock.connect('ipc:///tmp/zmqtest')

        @asyncio.coroutine
        def get_data(sock):
            return (yield from sock.recv_pyobj())

        self.assertEqual(
            ('rec1', 'rec2'),
            self.loop.run_until_complete(get_data(client_sock)))
