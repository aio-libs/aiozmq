import unittest
import asyncio
import aiozmq
import errno
import os
import time
import zmq
from unittest import mock

from aiozmq._test_util import find_unused_port


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
        port = find_unused_port()

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
        port = find_unused_port()

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

        # Sorry, sleep is required to get rid of sporadic hangs
        # without that 0MQ not always establishes tcp connection
        # and waiting for message from sub socket hangs.
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
        port = find_unused_port()

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
        port = find_unused_port()

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
        port1 = find_unused_port()
        port2 = find_unused_port()
        addr1 = 'tcp://127.0.0.1:{}'.format(port1)
        addr2 = 'tcp://127.0.0.1:{}'.format(port2)

        @asyncio.coroutine
        def connect():
            tr, pr = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.REQ,
                bind=[addr1, addr2])
            yield from pr.connected

            self.assertEqual({addr1, addr2}, tr.bindings())

            addr3 = yield from tr.bind('tcp://*:*')
            self.assertEqual({addr1, addr2, addr3}, tr.bindings())
            yield from tr.unbind(addr2)
            self.assertEqual({addr1, addr3}, tr.bindings())
            self.assertIn(addr1, tr.bindings())
            self.assertRegex(repr(tr.bindings()),
                             r'{tcp://0.0.0.0:.\d+, tcp://127.0.0.1:\d+}')
            tr.close()

        self.loop.run_until_complete(connect())

    def test_connects(self):
        port1 = find_unused_port()
        port2 = find_unused_port()
        port3 = find_unused_port()
        addr1 = 'tcp://127.0.0.1:{}'.format(port1)
        addr2 = 'tcp://127.0.0.1:{}'.format(port2)
        addr3 = 'tcp://127.0.0.1:{}'.format(port3)

        @asyncio.coroutine
        def go():
            tr, pr = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.REQ,
                connect=[addr1, addr2])
            yield from pr.connected

            self.assertEqual({addr1, addr2}, tr.connections())
            yield from tr.connect(addr3)
            self.assertEqual({addr1, addr3, addr2}, tr.connections())
            yield from tr.disconnect(addr1)
            self.assertEqual({addr2, addr3}, tr.connections())
            tr.close()

        self.loop.run_until_complete(go())

    def test_zmq_socket(self):
        zmq_sock = self.loop._zmq_context.socket(zmq.PUB)

        @asyncio.coroutine
        def connect():
            tr, pr = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.PUB,
                zmq_sock=zmq_sock)
            yield from pr.connected
            return tr, pr

        tr, pr = self.loop.run_until_complete(connect())
        self.assertIs(zmq_sock, tr._zmq_sock)
        self.assertFalse(zmq_sock.closed)
        tr.close()

    def test_zmq_socket_invalid_type(self):
        zmq_sock = self.loop._zmq_context.socket(zmq.PUB)

        @asyncio.coroutine
        def connect():
            tr, pr = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.SUB,
                zmq_sock=zmq_sock)
            yield from pr.connected
            return tr, pr

        with self.assertRaises(ValueError):
            self.loop.run_until_complete(connect())
        self.assertFalse(zmq_sock.closed)

    def test_create_zmq_connection_ZMQError(self):
        zmq_sock = self.loop._zmq_context.socket(zmq.PUB)
        zmq_sock.close()

        @asyncio.coroutine
        def connect():
            tr, pr = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.SUB,
                zmq_sock=zmq_sock)
            yield from pr.connected
            return tr, pr

        with self.assertRaises(OSError) as ctx:
            self.loop.run_until_complete(connect())
        self.assertEqual(errno.ENOTSUP, ctx.exception.errno)

    def test_create_zmq_connection_invalid_bind(self):

        @asyncio.coroutine
        def connect():
            tr, pr = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.SUB,
                bind=2)

        with self.assertRaises(ValueError):
            self.loop.run_until_complete(connect())

    def test_create_zmq_connection_invalid_connect(self):

        @asyncio.coroutine
        def connect():
            tr, pr = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.SUB,
                connect=2)

        with self.assertRaises(ValueError):
            self.loop.run_until_complete(connect())

    def test_create_zmq_connection_closes_socket_on_bad_bind(self):

        @asyncio.coroutine
        def connect():
            tr, pr = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.SUB,
                bind='badaddr')
            yield from pr.connected
            return tr, pr

        with self.assertRaises(OSError):
            self.loop.run_until_complete(connect())

    def test_create_zmq_connection_closes_socket_on_bad_connect(self):

        @asyncio.coroutine
        def connect():
            tr, pr = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.SUB,
                connect='badaddr')
            yield from pr.connected
            return tr, pr

        with self.assertRaises(OSError):
            self.loop.run_until_complete(connect())

    def test_create_zmq_connection_dns_in_connect(self):

        @asyncio.coroutine
        def connect():
            tr, pr = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.SUB,
                connect='tcp://example.com:5555')
            yield from pr.connected
            return tr, pr

        with self.assertRaises(ValueError):
            self.loop.run_until_complete(connect())

    def test_getsockopt_badopt(self):
        port = find_unused_port()

        @asyncio.coroutine
        def connect():
            tr, pr = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.SUB,
                connect='tcp://127.0.0.1:{}'.format(port))
            yield from pr.connected
            return tr, pr

        tr, pr = self.loop.run_until_complete(connect())

        with self.assertRaises(OSError) as ctx:
            tr.getsockopt(1111)  # invalid option
        self.assertEqual(errno.EINVAL, ctx.exception.errno)

    def test_setsockopt_badopt(self):
        port = find_unused_port()

        @asyncio.coroutine
        def connect():
            tr, pr = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.SUB,
                connect='tcp://127.0.0.1:{}'.format(port))
            yield from pr.connected
            return tr, pr

        tr, pr = self.loop.run_until_complete(connect())

        with self.assertRaises(OSError) as ctx:
            tr.setsockopt(1111, 1)  # invalid option
        self.assertEqual(errno.EINVAL, ctx.exception.errno)

    def test_unbind_from_nonbinded_addr(self):
        port = find_unused_port()
        addr = 'tcp://127.0.0.1:{}'.format(port)

        @asyncio.coroutine
        def connect():
            tr, pr = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.SUB,
                bind=addr)
            yield from pr.connected

            self.assertEqual({addr}, tr.bindings())
            with self.assertRaises(OSError) as ctx:
                yield from tr.unbind('ipc:///some-addr')  # non-bound addr

            # TODO: check travis build and remove skip when test passed.
            if (ctx.exception.errno == errno.EAGAIN and
                    os.environ.get('TRAVIS')):
                raise unittest.SkipTest("Travis has a bug, it returns "
                                        "EAGAIN for unknown endpoint")
            self.assertEqual(errno.ENOENT, ctx.exception.errno)
            self.assertEqual({addr}, tr.bindings())

        self.loop.run_until_complete(connect())

    def test_disconnect_from_nonbinded_addr(self):
        port = find_unused_port()
        addr = 'tcp://127.0.0.1:{}'.format(port)

        @asyncio.coroutine
        def go():
            tr, pr = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.SUB,
                connect=addr)
            yield from pr.connected

            self.assertEqual({addr}, tr.connections())
            with self.assertRaises(OSError) as ctx:
                yield from tr.disconnect('ipc:///some-addr')  # non-bound addr

            # TODO: check travis build and remove skip when test passed.
            if (ctx.exception.errno == errno.EAGAIN and
                    os.environ.get('TRAVIS')):
                raise unittest.SkipTest("Travis has a bug, it returns "
                                        "EAGAIN for unknown endpoint")
            self.assertEqual(errno.ENOENT, ctx.exception.errno)
            self.assertEqual({addr}, tr.connections())

        self.loop.run_until_complete(go())

    def test_subscriptions_of_invalid_socket(self):

        @asyncio.coroutine
        def connect():
            tr, pr = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.PUSH,
                bind='tcp://*:*')
            yield from pr.connected
            return tr, pr

        tr, pr = self.loop.run_until_complete(connect())
        self.assertRaises(NotImplementedError, tr.subscribe, b'a')
        self.assertRaises(NotImplementedError, tr.unsubscribe, b'a')
        self.assertRaises(NotImplementedError, tr.subscriptions)

    def test_double_subscribe(self):

        @asyncio.coroutine
        def connect():
            tr, pr = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.SUB,
                bind='tcp://*:*')
            yield from pr.connected
            return tr, pr

        tr, pr = self.loop.run_until_complete(connect())
        tr.subscribe(b'val')
        self.assertEqual({b'val'}, tr.subscriptions())

        tr.subscribe(b'val')
        self.assertEqual({b'val'}, tr.subscriptions())

    def test_double_unsubscribe(self):

        @asyncio.coroutine
        def connect():
            tr, pr = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.SUB,
                bind='tcp://*:*')
            yield from pr.connected
            return tr, pr

        tr, pr = self.loop.run_until_complete(connect())
        tr.subscribe(b'val')
        self.assertEqual({b'val'}, tr.subscriptions())

        tr.unsubscribe(b'val')
        self.assertFalse(tr.subscriptions())
        tr.unsubscribe(b'val')
        self.assertFalse(tr.subscriptions())

    def test_unsubscribe_unknown_filter(self):

        @asyncio.coroutine
        def connect():
            tr, pr = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.SUB,
                bind='tcp://*:*')
            yield from pr.connected
            return tr, pr

        tr, pr = self.loop.run_until_complete(connect())

        tr.unsubscribe(b'val')
        self.assertFalse(tr.subscriptions())
        tr.unsubscribe(b'val')
        self.assertFalse(tr.subscriptions())

    def test_endpoint_is_not_a_str(self):

        @asyncio.coroutine
        def go():
            tr, pr = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.PUSH,
                bind='tcp://*:*')
            yield from pr.connected

            with self.assertRaises(TypeError):
                yield from tr.bind(123)

            with self.assertRaises(TypeError):
                yield from tr.unbind(123)

            with self.assertRaises(TypeError):
                yield from tr.connect(123)

            with self.assertRaises(TypeError):
                yield from tr.disconnect(123)

        self.loop.run_until_complete(go())
