import unittest
import asyncio
import aiozmq
import aiozmq.rpc
import datetime

from aiozmq._test_utils import find_unused_port


class MyException(Exception):
    pass


class MyHandler(aiozmq.rpc.AttrHandler):

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

    def make_rpc_pair(self, *, error_table=None):
        port = find_unused_port()

        @asyncio.coroutine
        def create():
            server = yield from aiozmq.rpc.serve_rpc(
                MyHandler(),
                bind='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop)
            client = yield from aiozmq.rpc.connect_rpc(
                connect='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop, error_table=error_table)
            return client, server

        self.client, self.server = self.loop.run_until_complete(create())

        return self.client, self.server

    def test_func(self):
        client, server = self.make_rpc_pair()

        @asyncio.coroutine
        def communicate():
            ret = yield from client.rpc.func(1)
            self.assertEqual(2, ret)
            client.close()
            yield from client.wait_closed()

        self.loop.run_until_complete(communicate())

    def test_exc(self):
        client, server = self.make_rpc_pair()

        @asyncio.coroutine
        def communicate():
            with self.assertRaises(RuntimeError) as exc:
                yield from client.rpc.exc(1)
            self.assertEqual(('bad arg', 1), exc.exception.args)

        self.loop.run_until_complete(communicate())

    def test_not_found(self):
        client, server = self.make_rpc_pair()

        @asyncio.coroutine
        def communicate():
            with self.assertRaises(aiozmq.rpc.NotFoundError) as exc:
                yield from client.rpc.unknown_method(1, 2, 3)
            self.assertEqual(('unknown_method',), exc.exception.args)

        self.loop.run_until_complete(communicate())

    def test_coro(self):
        client, server = self.make_rpc_pair()

        @asyncio.coroutine
        def communicate():
            ret = yield from client.rpc.coro(2)
            self.assertEqual(3, ret)

        self.loop.run_until_complete(communicate())

    def test_exc_coro(self):
        client, server = self.make_rpc_pair()

        @asyncio.coroutine
        def communicate():
            with self.assertRaises(RuntimeError) as exc:
                yield from client.rpc.exc_coro(1)
            self.assertEqual(('bad arg 2', 1), exc.exception.args)

        self.loop.run_until_complete(communicate())

    def test_datetime_translators(self):
        client, server = self.make_rpc_pair()

        @asyncio.coroutine
        def communicate():
            ret = yield from client.rpc.add(datetime.date(2014, 3, 21),
                                            datetime.timedelta(days=2))
            self.assertEqual(datetime.date(2014, 3, 23), ret)

        self.loop.run_until_complete(communicate())

    def test_not_found_empty_name(self):
        client, server = self.make_rpc_pair()

        @asyncio.coroutine
        def communicate():
            with self.assertRaises(ValueError) as exc:
                yield from client.rpc(1, 2, 3)
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
                yield from client.rpc.generic_exception()
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
                yield from client.rpc.generic_exception()
            self.assertEqual(('additional', 'data'), exc.exception.args)

        self.loop.run_until_complete(communicate())

    def test_default_event_loop(self):
        port = find_unused_port()

        asyncio.set_event_loop_policy(aiozmq.ZmqEventLoopPolicy())

        @asyncio.coroutine
        def create():
            server = yield from aiozmq.rpc.serve_rpc(
                MyHandler(),
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
            ret = yield from self.client.rpc.func(1)
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
