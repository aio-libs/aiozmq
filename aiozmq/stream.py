import collections
import asyncio
from .core import create_zmq_connection
from .interface import ZmqProtocol


class ZmqStreamClosed(Exception):
    """A stream was closed"""


@asyncio.coroutine
def create_zmq_stream(zmq_type, *, bind=None, connect=None,
                      loop=None, zmq_sock=None,
                      high_read=None, low_read=None,
                      high_write=None, low_write=None):
    """A wrapper for create_zmq_connection() returning a Stream instance.

    The arguments are all the usual arguments to create_connection()
    except protocol_factory; most common are positional host and port,
    with various optional keyword arguments following.

    Additional optional keyword arguments are loop (to set the event
    loop instance to use) and high_read, low_read, high_write,
    low_write -- high and low watermarks for reading and writing
    respectively.

    """
    if loop is None:
        loop = asyncio.get_event_loop()
    stream = ZmqStream(loop=loop, high=high_read, low=low_read)
    tr, _ = yield from create_zmq_connection(
        lambda: stream._protocol,
        zmq_type,
        bind=bind,
        connect=connect,
        zmq_sock=zmq_sock,
        loop=loop)
    tr.set_write_buffer_limits(high_write, low_write)
    return stream


class ZmqStreamProtocol(ZmqProtocol):
    """Helper class to adapt between ZmqProtocol and ZmqStream.

    This is a helper class to use ZmqStream instead of subclassing
    ZmqProtocol.
    """

    def __init__(self, stream, loop):
        self._loop = loop
        self._stream = stream
        self._paused = False
        self._drain_waiter = None
        self._connection_lost = False

    def pause_writing(self):
        assert not self._paused
        self._paused = True

    def resume_writing(self):
        assert self._paused
        self._paused = False
        waiter = self._drain_waiter
        if waiter is not None:
            self._drain_waiter = None
            if not waiter.done():
                waiter.set_result(None)

    def connection_made(self, transport):
        self._stream.set_transport(transport)

    def connection_lost(self, exc):
        self._connection_lost = True
        if exc is None:
            self._stream.feed_closing()
        else:
            self._stream.set_exception(exc)
        if not self._paused:
            return
        waiter = self._drain_waiter
        if waiter is None:
            return
        self._drain_waiter = None
        if waiter.done():
            return
        if exc is None:
            waiter.set_result(None)
        else:
            waiter.set_exception(exc)

    @asyncio.coroutine
    def _drain_helper(self):
        if self._connection_lost:
            raise ConnectionResetError('Connection lost')
        if not self._paused:
            return
        waiter = self._drain_waiter
        assert waiter is None or waiter.cancelled()
        waiter = asyncio.Future(loop=self._loop)
        self._drain_waiter = waiter
        yield from waiter

    def msg_received(self, msg):
        self._stream.feed_msg(msg)


class ZmqStream:
    """Wraps a ZmqTransport.

    Has write() method and read() coroutine for writing and reading
    ZMQ messages.

    It adds drain() coroutine which can be used for waiting for flow
    control.

    It also adds a transport property which references the
    ZmqTransport directly.

    """

    def __init__(self, loop, *, high=None, low=None):
        self._transport = None
        self._protocol = ZmqStreamProtocol(self, loop=loop)
        self._loop = loop
        self._queue = collections.deque()
        self._closing = False  # Whether we're done.
        self._waiter = None  # A future.
        self._exception = None
        self._paused = False
        self._set_read_buffer_limits(high, low)
        self._queue_len = 0

    @property
    def transport(self):
        return self._transport

    def write(self, msg):
        self._transport.write(msg)

    def close(self):
        return self._transport.close()

    def get_extra_info(self, name, default=None):
        return self._transport.get_extra_info(name, default)

    @asyncio.coroutine
    def drain(self):
        """Flush the write buffer.

        The intended use is to write

          w.write(data)
          yield from w.drain()
        """
        if self._exception is not None:
            raise self._exception
        yield from self._protocol._drain_helper()

    def exception(self):
        return self._exception

    def set_exception(self, exc):
        """Private"""
        self._exception = exc

        waiter = self._waiter
        if waiter is not None:
            self._waiter = None
            if not waiter.cancelled():
                waiter.set_exception(exc)

    def set_transport(self, transport):
        """Private"""
        assert self._transport is None, 'Transport already set'
        self._transport = transport

    def _set_read_buffer_limits(self, high=None, low=None):
        if high is None:
            if low is None:
                high = 64*1024
            else:
                high = 4*low
        if low is None:
            low = high // 4
        if not high >= low >= 0:
            raise ValueError('high (%r) must be >= low (%r) must be >= 0' %
                             (high, low))
        self._high_water = high
        self._low_water = low

    def set_read_buffer_limits(self, high=None, low=None):
        self._set_read_buffer_limits(high, low)
        self._maybe_resume_transport()

    def _maybe_resume_transport(self):
        if self._paused and self._queue_len <= self._low_water:
            self._paused = False
            self._transport.resume_reading()

    def feed_closing(self):
        """Private"""
        self._closing = True
        self._transport = None
        waiter = self._waiter
        if waiter is not None:
            self._waiter = None
            if not waiter.cancelled():
                waiter.set_exception(ZmqStreamClosed())

    def at_closing(self):
        """Return True if the buffer is empty and 'feed_closing' was called."""
        return self._closing and not self._queue

    def feed_msg(self, msg):
        """Private"""
        assert not self._closing, 'feed_msg after feed_closing'

        msg_len = sum(len(i) for i in msg)
        self._queue.append((msg_len, msg))
        self._queue_len += msg_len

        waiter = self._waiter
        if waiter is not None:
            self._waiter = None
            if not waiter.cancelled():
                waiter.set_result(None)
        if (self._transport is not None and
                not self._paused and
                self._queue_len > self._high_water):
            self._transport.pause_reading()
            self._paused = True

    @asyncio.coroutine
    def read(self):
        if self._exception is not None:
            raise self._exception

        if self._closing:
            raise ZmqStreamClosed()

        if not self._queue_len:
            if self._waiter is not None:
                raise RuntimeError('read called while another coroutine is '
                                   'already waiting for incoming data')
            self._waiter = asyncio.Future(loop=self._loop)
            try:
                yield from self._waiter
            finally:
                self._waiter = None

        msg_len, msg = self._queue.popleft()
        self._queue_len -= msg_len
        self._maybe_resume_transport()
        return msg
