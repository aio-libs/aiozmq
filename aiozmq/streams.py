from asyncio.streams import FlowControlMixin
from .interface import ZmqProtocol


@tasks.coroutine
def create_zmq__connection(*, bind=None, connect=None,
                           loop=None, limit=_DEFAULT_LIMIT, **kwds):
    """A wrapper for create_connection() returning a (reader, writer) pair.

    The reader returned is a StreamReader instance; the writer is a
    StreamWriter instance.

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
        loop = events.get_event_loop()
    reader = StreamReader(limit=limit, loop=loop)
    protocol = StreamReaderProtocol(reader, loop=loop)
    transport, _ = yield from loop.create_connection(
        lambda: protocol, host, port, **kwds)
    writer = StreamWriter(transport, protocol, reader, loop)
    return reader, writer


class ZmqStreamReaderProtocol(FlowControlMixin, ZmqProtocol):
    """Helper class to adapt between ZmqProtocol and ZmqStreamReader.

    (This is a helper class instead of making ZmqStreamReader itself a
    ZmqProtocol subclass, because the ZmqStreamReader has other potential
    uses, and to prevent the user of the ZmqStreamReader to accidentally
    call inappropriate methods of the protocol.)
    """

    def __init__(self, stream_reader, client_connected_cb=None, loop=None):
        super().__init__(loop=loop)
        self._stream_reader = stream_reader
        self._stream_writer = None
        self._client_connected_cb = client_connected_cb

    def connection_made(self, transport):
        self._stream_reader.set_transport(transport)
        if self._client_connected_cb is not None:
            self._stream_writer = ZmqStreamWriter(transport, self,
                                                  self._stream_reader,
                                                  self._loop)
            res = self._client_connected_cb(self._stream_reader,
                                            self._stream_writer)
            if asyncio.iscoroutine(res):
                asyncio.Task(res, loop=self._loop)

    def connection_lost(self, exc):
        if exc is None:
            self._stream_reader.feed_closing()
        else:
            self._stream_reader.set_exception(exc)
        super().connection_lost(exc)

    def msg_received(self, msg):
        self._stream_reader.feed_msg(msg)


class ZmqStreamWriter:
    """Wraps a ZmqTransport.

    This exposes write(), getsockopt(), setsockopt(), connect(),
    disconnect(), connections(), bind(), unbind(), bindings(),
    subscribe(), unsubscribe(), subscriptions(), get_extra_info() and
    close().  It adds drain() which returns an optional Future on
    which you can wait for flow control.  It also adds a transport
    property which references the ZmqTransport directly.
    """

    def __init__(self, transport, protocol, reader, loop):
        self._transport = transport
        self._protocol = protocol
        self._reader = reader
        self._loop = loop

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
        if self._reader is not None and self._reader._exception is not None:
            raise self._reader._exception
        return self._protocol._make_drain_waiter()


class ZmqStreamReader:

    def __init__(self, limit=_DEFAULT_LIMIT, loop=None):
        # The line length limit is  a security feature;
        # it also doubles as half the buffer limit.
        self._limit = limit
        if loop is None:
            loop = events.get_event_loop()
        self._loop = loop
        self._buffer = bytearray()
        self._closing = False  # Whether we're done.
        self._waiter = None  # A future.
        self._exception = None
        self._transport = None
        self._paused = False

    def exception(self):
        return self._exception

    def set_exception(self, exc):
        self._exception = exc

        waiter = self._waiter
        if waiter is not None:
            self._waiter = None
            if not waiter.cancelled():
                waiter.set_exception(exc)

    def set_transport(self, transport):
        assert self._transport is None, 'Transport already set'
        self._transport = transport

    def _maybe_resume_transport(self):
        if self._paused and len(self._buffer) <= self._limit:
            self._paused = False
            self._transport.resume_reading()

    def feed_eof(self):
        self._eof = True
        waiter = self._waiter
        if waiter is not None:
            self._waiter = None
            if not waiter.cancelled():
                waiter.set_result(True)

    def at_closing(self):
        """Return True if the buffer is empty and 'feed_eof' was called."""
        return self._closing and not self._buffer

    def feed_msg(self, msg):
        assert not self._closing, 'feed_msg after feed_closing'

        if not msg:
            return

        self._buffer.extend(msg)

        waiter = self._waiter
        if waiter is not None:
            self._waiter = None
            if not waiter.cancelled():
                waiter.set_result(False)

        if (self._transport is not None and
            not self._paused and
            len(self._buffer) > 2*self._limit):
            try:
                self._transport.pause_reading()
            except NotImplementedError:
                # The transport can't be paused.
                # We'll just have to buffer all data.
                # Forget the transport so we don't keep trying.
                self._transport = None
            else:
                self._paused = True

    def _create_waiter(self, func_name):
        # StreamReader uses a future to link the protocol feed_data() method
        # to a read coroutine. Running two read coroutines at the same time
        # would have an unexpected behaviour. It would not possible to know
        # which coroutine would get the next data.
        if self._waiter is not None:
            raise RuntimeError('%s() called while another coroutine is '
                               'already waiting for incoming data' % func_name)
        return futures.Future(loop=self._loop)

    @tasks.coroutine
    def read_msg(self):
        if self._exception is not None:
            raise self._exception

        line = bytearray()
        not_enough = True

        while not_enough:
            while self._buffer and not_enough:
                ichar = self._buffer.find(b'\n')
                if ichar < 0:
                    line.extend(self._buffer)
                    self._buffer.clear()
                else:
                    ichar += 1
                    line.extend(self._buffer[:ichar])
                    del self._buffer[:ichar]
                    not_enough = False

                if len(line) > self._limit:
                    self._maybe_resume_transport()
                    raise ValueError('Line is too long')

            if self._eof:
                break

            if not_enough:
                self._waiter = self._create_waiter('readline')
                try:
                    yield from self._waiter
                finally:
                    self._waiter = None

        self._maybe_resume_transport()
        return bytes(line)

    @tasks.coroutine
    def read(self, n=-1):
        if self._exception is not None:
            raise self._exception

        if not n:
            return b''

        if n < 0:
            while not self._eof:
                self._waiter = self._create_waiter('read')
                try:
                    yield from self._waiter
                finally:
                    self._waiter = None
        else:
            if not self._buffer and not self._eof:
                self._waiter = self._create_waiter('read')
                try:
                    yield from self._waiter
                finally:
                    self._waiter = None

        if n < 0 or len(self._buffer) <= n:
            data = bytes(self._buffer)
            self._buffer.clear()
        else:
            # n > 0 and len(self._buffer) > n
            data = bytes(self._buffer[:n])
            del self._buffer[:n]

        self._maybe_resume_transport()
        return data
