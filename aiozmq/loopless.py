import asyncio
import errno
import zmq

from collections import Iterable

from .core import ZmqEventLoop, _BaseTransport


@asyncio.coroutine
def create_zmq_connection(protocol_factory, zmq_type, *,
                          bind=None, connect=None, zmq_sock=None, loop=None):
    """A coroutine which creates a ZeroMQ connection endpoint.

    The return value is a pair of (transport, protocol),
    where transport support ZmqTransport interface.

    protocol_factory should instantiate object with ZmqProtocol interface.

    zmq_type is type of ZeroMQ socket (zmq.REQ, zmq.REP, zmq.PUB, zmq.SUB,
    zmq.PAIR, zmq.DEALER, zmq.ROUTER, zmq.PULL, zmq.PUSH, etc.)

    bind is string or iterable of strings that specifies enpoints.
    Every endpoint creates ending for acceptin connections
    and binds it to the transport.
    Other side should use connect parameter to connect to this transport.
    See http://api.zeromq.org/master:zmq-bind for details.

    connect is string or iterable of strings that specifies enpoints.
    Every endpoint connects transport to specified transport.
    Other side should use bind parameter to wait for incoming connections.
    See http://api.zeromq.org/master:zmq-connect for details.

    endpoint is a string consisting of two parts as follows:
    transport://address.

    The transport part specifies the underlying transport protocol to use.
    The meaning of the address part is specific to the underlying
    transport protocol selected.

    The following transports are defined:

    inproc - local in-process (inter-thread) communication transport,
    see http://api.zeromq.org/master:zmq-inproc.

    ipc - local inter-process communication transport,
    see http://api.zeromq.org/master:zmq-ipc

    tcp - unicast transport using TCP,
    see http://api.zeromq.org/master:zmq_tcp

    pgm, epgm - reliable multicast transport using PGM,
    see http://api.zeromq.org/master:zmq_pgm

    zmq_sock is a zmq.Socket instance to use preexisting object
    with created transport.
    """
    if loop is None:
        loop = asyncio.get_event_loop()
    if isinstance(loop, ZmqEventLoop):
        ret = yield from loop.create_zmq_connection(protocol_factory,
                                                    zmq_type,
                                                    bind=bind,
                                                    connect=connect,
                                                    zmq_sock=zmq_sock)
        return ret

    try:
        if zmq_sock is None:
            zmq_sock = zmq.Context().instance().socket(zmq_type)
        elif zmq_sock.getsockopt(zmq.TYPE) != zmq_type:
            raise ValueError('Invalid zmq_sock type')
    except zmq.ZMQError as exc:
        raise OSError(exc.errno, exc.strerror) from exc

    protocol = protocol_factory()
    waiter = asyncio.Future(loop=loop)
    transport = _ZmqLooplessTransportImpl(loop, zmq_type,
                                          zmq_sock, protocol, waiter)
    yield from waiter

    try:
        if bind is not None:
            if isinstance(bind, str):
                bind = [bind]
            else:
                if not isinstance(bind, Iterable):
                    raise ValueError('bind should be str or iterable')
            for endpoint in bind:
                yield from transport.bind(endpoint)
        if connect is not None:
            if isinstance(connect, str):
                connect = [connect]
            else:
                if not isinstance(connect, Iterable):
                    raise ValueError('connect should be '
                                     'str or iterable')
            for endpoint in connect:
                yield from transport.connect(endpoint)
        return transport, protocol
    except OSError:
        # don't care if zmq_sock.close can raise exception
        # that should never happen
        zmq_sock.close()
        raise


class _ZmqLooplessTransportImpl(_BaseTransport):

    def __init__(self, loop, zmq_type, zmq_sock, protocol, waiter):
        super().__init__(loop, zmq_type, zmq_sock, protocol)

        fd = zmq_sock.getsockopt(zmq.FD)
        self._fd = fd
        self._loop.add_reader(fd, self._read_ready)

        self._loop.call_soon(self._protocol.connection_made, self)
        self._loop.call_soon(waiter.set_result, None)

    def _read_ready(self):
        if self._zmq_sock is None:
            return
        events = self._zmq_sock.getsockopt(zmq.EVENTS)
        try_again = False
        if not self._paused and events & zmq.POLLIN:
            self._do_read()
            try_again = True
        if self._buffer and events & zmq.POLLOUT:
            self._do_write()
            if not try_again:
                try_again = bool(self._buffer)
        if try_again:
            postevents = self._zmq_sock.getsockopt(zmq.EVENTS)
            if postevents & zmq.POLLIN:
                schedule = True
            elif self._buffer and postevents & zmq.POLLOUT:
                schedule = True
            else:
                schedule = False
            if schedule:
                self._loop.call_soon(self._read_ready)

    def _do_read(self):
        try:
            try:
                data = self._zmq_sock.recv_multipart(zmq.NOBLOCK)
            except zmq.ZMQError as exc:
                if exc.errno in (errno.EAGAIN, errno.EINTR):
                    return
                else:
                    raise OSError(exc.errno, exc.strerror) from exc
        except Exception as exc:
            self._fatal_error(exc, 'Fatal read error on zmq socket transport')
        else:
            self._protocol.msg_received(data)

    def _do_write(self):
        if not self._buffer:
            return
        try:
            try:
                self._zmq_sock.send_multipart(self._buffer[0][1], zmq.DONTWAIT)
            except zmq.ZMQError as exc:
                if exc.errno in (errno.EAGAIN, errno.EINTR):
                    return
                else:
                    raise OSError(exc.errno, exc.strerror) from exc
        except Exception as exc:
            self._fatal_error(exc,
                              'Fatal write error on zmq socket transport')
        else:
            sent_len, sent_data = self._buffer.popleft()
            self._buffer_size -= sent_len

            self._maybe_resume_protocol()

            if not self._buffer and self._closing:
                self._loop.remove_reader(self._fd)
                self._call_connection_lost(None)

    def _do_send(self, data):
        try:
            self._zmq_sock.send_multipart(data, zmq.DONTWAIT)
            return True
        except zmq.ZMQError as exc:
            if exc.errno not in (errno.EAGAIN, errno.EINTR):
                raise OSError(exc.errno, exc.strerror) from exc
            else:
                return False

    def close(self):
        if self._closing:
            return
        self._closing = True
        if not self._buffer:
            self._conn_lost += 1
            if not self._paused:
                self._loop.remove_reader(self._fd)
            self._loop.call_soon(self._call_connection_lost, None)

    def _force_close(self, exc):
        if self._conn_lost:
            return
        if self._buffer:
            self._buffer.clear()
            self._buffer_size = 0
        if not self._closing:
            self._closing = True
        self._loop.remove_reader(self._fd)
        self._conn_lost += 1
        self._loop.call_soon(self._call_connection_lost, exc)

    def pause_reading(self):
        if self._closing:
            raise RuntimeError('Cannot pause_reading() when closing')
        if self._paused:
            raise RuntimeError('Already paused')
        self._paused = True

    def resume_reading(self):
        if not self._paused:
            raise RuntimeError('Not paused')
        self._paused = False
        if self._closing:
            return
        self._read_ready()
