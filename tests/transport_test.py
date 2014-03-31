import unittest

import asyncio
import zmq
import aiozmq
import errno

from collections import deque

from asyncio import test_utils
from aiozmq.core import _ZmqTransportImpl
from unittest import mock

from aiozmq._test_util import check_errno


class TransportTests(unittest.TestCase):

    def setUp(self):
        self.loop = test_utils.TestLoop()
        self.sock = mock.Mock()
        self.proto = test_utils.make_test_protocol(aiozmq.ZmqProtocol)
        self.tr = _ZmqTransportImpl(self.loop, zmq.SUB, self.sock, self.proto)
        self.exc_handler = mock.Mock()
        self.loop.set_exception_handler(self.exc_handler)

    def test_empty_write(self):
        self.tr.write([b''])
        self.assertFalse(self.sock.send_multipart.called)
        self.assertFalse(self.proto.pause_writing.called)
        self.assertFalse(self.tr._buffer)
        self.assertEqual(0, self.tr._buffer_size)
        self.assertFalse(self.exc_handler.called)
        self.assertNotIn(self.sock, self.loop.writers)

    def test_write(self):
        self.tr.write((b'a', b'b'))
        self.sock.send_multipart.assert_called_with((b'a', b'b'), zmq.DONTWAIT)
        self.assertFalse(self.proto.pause_writing.called)
        self.assertFalse(self.tr._buffer)
        self.assertEqual(0, self.tr._buffer_size)
        self.assertFalse(self.exc_handler.called)
        self.assertNotIn(self.sock, self.loop.writers)

    def test_partial_write(self):
        self.sock.send_multipart.side_effect = zmq.ZMQError(errno.EAGAIN)
        self.tr.write((b'a', b'b'))
        self.sock.send_multipart.assert_called_with((b'a', b'b'), zmq.DONTWAIT)
        self.assertFalse(self.proto.pause_writing.called)
        self.assertEqual([(b'a', b'b')], list(self.tr._buffer))
        self.assertEqual(2, self.tr._buffer_size)
        self.assertFalse(self.exc_handler.called)
        self.loop.assert_writer(self.sock, self.tr._write_ready)

    def test_partial_double_write(self):
        self.sock.send_multipart.side_effect = zmq.ZMQError(errno.EAGAIN)
        self.tr.write((b'a', b'b'))
        self.tr.write((b'c',))
        self.sock.send_multipart.mock_calls = [
            mock.call((b'a', b'b'), zmq.DONTWAIT)]
        self.assertFalse(self.proto.pause_writing.called)
        self.assertEqual([(b'a', b'b'), (b'c',)], list(self.tr._buffer))
        self.assertEqual(3, self.tr._buffer_size)
        self.assertFalse(self.exc_handler.called)
        self.loop.assert_writer(self.sock, self.tr._write_ready)

    def test__write_ready(self):
        self.tr._buffer.append((b'a', b'b'))
        self.tr._buffer.append((b'c',))
        self.tr._buffer_size = 3
        self.loop.add_writer(self.sock, self.tr._write_ready)

        self.tr._write_ready()

        self.sock.send_multipart.mock_calls = [
            mock.call((b'a', b'b'), zmq.DONTWAIT)]
        self.assertFalse(self.proto.pause_writing.called)
        self.assertEqual([(b'c',)], list(self.tr._buffer))
        self.assertEqual(1, self.tr._buffer_size)
        self.assertFalse(self.exc_handler.called)
        self.loop.assert_writer(self.sock, self.tr._write_ready)

    def test__write_ready_sent_whole_buffer(self):
        self.tr._buffer.append((b'a', b'b'))
        self.tr._buffer_size = 2
        self.loop.add_writer(self.sock, self.tr._write_ready)

        self.sock.send_multipart.mock_calls = [
            mock.call((b'a', b'b'), zmq.DONTWAIT)]
        self.tr._write_ready()

        self.assertFalse(self.proto.pause_writing.called)
        self.assertFalse(self.tr._buffer)
        self.assertEqual(0, self.tr._buffer_size)
        self.assertFalse(self.exc_handler.called)
        self.assertEqual(1, self.loop.remove_writer_count[self.sock])

    def test__write_ready_raises_ZMQError(self):
        self.tr._buffer.append((b'a', b'b'))
        self.tr._buffer_size = 2
        self.loop.add_writer(self.sock, self.tr._write_ready)

        self.sock.send_multipart.side_effect = zmq.ZMQError(errno.ENOTSUP,
                                                            'not supported')
        self.tr._write_ready()
        self.assertFalse(self.proto.pause_writing.called)
        self.assertFalse(self.tr._buffer)
        self.assertEqual(0, self.tr._buffer_size)
        self.assertTrue(self.exc_handler.called)
        self.assertEqual(1, self.loop.remove_writer_count[self.sock])
        self.assertTrue(self.tr._closing)
        self.assertEqual(1, self.loop.remove_reader_count[self.sock])

    def test__write_ready_raises_EAGAIN(self):
        self.tr._buffer.append((b'a', b'b'))
        self.tr._buffer_size = 2
        self.loop.add_writer(self.sock, self.tr._write_ready)

        self.sock.send_multipart.side_effect = zmq.ZMQError(errno.EAGAIN,
                                                            'try again')
        self.tr._write_ready()
        self.assertFalse(self.proto.pause_writing.called)
        self.assertEqual([(b'a', b'b',)], list(self.tr._buffer))
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

        test_utils.run_briefly(self.loop)

        self.proto.connection_lost.assert_called_with(None)
        self.assertIsNone(self.tr._protocol)
        self.assertIsNone(self.tr._zmq_sock)
        self.assertIsNone(self.tr._loop)
        self.sock.close.assert_called_with()

    def test_close_with_waiting_buffer(self):
        self.tr._buffer = deque([(b'data',)])
        self.tr._buffer_size = 4
        self.loop.add_writer(self.sock, self.tr._write_ready)

        self.tr.close()

        self.assertEqual(1, self.loop.remove_reader_count[self.sock])
        self.assertEqual(0, self.loop.remove_writer_count[self.sock])
        self.assertEqual([(b'data',)], list(self.tr._buffer))
        self.assertEqual(4, self.tr._buffer_size)
        self.assertTrue(self.tr._closing)

        self.assertIsNotNone(self.tr._protocol)
        self.assertIsNotNone(self.tr._zmq_sock)
        self.assertIsNotNone(self.tr._loop)
        self.assertFalse(self.sock.close.called)

        test_utils.run_briefly(self.loop)

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
        self.tr._buffer = deque([(b'data',)])
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

    def test_write_eof(self):
        self.assertFalse(self.tr.can_write_eof())

    def test_dns_address(self):
        @asyncio.coroutine
        def go():
            with self.assertRaises(ValueError):
                yield from self.tr.connect('tcp://example.com:8080')

    def test_write_none(self):
        self.tr.write(None)
        self.assertFalse(self.sock.called)

    def test_write_noniterable(self):
        self.assertRaises(TypeError, self.tr.write, 1)
        self.assertFalse(self.sock.called)

    def test_write_nonbytes(self):
        self.assertRaises(TypeError, self.tr.write, [1])
        self.assertFalse(self.sock.called)

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

        test_utils.run_briefly(self.loop)

        self.proto.connection_lost.assert_called_with(None)
        self.assertIsNone(self.tr._protocol)
        self.assertIsNone(self.tr._zmq_sock)
        self.assertIsNone(self.tr._loop)
        self.sock.close.assert_called_with()

    def test_abort_with_waiting_buffer(self):
        self.tr._buffer = deque([(b'data',)])
        self.tr._buffer_size = 4
        self.loop.add_writer(self.sock, self.tr._write_ready)

        self.tr.abort()

        self.assertEqual(1, self.loop.remove_reader_count[self.sock])
        self.assertEqual(1, self.loop.remove_writer_count[self.sock])
        self.assertEqual([], list(self.tr._buffer))
        self.assertEqual(0, self.tr._buffer_size)
        self.assertTrue(self.tr._closing)

        test_utils.run_briefly(self.loop)

        self.assertIsNone(self.tr._protocol)
        self.assertIsNone(self.tr._zmq_sock)
        self.assertIsNone(self.tr._loop)
        self.assertTrue(self.proto.connection_lost.called)
        self.assertTrue(self.sock.close.called)

    def test_abort_with_close_on_waiting_buffer(self):
        self.tr._buffer = deque([(b'data',)])
        self.tr._buffer_size = 4
        self.loop.add_writer(self.sock, self.tr._write_ready)

        self.tr.close()
        self.tr.abort()

        self.assertEqual(1, self.loop.remove_reader_count[self.sock])
        self.assertEqual(1, self.loop.remove_writer_count[self.sock])
        self.assertEqual([], list(self.tr._buffer))
        self.assertEqual(0, self.tr._buffer_size)
        self.assertTrue(self.tr._closing)

        test_utils.run_briefly(self.loop)

        self.assertIsNone(self.tr._protocol)
        self.assertIsNone(self.tr._zmq_sock)
        self.assertIsNone(self.tr._loop)
        self.assertTrue(self.proto.connection_lost.called)
        self.assertTrue(self.sock.close.called)

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
        self.assertIsNone(self.tr.setsockopt('opt', 'val'))
        self.assertEqual([mock.call('opt', 'val'), mock.call('opt', 'val')],
                         self.sock.setsockopt.call_args_list)

    def test_getsockopt_EINTR(self):
        self.sock.getsockopt.side_effect = [zmq.ZMQError(errno.EINTR), 'val']
        self.assertEqual('val', self.tr.getsockopt('opt'))
        self.assertEqual([mock.call('opt'), mock.call('opt')],
                         self.sock.getsockopt.call_args_list)

    def test_write_EAGAIN(self):
        self.sock.send_multipart.side_effect = zmq.ZMQError(errno.EAGAIN)
        self.tr.write((b'a', b'b'))
        self.sock.send_multipart.assert_called_once_with(
            (b'a', b'b'), zmq.DONTWAIT)
        self.assertFalse(self.proto.pause_writing.called)
        self.assertEqual([(b'a', b'b')], list(self.tr._buffer))
        self.assertEqual(2, self.tr._buffer_size)
        self.assertFalse(self.exc_handler.called)
        self.loop.assert_writer(self.sock, self.tr._write_ready)

    def test_write_EINTR(self):
        self.sock.send_multipart.side_effect = zmq.ZMQError(errno.EINTR)
        self.tr.write((b'a', b'b'))
        self.sock.send_multipart.assert_called_once_with(
            (b'a', b'b'), zmq.DONTWAIT)
        self.assertFalse(self.proto.pause_writing.called)
        self.assertEqual([(b'a', b'b')], list(self.tr._buffer))
        self.assertEqual(2, self.tr._buffer_size)
        self.assertFalse(self.exc_handler.called)
        self.loop.assert_writer(self.sock, self.tr._write_ready)

    def test_write_common_error(self):
        self.sock.send_multipart.side_effect = zmq.ZMQError(errno.ENOTSUP)
        self.tr.write((b'a', b'b'))
        self.sock.send_multipart.assert_called_once_with(
            (b'a', b'b'), zmq.DONTWAIT)
        self.assertFalse(self.proto.pause_writing.called)
        self.assertFalse(self.tr._buffer)
        self.assertEqual(0, self.tr._buffer_size)
        self.assertNotIn(self.sock, self.loop.writers)
        check_errno(errno.ENOTSUP,
                    self.exc_handler.call_args[0][1]['exception'])

    def test_subscribe_invalid_socket_type(self):
        self.tr._zmq_type = zmq.PUB
        self.assertRaises(NotImplementedError, self.tr.subscribe, b'a')
        self.assertRaises(NotImplementedError, self.tr.unsubscribe, b'a')
        self.assertRaises(NotImplementedError, self.tr.subscriptions)

    def test_double_subscribe(self):
        self.tr.subscribe(b'val')
        self.tr.subscribe(b'val')
        self.assertEqual({b'val'}, self.tr.subscriptions())
        self.sock.setsockopt.assert_called_once_with(zmq.SUBSCRIBE, b'val')

    def test_subscribe_bad_value_type(self):
        self.assertRaises(TypeError, self.tr.subscribe, 'a')
        self.assertFalse(self.tr.subscriptions())
        self.assertRaises(TypeError, self.tr.unsubscribe, 'a')
        self.assertFalse(self.sock.setsockopt.called)
        self.assertFalse(self.tr.subscriptions())

    def test_unsubscribe(self):
        self.tr.subscribe(b'val')

        self.tr.unsubscribe(b'val')
        self.assertFalse(self.tr.subscriptions())
        self.sock.setsockopt.assert_called_with(zmq.UNSUBSCRIBE, b'val')
