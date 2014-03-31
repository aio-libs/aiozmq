import unittest
import asyncio
import aiozmq
import aiozmq.rpc
import datetime
import time
from unittest import mock
import zmq
import msgpack
import struct

from aiozmq._test_utils import find_unused_port


class MyException(Exception):
    pass


class MyHandler(aiozmq.rpc.AttrHandler):

    def __init__(self, loop):
        self.loop = loop

    @aiozmq.rpc.method
    def func(self, arg):
        return arg + 1

    @aiozmq.rpc.method
    @asyncio.coroutine
    def coro(self, arg):
        return arg + 1
        yield

    @aiozmq.rpc.method
    def exc(self, arg):
        raise RuntimeError("bad arg", arg)

    @aiozmq.rpc.method
    @asyncio.coroutine
    def exc_coro(self, arg):
        raise RuntimeError("bad arg 2", arg)
        yield

    @aiozmq.rpc.method
    def add(self, a1, a2):
        return a1 + a2

    @aiozmq.rpc.method
    def generic_exception(self):
        raise MyException('additional', 'data')

    @aiozmq.rpc.method
    @asyncio.coroutine
    def slow_call(self):
        yield from asyncio.sleep(0.2, loop=self.loop)


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


class RpcTests(unittest.TestCase):

    def setUp(self):
        self.loop = aiozmq.ZmqEventLoop()
        asyncio.set_event_loop(None)
        self.client = self.server = None

    def tearDown(self):
        if self.client is not None:
            self.close(self.client)
        if self.server is not None:
            self.close(self.server)
        self.loop.close()

    def close(self, server):
        server.close()
        self.loop.run_until_complete(server.wait_closed())

    def make_rpc_pair(self, *, error_table=None, timeout=None):
        port = find_unused_port()

        @asyncio.coroutine
        def create():
            server = yield from aiozmq.rpc.serve_rpc(
                MyHandler(self.loop),
                bind='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop)
            client = yield from aiozmq.rpc.connect_rpc(
                connect='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop, error_table=error_table, timeout=timeout)
            return client, server

        self.client, self.server = self.loop.run_until_complete(create())

        return self.client, self.server

    def test_func(self):
        client, server = self.make_rpc_pair()

        @asyncio.coroutine
        def communicate():
            ret = yield from client.call.func(1)
            self.assertEqual(2, ret)
            client.close()
            yield from client.wait_closed()

        self.loop.run_until_complete(communicate())

    def test_exc(self):
        client, server = self.make_rpc_pair()

        @asyncio.coroutine
        def communicate():
            with self.assertRaises(RuntimeError) as exc:
                yield from client.call.exc(1)
            self.assertEqual(('bad arg', 1), exc.exception.args)

        self.loop.run_until_complete(communicate())

    def test_not_found(self):
        client, server = self.make_rpc_pair()

        @asyncio.coroutine
        def communicate():
            with self.assertRaises(aiozmq.rpc.NotFoundError) as exc:
                yield from client.call.unknown_method(1, 2, 3)
            self.assertEqual(('unknown_method',), exc.exception.args)

        self.loop.run_until_complete(communicate())

    def test_coro(self):
        client, server = self.make_rpc_pair()

        @asyncio.coroutine
        def communicate():
            ret = yield from client.call.coro(2)
            self.assertEqual(3, ret)

        self.loop.run_until_complete(communicate())

    def test_exc_coro(self):
        client, server = self.make_rpc_pair()

        @asyncio.coroutine
        def communicate():
            with self.assertRaises(RuntimeError) as exc:
                yield from client.call.exc_coro(1)
            self.assertEqual(('bad arg 2', 1), exc.exception.args)

        self.loop.run_until_complete(communicate())

    def test_datetime_translators(self):
        client, server = self.make_rpc_pair()

        @asyncio.coroutine
        def communicate():
            ret = yield from client.call.add(datetime.date(2014, 3, 21),
                                             datetime.timedelta(days=2))
            self.assertEqual(datetime.date(2014, 3, 23), ret)

        self.loop.run_until_complete(communicate())

    def test_not_found_empty_name(self):
        client, server = self.make_rpc_pair()

        @asyncio.coroutine
        def communicate():
            with self.assertRaises(ValueError) as exc:
                yield from client.call(1, 2, 3)
            self.assertEqual(('RPC method name is empty',), exc.exception.args)

        self.loop.run_until_complete(communicate())

    def test_not_found_empty_name_on_server(self):
        client, server = self.make_rpc_pair()

        @asyncio.coroutine
        def communicate():
            with self.assertRaises(aiozmq.rpc.NotFoundError) as exc:
                yield from client._proto.call('', (), {})
            self.assertEqual(('',), exc.exception.args)

        self.loop.run_until_complete(communicate())

    def test_generic_exception(self):
        client, server = self.make_rpc_pair()

        @asyncio.coroutine
        def communicate():
            with self.assertRaises(aiozmq.rpc.GenericError) as exc:
                yield from client.call.generic_exception()
            self.assertEqual(('rpc_test.MyException',
                             ('additional', 'data')),
                             exc.exception.args)

        self.loop.run_until_complete(communicate())

    def test_exception_translator(self):
        client, server = self.make_rpc_pair(
            error_table={__name__+'.MyException': MyException})

        @asyncio.coroutine
        def communicate():
            with self.assertRaises(MyException) as exc:
                yield from client.call.generic_exception()
            self.assertEqual(('additional', 'data'), exc.exception.args)

        self.loop.run_until_complete(communicate())

    def test_default_event_loop(self):
        port = find_unused_port()

        asyncio.set_event_loop_policy(aiozmq.ZmqEventLoopPolicy())
        self.addCleanup(asyncio.set_event_loop_policy, None)
        self.addCleanup(asyncio.set_event_loop, None)

        @asyncio.coroutine
        def create():
            server = yield from aiozmq.rpc.serve_rpc(
                MyHandler(self.loop),
                bind='tcp://127.0.0.1:{}'.format(port),
                loop=None)
            client = yield from aiozmq.rpc.connect_rpc(
                connect='tcp://127.0.0.1:{}'.format(port),
                loop=None)
            return client, server

        self.loop = loop = asyncio.get_event_loop()
        self.client, self.server = loop.run_until_complete(create())

        @asyncio.coroutine
        def communicate():
            ret = yield from self.client.call.func(1)
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

    @mock.patch("aiozmq.rpc.rpc.logger")
    def test_client_timeout(self, m_log):
        client, server = self.make_rpc_pair()

        @asyncio.coroutine
        def communicate():
            with self.assertRaises(asyncio.TimeoutError):
                t0 = time.monotonic()
                with client.with_timeout(0.1) as timedout:
                    yield from timedout.call.slow_call()
                t1 = time.monotonic()
                self.assertTrue(0.08 <= t1-t0 <= 0.12, t1-t0)

            t0 = time.monotonic()
            with self.assertRaises(asyncio.TimeoutError):
                yield from client.with_timeout(0.1).call.slow_call()
            t1 = time.monotonic()
            self.assertTrue(0.08 <= t1-t0 <= 0.12, t1-t0)

            yield from asyncio.sleep(0.12, loop=self.loop)
            m_log.info.assert_called_with(
                'The future for %d has been cancelled, '
                'skip the received result.', mock.ANY)

        self.loop.run_until_complete(communicate())

    def test_client_override_global_timeout(self):
        client, server = self.make_rpc_pair(timeout=10)

        @asyncio.coroutine
        def communicate():
            with self.assertRaises(asyncio.TimeoutError):
                t0 = time.monotonic()
                with client.with_timeout(0.1) as timedout:
                    yield from timedout.call.slow_call()
                t1 = time.monotonic()
                self.assertTrue(0.08 <= t1-t0 <= 0.12, t1-t0)

            t0 = time.monotonic()
            with self.assertRaises(asyncio.TimeoutError):
                yield from client.with_timeout(0.1).call.slow_call()
            t1 = time.monotonic()
            self.assertTrue(0.08 <= t1-t0 <= 0.12, t1-t0)

        self.loop.run_until_complete(communicate())

    def test_type_of_handler(self):

        @asyncio.coroutine
        def go():
            with self.assertRaises(TypeError):
                yield from aiozmq.rpc.serve_rpc(
                    "Bad Handler",
                    bind='tcp://*:*',
                    loop=self.loop)

        self.loop.run_until_complete(go())

    @mock.patch("aiozmq.rpc.rpc.logger")
    def test_unknown_format_at_server(self, m_log):
        port = find_unused_port()

        @asyncio.coroutine
        def go():
            server = yield from aiozmq.rpc.serve_rpc(
                MyHandler(self.loop),
                bind='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop)
            tr, pr = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop), zmq.DEALER,
                connect='tcp://127.0.0.1:{}'.format(port))

            yield from asyncio.sleep(0.001, loop=self.loop)

            tr.write([b'invalid', b'structure'])

            yield from asyncio.sleep(0.001, loop=self.loop)

            m_log.critical.assert_called_with(
                'Cannot unpack %r',
                (mock.ANY, b'invalid', b'structure'),
                exc_info=mock.ANY)
            self.assertTrue(pr.received.empty())
            server.close()

        self.loop.run_until_complete(go())

    @mock.patch("aiozmq.rpc.rpc.logger")
    def test_malformed_args(self, m_log):
        port = find_unused_port()

        @asyncio.coroutine
        def go():
            server = yield from aiozmq.rpc.serve_rpc(
                MyHandler(self.loop),
                bind='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop)
            tr, pr = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop), zmq.DEALER,
                connect='tcp://127.0.0.1:{}'.format(port))

            tr.write([struct.pack('=HHLd', 1, 2, 3, 4),
                      b'bad args', b'bad_kwargs'])

            yield from asyncio.sleep(0.001, loop=self.loop)

            m_log.critical.assert_called_with(
                'Cannot unpack %r',
                mock.ANY,
                exc_info=mock.ANY)
            self.assertTrue(pr.received.empty())
            server.close()

        self.loop.run_until_complete(go())

    @mock.patch("aiozmq.rpc.rpc.logger")
    def test_malformed_kwargs(self, m_log):
        port = find_unused_port()

        @asyncio.coroutine
        def go():
            server = yield from aiozmq.rpc.serve_rpc(
                MyHandler(self.loop),
                bind='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop)
            tr, pr = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop), zmq.DEALER,
                connect='tcp://127.0.0.1:{}'.format(port))

            tr.write([struct.pack('=HHLd', 1, 2, 3, 4),
                      msgpack.packb((1, 2)), b'bad_kwargs'])

            yield from asyncio.sleep(0.001, loop=self.loop)

            m_log.critical.assert_called_with(
                'Cannot unpack %r',
                mock.ANY,
                exc_info=mock.ANY)
            self.assertTrue(pr.received.empty())
            server.close()

        self.loop.run_until_complete(go())

    @mock.patch("aiozmq.rpc.rpc.logger")
    def test_unknown_format_at_client(self, m_log):
        port = find_unused_port()

        @asyncio.coroutine
        def go():
            tr, pr = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop), zmq.DEALER,
                bind='tcp://127.0.0.1:{}'.format(port))

            client = yield from aiozmq.rpc.connect_rpc(
                connect='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop)

            tr.write([b'invalid', b'structure'])

            yield from asyncio.sleep(0.001, loop=self.loop)

            m_log.critical.assert_called_with(
                'Cannot unpack %r',
                mock.ANY,
                exc_info=mock.ANY)
            client.close()

        self.loop.run_until_complete(go())

    @mock.patch("aiozmq.rpc.rpc.logger")
    def test_malformed_anser_at_client(self, m_log):
        port = find_unused_port()

        @asyncio.coroutine
        def go():
            tr, pr = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop), zmq.DEALER,
                bind='tcp://127.0.0.1:{}'.format(port))

            client = yield from aiozmq.rpc.connect_rpc(
                connect='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop)

            tr.write([struct.pack('=HHLd?', 1, 2, 3, 4, True),
                      b'bad_answer'])

            yield from asyncio.sleep(0.001, loop=self.loop)

            m_log.critical.assert_called_with(
                'Cannot unpack %r',
                mock.ANY,
                exc_info=mock.ANY)
            client.close()

        self.loop.run_until_complete(go())

    @mock.patch("aiozmq.rpc.rpc.logger")
    def test_unknown_req_id_at_client(self, m_log):
        port = find_unused_port()

        @asyncio.coroutine
        def go():
            tr, pr = yield from self.loop.create_zmq_connection(
                lambda: Protocol(self.loop), zmq.DEALER,
                bind='tcp://127.0.0.1:{}'.format(port))

            client = yield from aiozmq.rpc.connect_rpc(
                connect='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop)

            tr.write([struct.pack('=HHLd?', 1, 2, 34435, 4, True),
                      msgpack.packb((1, 2))])

            yield from asyncio.sleep(0.001, loop=self.loop)

            m_log.critical.assert_called_with(
                'Unknown answer id: %d (%d %d %f %d) -> %s',
                34435, 1, 2, 4.0, True, (1, 2))
            client.close()

        self.loop.run_until_complete(go())

    def test_overflow_client_counter(self):
        client, server = self.make_rpc_pair()

        @asyncio.coroutine
        def communicate():
            client._proto.counter = 0xffffffff
            ret = yield from client.call.func(1)
            self.assertEqual(2, ret)
            client.close()
            yield from client.wait_closed()

        self.loop.run_until_complete(communicate())


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
        self.assertNotIsInstance('string', aiozmq.rpc.AbstractHandler)
        self.assertNotIsInstance(b'bytes', aiozmq.rpc.AbstractHandler)
