import asyncio
from asyncio.streams import FlowControlMixin
from .interface import ZmqProtocol


@asyncio.coroutine
def create_zmq_connection(zmq_type, *, bind=None, connect=None,
                          loop=None, zmq_sock=None, limit=0xffff):
    """A wrapper for create_connection() returning a Stream instance.

    The arguments are all the usual arguments to create_connection()
    except protocol_factory; most common are positional host and port,
    with various optional keyword arguments following.

    Additional optional keyword arguments are loop (to set the event loop
    instance to use) and limit (to set the buffer limit passed to the
    StreamReader).

    (If you want to customize the StreamReader and/or
    StreamReaderProtocol classes, just copy the code -- there's
    really nothing special here except some convenience.)
    """
    if loop is None:
        loop = asyncio.get_event_loop()
    stream = ZmqStream(loop=loop, limit=limit)
    yield from loop.create_zmq_connection(
        lambda: stream._protocol, zmq_type, bind=bind, connect=connect,
        zmq_sock=zmq_sock)
    return stream


class ZmqStreamProtocol(FlowControlMixin, ZmqProtocol):
    """Helper class to adapt between ZmqProtocol and ZmqStream.

    This is a helper class to use ZmqStream instead of subclassing
    ZmqProtocol.
    """

    def __init__(self, stream, loop=None):
        super().__init__(loop=loop)
        self._stream = stream

    def connection_made(self, transport):
        self._stream.set_transport(transport)

    def connection_lost(self, exc):
        if exc is None:
            self._stream.feed_closing()
        else:
            self._stream.set_exception(exc)
        super().connection_lost(exc)

    def msg_received(self, msg):
        self._stream.feed_msg(msg)


class ZmqStream:
    """Wraps a ZmqTransport.

    This exposes write(), getsockopt(), setsockopt(), connect(),
    disconnect(), connections(), bind(), unbind(), bindings(),
    subscribe(), unsubscribe(), subscriptions(), get_extra_info() and
    close().  It adds drain() which returns an optional Future on
    which you can wait for flow control.  It also adds a transport
    property which references the ZmqTransport directly.
    """

    def __init__(self, loop, limit=0xffff):
        self._transport = None
        self._protocol = ZmqStreamProtocol(self, loop=loop)
        self._loop = loop
        self._queue = asyncio.Queue(loop=loop)
        self._closing = False  # Whether we're done.
        self._waiter = None  # A future.
        self._exception = None
        self._paused = False
        self._limit = limit
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

    def drain(self):
        """This method has an unusual return value.

        The intended use is to write

          w.write(data)
          yield from w.drain()

        When there's nothing to wait for, drain() returns (), and the
        yield-from continues immediately.  When the transport buffer
        is full (the protocol is paused), drain() creates and returns
        a Future and the yield-from will block until that Future is
        completed, which will happen when the buffer is (partially)
        drained and the protocol is resumed.
        """
        if self._stream is not None and self._stream._exception is not None:
            raise self._stream._exception
        return self._protocol._make_drain_waiter()

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

    def _maybe_resume_transport(self):
        if self._paused and self._queue_len <= self._limit:
            self._paused = False
            self._transport.resume_reading()

    def feed_closing(self):
        """Private"""
        self._eof = True
        waiter = self._waiter
        if waiter is not None:
            self._waiter = None
            if not waiter.cancelled():
                waiter.set_result(True)

    def at_closing(self):
        """Return True if the buffer is empty and 'feed_eof' was called."""
        return self._closing and not self._queue

    def feed_msg(self, msg):
        """Private"""
        assert not self._closing, 'feed_msg after feed_closing'

        if not msg:
            return

        self._queue.put_nowait(msg)
        self._queue_len += sum(len(i) for i in msg)

        waiter = self._waiter
        if waiter is not None:
            self._waiter = None
            if not waiter.cancelled():
                waiter.set_result(False)

        if (self._transport is not None and
                not self._paused and
                self._queue_len > 2*self._limit):
            try:
                self._transport.pause_reading()
            except NotImplementedError:
                # The transport can't be paused.
                # We'll just have to buffer all data.
                # Forget the transport so we don't keep trying.
                self._transport = None
            else:
                self._paused = True

    @asyncio.coroutine
    def read(self):
        if self._exception is not None:
            raise self._exception

        msg = yield from self._queue.get()
        self._queue_len -= sum(len(i) for i in msg)
        self._maybe_resume_transport()
        return msg
