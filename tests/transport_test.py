import unittest

import asyncio
import collections
import zmq
import aiozmq
import errno
import selectors
import weakref

from collections import deque

from aiozmq.core import _ZmqTransportImpl, _ZmqLooplessTransportImpl
from unittest import mock

from aiozmq._test_util import check_errno


async def dummy():
    pass


# make_test_protocol, TestSelector, and TestLoop were taken from
# test.test_asyncio.utils in CPython.
# https://github.com/python/cpython/blob/9602643120a509858d0bee4215d7f150e6125468/Lib/test/test_asyncio/utils.py


def make_test_protocol(base):
    dct = {}
    for name in dir(base):
        if name.startswith("__") and name.endswith("__"):
            # skip magic names
            continue
        dct[name] = mock.Mock(return_value=None)
    return type("TestProtocol", (base,) + base.__bases__, dct)()


class TestSelector(selectors.BaseSelector):
    def __init__(self):
        self.keys = {}

    def register(self, fileobj, events, data=None):
        key = selectors.SelectorKey(fileobj, 0, events, data)
        self.keys[fileobj] = key
        return key

    def unregister(self, fileobj):
        return self.keys.pop(fileobj)

    def select(self, timeout):
        return []

    def get_map(self):
        return self.keys


class TestLoop(asyncio.base_events.BaseEventLoop):
    def __init__(self):
        super().__init__()

        self._selector = TestSelector()

        self.readers = {}
        self.writers = {}
        self.reset_counters()

        self._transports = weakref.WeakValueDictionary()

    def _add_reader(self, fd, callback, *args):
        self.readers[fd] = asyncio.events.Handle(callback, args, self)

    def _remove_reader(self, fd):
        self.remove_reader_count[fd] += 1
        if fd in self.readers:
            del self.readers[fd]
            return True
        else:
            return False

    def assert_reader(self, fd, callback, *args):
        if fd not in self.readers:
            raise AssertionError("fd {fd} is not registered".format(fd=fd))
        handle = self.readers[fd]
        if handle._callback != callback:
            raise AssertionError(
                "unexpected callback: {handle._callback} != {callback}".format(
                    handle=handle, callback=callback
                )
            )
        if handle._args != args:
            raise AssertionError(
                "unexpected callback args: {handle._args} != {args}".format(
                    handle=handle, args=args
                )
            )

    def assert_no_reader(self, fd):
        if fd in self.readers:
            raise AssertionError("fd {fd} is registered".format(fd=fd))

    def _add_writer(self, fd, callback, *args):
        self.writers[fd] = asyncio.events.Handle(callback, args, self)

    def _remove_writer(self, fd):
        self.remove_writer_count[fd] += 1
        if fd in self.writers:
            del self.writers[fd]
            return True
        else:
            return False

    def assert_writer(self, fd, callback, *args):
        assert fd in self.writers, "fd {} is not registered".format(fd)
        handle = self.writers[fd]
        assert handle._callback == callback, "{!r} != {!r}".format(
            handle._callback, callback
        )
        assert handle._args == args, "{!r} != {!r}".format(handle._args, args)

    def _ensure_fd_no_transport(self, fd):
        try:
            transport = self._transports[fd]
        except KeyError:
            pass
        else:
            raise RuntimeError(
                "File descriptor {!r} is used by transport {!r}".format(fd, transport)
            )

    def add_reader(self, fd, callback, *args):
        """Add a reader callback."""
        self._ensure_fd_no_transport(fd)
        return self._add_reader(fd, callback, *args)

    def remove_reader(self, fd):
        """Remove a reader callback."""
        self._ensure_fd_no_transport(fd)
        return self._remove_reader(fd)

    def add_writer(self, fd, callback, *args):
        """Add a writer callback.."""
        self._ensure_fd_no_transport(fd)
        return self._add_writer(fd, callback, *args)

    def remove_writer(self, fd):
        """Remove a writer callback."""
        self._ensure_fd_no_transport(fd)
        return self._remove_writer(fd)

    def reset_counters(self):
        self.remove_reader_count = collections.defaultdict(int)
        self.remove_writer_count = collections.defaultdict(int)

    def _process_events(self, event_list):
        return

    def _write_to_self(self):
        pass


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.loop = TestLoop()
        asyncio.set_event_loop(self.loop)
        self.sock = mock.Mock()
        self.sock.closed = False
        self.proto = make_test_protocol(aiozmq.ZmqProtocol)
        self.tr = _ZmqTransportImpl(self.loop, zmq.SUB, self.sock, self.proto)
        self.exc_handler = mock.Mock()
        self.loop.set_exception_handler(self.exc_handler)

    def tearDown(self):
        self.loop.close()
        asyncio.set_event_loop(None)

    def test_empty_write(self):
        self.tr.write([b""])
        self.assertTrue(self.sock.send_multipart.called)
        self.assertFalse(self.proto.pause_writing.called)
        self.assertFalse(self.tr._buffer)
        self.assertEqual(0, self.tr._buffer_size)
        self.assertFalse(self.exc_handler.called)
        self.assertNotIn(self.sock, self.loop.writers)

    def test_write(self):
        self.tr.write((b"a", b"b"))
        self.sock.send_multipart.assert_called_with((b"a", b"b"), zmq.DONTWAIT)
        self.assertFalse(self.proto.pause_writing.called)
        self.assertFalse(self.tr._buffer)
        self.assertEqual(0, self.tr._buffer_size)
        self.assertFalse(self.exc_handler.called)
        self.assertNotIn(self.sock, self.loop.writers)

    def test_partial_write(self):
        self.sock.send_multipart.side_effect = zmq.ZMQError(errno.EAGAIN)
        self.tr.write((b"a", b"b"))
        self.sock.send_multipart.assert_called_with((b"a", b"b"), zmq.DONTWAIT)
        self.assertFalse(self.proto.pause_writing.called)
        self.assertEqual([(2, (b"a", b"b"))], list(self.tr._buffer))
        self.assertEqual(2, self.tr._buffer_size)
        self.assertFalse(self.exc_handler.called)
        self.loop.assert_writer(self.sock, self.tr._write_ready)

    def test_partial_double_write(self):
        self.sock.send_multipart.side_effect = zmq.ZMQError(errno.EAGAIN)
        self.tr.write((b"a", b"b"))
        self.tr.write((b"c",))
        self.sock.send_multipart.mock_calls = [mock.call((b"a", b"b"), zmq.DONTWAIT)]
        self.assertFalse(self.proto.pause_writing.called)
        self.assertEqual([(2, (b"a", b"b")), (1, (b"c",))], list(self.tr._buffer))
        self.assertEqual(3, self.tr._buffer_size)
        self.assertFalse(self.exc_handler.called)
        self.loop.assert_writer(self.sock, self.tr._write_ready)

    def test__write_ready(self):
        self.tr._buffer.append((2, (b"a", b"b")))
        self.tr._buffer.append((1, (b"c",)))
        self.tr._buffer_size = 3
        self.loop.add_writer(self.sock, self.tr._write_ready)

        self.tr._write_ready()

        self.sock.send_multipart.mock_calls = [mock.call((b"a", b"b"), zmq.DONTWAIT)]
        self.assertFalse(self.proto.pause_writing.called)
        self.assertEqual([(1, (b"c",))], list(self.tr._buffer))
        self.assertEqual(1, self.tr._buffer_size)
        self.assertFalse(self.exc_handler.called)
        self.loop.assert_writer(self.sock, self.tr._write_ready)

    def test__write_ready_sent_whole_buffer(self):
        self.tr._buffer.append((2, (b"a", b"b")))
        self.tr._buffer_size = 2
        self.loop.add_writer(self.sock, self.tr._write_ready)

        self.sock.send_multipart.mock_calls = [mock.call((b"a", b"b"), zmq.DONTWAIT)]
        self.tr._write_ready()

        self.assertFalse(self.proto.pause_writing.called)
        self.assertFalse(self.tr._buffer)
        self.assertEqual(0, self.tr._buffer_size)
        self.assertFalse(self.exc_handler.called)
        self.assertEqual(1, self.loop.remove_writer_count[self.sock])

    def test__write_ready_raises_ZMQError(self):
        self.tr._buffer.append((2, (b"a", b"b")))
        self.tr._buffer_size = 2
        self.loop.add_writer(self.sock, self.tr._write_ready)

        self.sock.send_multipart.side_effect = zmq.ZMQError(
            errno.ENOTSUP, "not supported"
        )
        self.tr._write_ready()
        self.assertFalse(self.proto.pause_writing.called)
        self.assertFalse(self.tr._buffer)
        self.assertEqual(0, self.tr._buffer_size)
        self.assertTrue(self.exc_handler.called)
        self.assertEqual(1, self.loop.remove_writer_count[self.sock])
        self.assertTrue(self.tr._closing)
        self.assertEqual(1, self.loop.remove_reader_count[self.sock])

    def test__write_ready_raises_EAGAIN(self):
        self.tr._buffer.append((2, (b"a", b"b")))
        self.tr._buffer_size = 2
        self.loop.add_writer(self.sock, self.tr._write_ready)

        self.sock.send_multipart.side_effect = zmq.ZMQError(errno.EAGAIN, "try again")
        self.tr._write_ready()
        self.assertFalse(self.proto.pause_writing.called)
        self.assertEqual(
            [
                (
                    2,
                    (
                        b"a",
                        b"b",
                    ),
                )
            ],
            list(self.tr._buffer),
        )
        self.assertEqual(2, self.tr._buffer_size)
        self.assertFalse(self.exc_handler.called)
        self.loop.assert_writer(self.sock, self.tr._write_ready)
        self.assertFalse(self.tr._closing)
        self.loop.assert_reader(self.sock, self.tr._read_ready)

    def test_close_with_empty_buffer(self):
        self.tr.close()

        self.assertTrue(self.tr._closing)
        self.assertEqual(1, self.loop.remove_reader_count[self.sock])
        self.assertFalse(self.tr._buffer)
        self.assertEqual(0, self.tr._buffer_size)
        self.assertIsNotNone(self.tr._protocol)
        self.assertIsNotNone(self.tr._zmq_sock)
        self.assertIsNotNone(self.tr._loop)
        self.assertFalse(self.sock.close.called)

        self.loop.run_until_complete(dummy())

        self.proto.connection_lost.assert_called_with(None)
        self.assertIsNone(self.tr._protocol)
        self.assertIsNone(self.tr._zmq_sock)
        self.assertIsNone(self.tr._loop)
        self.sock.close.assert_called_with()

    def test_close_already_closed_socket(self):
        self.tr._zmq_sock.closed = True
        self.tr.close()

        self.assertTrue(self.tr._closing)
        self.assertEqual(1, self.loop.remove_reader_count[self.sock])
        self.assertFalse(self.tr._buffer)
        self.assertEqual(0, self.tr._buffer_size)
        self.assertIsNotNone(self.tr._protocol)
        self.assertIsNotNone(self.tr._zmq_sock)
        self.assertIsNotNone(self.tr._loop)
        self.assertFalse(self.sock.close.called)

        self.loop.run_until_complete(dummy())

        self.proto.connection_lost.assert_called_with(None)
        self.assertIsNone(self.tr._protocol)
        self.assertIsNone(self.tr._zmq_sock)
        self.assertIsNone(self.tr._loop)
        self.assertFalse(self.sock.close.called)

    def test_close_with_waiting_buffer(self):
        self.tr._buffer = deque([(b"data",)])
        self.tr._buffer_size = 4
        self.loop.add_writer(self.sock, self.tr._write_ready)

        self.tr.close()

        self.assertEqual(1, self.loop.remove_reader_count[self.sock])
        self.assertEqual(0, self.loop.remove_writer_count[self.sock])
        self.assertEqual([(b"data",)], list(self.tr._buffer))
        self.assertEqual(4, self.tr._buffer_size)
        self.assertTrue(self.tr._closing)

        self.assertIsNotNone(self.tr._protocol)
        self.assertIsNotNone(self.tr._zmq_sock)
        self.assertIsNotNone(self.tr._loop)
        self.assertFalse(self.sock.close.called)

        self.loop.run_until_complete(dummy())

        self.assertIsNotNone(self.tr._protocol)
        self.assertIsNotNone(self.tr._zmq_sock)
        self.assertIsNotNone(self.tr._loop)
        self.assertFalse(self.sock.close.called)
        self.assertFalse(self.proto.connection_lost.called)

    def test_double_closing(self):
        self.tr.close()
        self.tr.close()
        self.assertEqual(1, self.loop.remove_reader_count[self.sock])

    def test_close_on_last__write_ready(self):
        self.tr._buffer = deque([(4, (b"data",))])
        self.tr._buffer_size = 4
        self.loop.add_writer(self.sock, self.tr._write_ready)

        self.tr.close()
        self.tr._write_ready()

        self.assertFalse(self.tr._buffer)
        self.assertEqual(0, self.tr._buffer_size)
        self.assertIsNone(self.tr._protocol)
        self.assertIsNone(self.tr._zmq_sock)
        self.assertIsNone(self.tr._loop)
        self.proto.connection_lost.assert_called_with(None)
        self.sock.close.assert_called_with()

    def test_close_paused(self):
        self.tr.pause_reading()
        self.assertEqual(1, self.loop.remove_reader_count[self.sock])
        self.tr.close()

        self.assertTrue(self.tr._closing)
        self.assertEqual(1, self.loop.remove_reader_count[self.sock])
        self.assertFalse(self.tr._buffer)
        self.assertEqual(0, self.tr._buffer_size)
        self.assertIsNotNone(self.tr._protocol)
        self.assertIsNotNone(self.tr._zmq_sock)
        self.assertIsNotNone(self.tr._loop)
        self.assertFalse(self.sock.close.called)

        self.loop.run_until_complete(dummy())

        self.proto.connection_lost.assert_called_with(None)
        self.assertIsNone(self.tr._protocol)
        self.assertIsNone(self.tr._zmq_sock)
        self.assertIsNone(self.tr._loop)
        self.sock.close.assert_called_with()

    def test_write_eof(self):
        self.assertFalse(self.tr.can_write_eof())

    def test_dns_address(self):
        async def go():
            with self.assertRaises(ValueError):
                await self.tr.connect("tcp://example.com:8080")

    def test_write_none(self):
        self.tr.write(None)
        self.assertFalse(self.sock.send_multipart.called)

    def test_write_noniterable(self):
        self.assertRaises(TypeError, self.tr.write, 1)
        self.assertFalse(self.sock.send_multipart.called)

    def test_write_nonbytes(self):
        self.assertRaises(TypeError, self.tr.write, [1])
        self.assertFalse(self.sock.send_multipart.called)

    def test_abort_with_empty_buffer(self):
        self.tr.abort()

        self.assertTrue(self.tr._closing)
        self.assertEqual(1, self.loop.remove_reader_count[self.sock])
        self.assertFalse(self.tr._buffer)
        self.assertEqual(0, self.tr._buffer_size)
        self.assertIsNotNone(self.tr._protocol)
        self.assertIsNotNone(self.tr._zmq_sock)
        self.assertIsNotNone(self.tr._loop)
        self.assertFalse(self.sock.close.called)

        self.loop.run_until_complete(dummy())

        self.proto.connection_lost.assert_called_with(None)
        self.assertIsNone(self.tr._protocol)
        self.assertIsNone(self.tr._zmq_sock)
        self.assertIsNone(self.tr._loop)
        self.sock.close.assert_called_with()

    def test_abort_with_waiting_buffer(self):
        self.tr._buffer = deque([(b"data",)])
        self.tr._buffer_size = 4
        self.loop.add_writer(self.sock, self.tr._write_ready)

        self.tr.abort()

        self.assertEqual(1, self.loop.remove_reader_count[self.sock])
        self.assertEqual(1, self.loop.remove_writer_count[self.sock])
        self.assertEqual([], list(self.tr._buffer))
        self.assertEqual(0, self.tr._buffer_size)
        self.assertTrue(self.tr._closing)

        self.loop.run_until_complete(dummy())

        self.assertIsNone(self.tr._protocol)
        self.assertIsNone(self.tr._zmq_sock)
        self.assertIsNone(self.tr._loop)
        self.assertTrue(self.proto.connection_lost.called)
        self.assertTrue(self.sock.close.called)

    def test_abort_with_close_on_waiting_buffer(self):
        self.tr._buffer = deque([(b"data",)])
        self.tr._buffer_size = 4
        self.loop.add_writer(self.sock, self.tr._write_ready)

        self.tr.close()
        self.tr.abort()

        self.assertEqual(1, self.loop.remove_reader_count[self.sock])
        self.assertEqual(1, self.loop.remove_writer_count[self.sock])
        self.assertEqual([], list(self.tr._buffer))
        self.assertEqual(0, self.tr._buffer_size)
        self.assertTrue(self.tr._closing)

        self.loop.run_until_complete(dummy())

        self.assertIsNone(self.tr._protocol)
        self.assertIsNone(self.tr._zmq_sock)
        self.assertIsNone(self.tr._loop)
        self.assertTrue(self.proto.connection_lost.called)
        self.assertTrue(self.sock.close.called)

    def test_abort_paused(self):
        self.tr.pause_reading()
        self.assertEqual(1, self.loop.remove_reader_count[self.sock])
        self.tr.abort()

        self.assertTrue(self.tr._closing)
        self.assertEqual(1, self.loop.remove_reader_count[self.sock])
        self.assertFalse(self.tr._buffer)
        self.assertEqual(0, self.tr._buffer_size)
        self.assertIsNotNone(self.tr._protocol)
        self.assertIsNotNone(self.tr._zmq_sock)
        self.assertIsNotNone(self.tr._loop)
        self.assertFalse(self.sock.close.called)

        self.loop.run_until_complete(dummy())

        self.proto.connection_lost.assert_called_with(None)
        self.assertIsNone(self.tr._protocol)
        self.assertIsNone(self.tr._zmq_sock)
        self.assertIsNone(self.tr._loop)
        self.sock.close.assert_called_with()

    def test__read_ready_got_EAGAIN(self):
        self.sock.recv_multipart.side_effect = zmq.ZMQError(errno.EAGAIN)
        self.tr._fatal_error = mock.Mock()

        self.tr._read_ready()

        self.assertFalse(self.tr._fatal_error.called)
        self.assertFalse(self.proto.msg_received.called)

    def test__read_ready_got_fatal_error(self):
        self.sock.recv_multipart.side_effect = zmq.ZMQError(errno.EINVAL)
        self.tr._fatal_error = mock.Mock()

        self.tr._read_ready()

        self.assertFalse(self.proto.msg_received.called)
        exc = self.tr._fatal_error.call_args[0][0]
        self.assertIsInstance(exc, OSError)
        self.assertEqual(exc.errno, errno.EINVAL)

    def test_setsockopt_EINTR(self):
        self.sock.setsockopt.side_effect = [zmq.ZMQError(errno.EINTR), None]
        self.assertIsNone(self.tr.setsockopt("opt", "val"))
        self.assertEqual(
            [mock.call("opt", "val"), mock.call("opt", "val")],
            self.sock.setsockopt.call_args_list,
        )

    def test_getsockopt_EINTR(self):
        self.sock.getsockopt.side_effect = [zmq.ZMQError(errno.EINTR), "val"]
        self.assertEqual("val", self.tr.getsockopt("opt"))
        self.assertEqual(
            [mock.call("opt"), mock.call("opt")], self.sock.getsockopt.call_args_list
        )

    def test_write_EAGAIN(self):
        self.sock.send_multipart.side_effect = zmq.ZMQError(errno.EAGAIN)
        self.tr.write((b"a", b"b"))
        self.sock.send_multipart.assert_called_once_with((b"a", b"b"), zmq.DONTWAIT)
        self.assertFalse(self.proto.pause_writing.called)
        self.assertEqual([(2, (b"a", b"b"))], list(self.tr._buffer))
        self.assertEqual(2, self.tr._buffer_size)
        self.assertFalse(self.exc_handler.called)
        self.loop.assert_writer(self.sock, self.tr._write_ready)

    def test_write_EINTR(self):
        self.sock.send_multipart.side_effect = zmq.ZMQError(errno.EINTR)
        self.tr.write((b"a", b"b"))
        self.sock.send_multipart.assert_called_once_with((b"a", b"b"), zmq.DONTWAIT)
        self.assertFalse(self.proto.pause_writing.called)
        self.assertEqual([(2, (b"a", b"b"))], list(self.tr._buffer))
        self.assertEqual(2, self.tr._buffer_size)
        self.assertFalse(self.exc_handler.called)
        self.loop.assert_writer(self.sock, self.tr._write_ready)

    def test_write_common_error(self):
        self.sock.send_multipart.side_effect = zmq.ZMQError(errno.ENOTSUP)
        self.tr.write((b"a", b"b"))
        self.sock.send_multipart.assert_called_once_with((b"a", b"b"), zmq.DONTWAIT)
        self.assertFalse(self.proto.pause_writing.called)
        self.assertFalse(self.tr._buffer)
        self.assertEqual(0, self.tr._buffer_size)
        self.assertNotIn(self.sock, self.loop.writers)
        check_errno(errno.ENOTSUP, self.exc_handler.call_args[0][1]["exception"])

    def test_subscribe_invalid_socket_type(self):
        self.tr._zmq_type = zmq.PUB
        self.assertRaises(NotImplementedError, self.tr.subscribe, b"a")
        self.assertRaises(NotImplementedError, self.tr.unsubscribe, b"a")
        self.assertRaises(NotImplementedError, self.tr.subscriptions)

    def test_double_subscribe(self):
        self.tr.subscribe(b"val")
        self.tr.subscribe(b"val")
        self.assertEqual({b"val"}, self.tr.subscriptions())
        self.sock.setsockopt.assert_called_once_with(zmq.SUBSCRIBE, b"val")

    def test_subscribe_bad_value_type(self):
        self.assertRaises(TypeError, self.tr.subscribe, "a")
        self.assertFalse(self.tr.subscriptions())
        self.assertRaises(TypeError, self.tr.unsubscribe, "a")
        self.assertFalse(self.sock.setsockopt.called)
        self.assertFalse(self.tr.subscriptions())

    def test_unsubscribe(self):
        self.tr.subscribe(b"val")

        self.tr.unsubscribe(b"val")
        self.assertFalse(self.tr.subscriptions())
        self.sock.setsockopt.assert_called_with(zmq.UNSUBSCRIBE, b"val")

    def test__set_write_buffer_limits1(self):
        self.tr.set_write_buffer_limits(low=10)
        self.assertEqual(10, self.tr._low_water)
        self.assertEqual(40, self.tr._high_water)

    def test__set_write_buffer_limits2(self):
        self.tr.set_write_buffer_limits(high=60)
        self.assertEqual(15, self.tr._low_water)
        self.assertEqual(60, self.tr._high_water)

    def test__set_write_buffer_limits3(self):
        with self.assertRaises(ValueError):
            self.tr.set_write_buffer_limits(high=1, low=2)

    def test_get_write_buffer_limits(self):
        self.tr.set_write_buffer_limits(low=128, high=256)
        self.assertEqual((128, 256), self.tr.get_write_buffer_limits())

    def test__maybe_pause_protocol(self):
        self.tr.set_write_buffer_limits(high=10)
        self.assertFalse(self.tr._protocol_paused)
        self.sock.send_multipart.side_effect = zmq.ZMQError(errno.EAGAIN)
        self.tr.write([b"binary data"])
        self.assertEqual(11, self.tr._buffer_size)
        self.assertTrue(self.tr._protocol_paused)
        self.proto.pause_writing.assert_called_with()

    def test__maybe_pause_protocol_err(self):
        self.tr.set_write_buffer_limits(high=10)
        ceh = self.loop.call_exception_handler = mock.Mock()
        self.assertFalse(self.tr._protocol_paused)
        self.sock.send_multipart.side_effect = zmq.ZMQError(errno.EAGAIN)
        self.proto.pause_writing.side_effect = exc = RuntimeError()
        self.tr.write([b"binary data"])
        self.assertEqual(11, self.tr._buffer_size)
        self.assertTrue(self.tr._protocol_paused)
        ceh.assert_called_with(
            {
                "transport": self.tr,
                "exception": exc,
                "protocol": self.proto,
                "message": "protocol.pause_writing() failed",
            }
        )

    def test__maybe_pause_protocol_already_paused(self):
        self.tr.set_write_buffer_limits(high=10)
        self.tr._protocol_paused = True
        self.sock.send_multipart.side_effect = zmq.ZMQError(errno.EAGAIN)
        self.tr.write([b"binary data"])
        self.assertEqual(11, self.tr._buffer_size)
        self.assertTrue(self.tr._protocol_paused)
        self.assertFalse(self.proto.pause_writing.called)

    def test__maybe_resume_protocol(self):
        self.tr.set_write_buffer_limits()
        self.tr._protocol_paused = True
        self.tr._buffer_size = 11
        self.tr._buffer.append((11, [b"binary data"]))

        self.tr._write_ready()
        self.assertEqual(0, self.tr._buffer_size)
        self.assertFalse(self.tr._buffer)

        self.assertFalse(self.tr._protocol_paused)
        self.proto.resume_writing.assert_called_with()

    def test__maybe_resume_protocol_err(self):
        self.tr.set_write_buffer_limits()
        self.tr._protocol_paused = True
        self.tr._buffer_size = 11
        self.tr._buffer.append((11, [b"binary data"]))
        ceh = self.loop.call_exception_handler = mock.Mock()
        self.proto.resume_writing.side_effect = exc = RuntimeError()

        self.tr._write_ready()
        self.assertEqual(0, self.tr._buffer_size)
        self.assertFalse(self.tr._buffer)

        self.assertFalse(self.tr._protocol_paused)
        ceh.assert_called_with(
            {
                "transport": self.tr,
                "exception": exc,
                "protocol": self.proto,
                "message": "protocol.resume_writing() failed",
            }
        )

    def test_pause_resume_reading(self):
        self.assertFalse(self.tr._paused)
        self.loop.assert_reader(self.sock, self.tr._read_ready)
        self.tr.pause_reading()
        self.assertTrue(self.tr._paused)
        self.assertNotIn(self.sock, self.loop.readers)
        self.tr.resume_reading()
        self.assertFalse(self.tr._paused)
        self.loop.assert_reader(self.sock, self.tr._read_ready)

    def test_pause_closing(self):
        self.tr.close()
        with self.assertRaises(RuntimeError):
            self.tr.pause_reading()

    def test_pause_paused(self):
        self.tr.pause_reading()
        with self.assertRaises(RuntimeError):
            self.tr.pause_reading()

    def test_resume_not_paused(self):
        with self.assertRaises(RuntimeError):
            self.tr.resume_reading()

    def test_resume_closed(self):
        self.assertIn(self.sock, self.loop.readers)
        self.tr.pause_reading()
        self.tr.close()
        self.tr.resume_reading()
        self.assertNotIn(self.sock, self.loop.readers)

    def test_conn_lost_on_force_close(self):
        self.tr._conn_lost = 1
        self.tr._force_close(RuntimeError())
        self.assertEqual(1, self.tr._conn_lost)


class LooplessTransportTests(unittest.TestCase):
    def setUp(self):
        self.loop = TestLoop()
        asyncio.set_event_loop(self.loop)
        self.sock = mock.Mock()
        self.sock.closed = False
        self.waiter = asyncio.Future()
        self.proto = make_test_protocol(aiozmq.ZmqProtocol)
        self.tr = _ZmqLooplessTransportImpl(
            self.loop, zmq.SUB, self.sock, self.proto, self.waiter
        )
        self.exc_handler = mock.Mock()
        self.loop.set_exception_handler(self.exc_handler)

    def tearDown(self):
        self.loop.close()
        asyncio.set_event_loop(None)

    def test_incomplete_read(self):
        self.sock.recv_multipart.side_effect = zmq.Again(errno.EAGAIN)
        self.tr._do_read()
        self.assertFalse(self.tr._closing)
        self.assertFalse(self.proto.msg_received.called)

    def test_bad_read(self):
        self.sock.recv_multipart.side_effect = zmq.ZMQError(errno.ENOTSOCK)
        self.tr._do_read()
        self.assertTrue(self.tr._closing)
        self.assertFalse(self.proto.msg_received.called)

    def test_pending_write_without_buffer(self):
        self.assertFalse(self.tr._buffer)
        self.tr._do_write()
        self.assertFalse(self.sock.send_multipart.called)

    def test_incomplete_pending_write(self):
        self.tr._buffer = [(4, [b"data"])]
        self.tr._buffer_size = 4
        self.sock.send_multipart.side_effect = zmq.Again(errno.EAGAIN)
        self.tr._do_write()
        self.assertEqual(4, self.tr._buffer_size)
        self.assertEqual([(4, [b"data"])], self.tr._buffer)

    def test_bad_pending_write(self):
        self.tr._buffer = [(4, [b"data"])]
        self.tr._buffer_size = 4
        self.sock.send_multipart.side_effect = zmq.ZMQError(errno.ENOTSOCK)
        self.tr._do_write()
        self.assertEqual(0, self.tr._buffer_size)
        self.assertEqual([], self.tr._buffer)
        self.assertTrue(self.tr._closing)
