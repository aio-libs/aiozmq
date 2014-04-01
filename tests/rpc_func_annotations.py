import unittest
import asyncio

import aiozmq
import aiozmq.rpc


def my_checker(val):
    if isinstance(val, int) or val is None:
        return val
    else:
        raise ValueError('bad value')


class MyHandler(aiozmq.rpc.AttrHandler):

    @aiozmq.rpc.method
    @asyncio.coroutine
    def no_params(self, arg):
        return arg + 1
        yield

    @aiozmq.rpc.method
    @asyncio.coroutine
    def single_param(self, arg: int):
        return arg + 1
        yield

    @aiozmq.rpc.method
    @asyncio.coroutine
    def custom_annotation(self, arg: my_checker):
        return arg
        yield

    @aiozmq.rpc.method
    @asyncio.coroutine
    def ret_annotation(self, arg: int=1) -> float:
        return float(arg)
        yield

    @aiozmq.rpc.method
    @asyncio.coroutine
    def bad_return(self, arg) -> int:
        return arg
        yield

    @aiozmq.rpc.method
    def has_default(self, arg: int=None):
        return arg


class FuncAnnotationsTests(unittest.TestCase):

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

    def close(self, service):
        service.close()
        self.loop.run_until_complete(service.wait_closed())

    def make_rpc_pair(self):

        @asyncio.coroutine
        def create():
            server = yield from aiozmq.rpc.serve_rpc(
                MyHandler(),
                loop=self.loop)

            addr = yield from server.transport.bind('tcp://*:*')

            client = yield from aiozmq.rpc.connect_rpc(
                connect=addr, loop=self.loop)
            return client, server

        self.client, self.server = self.loop.run_until_complete(create())

        return self.client, self.server

    def test_valid_annotations(self):

        msg = "Expected 'bad_arg' annotation to be callable"
        with self.assertRaisesRegexp(ValueError, msg):
            @aiozmq.rpc.method
            def test(good_arg: int, bad_arg: 0):
                pass

        msg = "Expected return annotation to be callable"
        with self.assertRaisesRegexp(ValueError, msg):
            @aiozmq.rpc.method
            def test2() -> 'bad annotation':
                pass

    def test_no_params(self):
        client, server = self.make_rpc_pair()

        @asyncio.coroutine
        def communicate():
            ret = yield from client.call.no_params(1)
            self.assertEqual(ret, 2)

        self.loop.run_until_complete(communicate())

    def test_single_param(self):
        client, server = self.make_rpc_pair()

        @asyncio.coroutine
        def communicate():
            ret = yield from client.call.single_param(1)
            self.assertEqual(ret, 2)
            ret = yield from client.call.single_param('1')
            self.assertEqual(ret, 2)
            ret = yield from client.call.single_param(1.0)
            self.assertEqual(ret, 2)

            msg = "Invalid value for argument 'arg'"
            with self.assertRaisesRegex(aiozmq.rpc.ParametersError, msg):
                yield from client.call.single_param('1.0')
            with self.assertRaisesRegex(aiozmq.rpc.ParametersError, msg):
                yield from client.call.single_param('bad value')
            with self.assertRaisesRegex(aiozmq.rpc.ParametersError, msg):
                yield from client.call.single_param({})
            with self.assertRaisesRegex(aiozmq.rpc.ParametersError, msg):
                yield from client.call.single_param(None)

            msg = "TypeError.*'arg' parameter lacking default value"
            with self.assertRaisesRegex(aiozmq.rpc.ParametersError, msg):
                yield from client.call.single_param()
            with self.assertRaisesRegex(aiozmq.rpc.ParametersError, msg):
                yield from client.call.single_param(bad='value')

            msg = "TypeError.*too many keyword arguments"
            with self.assertRaisesRegex(aiozmq.rpc.ParametersError, msg):
                yield from client.call.single_param(1, bad='value')

        self.loop.run_until_complete(communicate())

    def test_custom_annotation(self):
        client, server = self.make_rpc_pair()

        @asyncio.coroutine
        def communicate():
            ret = yield from client.call.custom_annotation(1)
            self.assertEqual(ret, 1)
            ret = yield from client.call.custom_annotation(None)
            self.assertIsNone(ret)

            msg = "Invalid value for argument 'arg': ValueError.*bad value.*"
            with self.assertRaisesRegex(aiozmq.rpc.ParametersError, msg):
                yield from client.call.custom_annotation(1.0)

        self.loop.run_until_complete(communicate())

    def test_ret_annotation(self):
        client, server = self.make_rpc_pair()

        @asyncio.coroutine
        def communicate():
            ret = yield from client.call.ret_annotation(1)
            self.assertEqual(ret, 1.0)
            ret = yield from client.call.ret_annotation('2')
            self.assertEqual(ret, 2.0)

        self.loop.run_until_complete(communicate())

    def test_bad_return(self):
        client, server = self.make_rpc_pair()

        @asyncio.coroutine
        def communicate():
            ret = yield from client.call.bad_return(1)
            self.assertEqual(ret, 1)
            ret = yield from client.call.bad_return(1.2)
            self.assertEqual(ret, 1)
            ret = yield from client.call.bad_return('2')
            self.assertEqual(ret, 2)

            with self.assertRaises(ValueError):
                yield from client.call.bad_return('1.0')
            with self.assertRaises(TypeError):
                yield from client.call.bad_return(None)

        self.loop.run_until_complete(communicate())

    def test_default_value_not_passed_to_annotation(self):
        client, server = self.make_rpc_pair()

        @asyncio.coroutine
        def communicate():
            ret = yield from client.call.has_default(1)
            self.assertEqual(ret, 1)

            ret = yield from client.call.has_default()
            self.assertEqual(ret, None)

            with self.assertRaises(ValueError):
                yield from client.call.has_default(None)

        self.loop.run_until_complete(communicate())
