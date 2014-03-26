import asyncio
import asyncio.events
import errno
import re
import threading
import zmq

from asyncio.unix_events import SelectorEventLoop, SafeChildWatcher
from asyncio.transports import _FlowControlMixin
from collections import deque, Iterable, Set
from ipaddress import ip_address

from .selector import ZmqSelector
from .interface import ZmqTransport


__all__ = ['ZmqEventLoop', 'ZmqEventLoopPolicy']


class ZmqEventLoop(SelectorEventLoop):
    """ZeroMQ event loop.

    Follows asyncio.AbstractEventLoop specification, in addition implements
    create_zmq_connection method for working with ZeroMQ sockets.
    """

    def __init__(self, *, io_threads=1):
        super().__init__(selector=ZmqSelector())
        self._zmq_context = zmq.Context(io_threads)

    def close(self):
        super().close()
        self._zmq_context.destroy()

    @asyncio.coroutine
    def create_zmq_connection(self, protocol_factory, zmq_type, *,
                              bind=None, connect=None, zmq_sock=None):
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

        The only one of bind, connect or zmq_sock should be specified.
        """
        if 1 != sum(
                1 if i is not None else 0 for i in [zmq_sock, bind, connect]):
            raise ValueError(
                "the only bind, connect or zmq_sock should be specified "
                "at the same time", bind, connect, zmq_sock)

        try:
            if zmq_sock is None:
                zmq_sock = self._zmq_context.socket(zmq_type)
            # TODO: process EINTR
            elif zmq_sock.getsockopt(zmq.TYPE) != zmq_type:
                raise ValueError('Invalid zmq_sock type')
        except zmq.ZMQError as exc:
            raise OSError(exc.errno, exc.strerror) from exc

        protocol = protocol_factory()
        waiter = asyncio.Future(loop=self)
        transport = _ZmqTransportImpl(self, zmq_type,
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
                    transport.bind(endpoint)
            elif connect is not None:
                if isinstance(connect, str):
                    connect = [connect]
                else:
                    if not isinstance(connect, Iterable):
                        raise ValueError('connect should be '
                                         'str or iterable')
                for endpoint in connect:
                    transport.connect(endpoint)

            return transport, protocol
        except OSError:
            # don't care if zmq_sock.close can raise exception
            # that should never happen
            zmq_sock.close()
            raise


class _EndpointsSet(Set):

    __slots__ = ('_collection',)

    def __init__(self, collection):
        self._collection = collection

    def __len__(self):
        return len(self._collection)

    def __contains__(self, endpoint):
        return endpoint in self._collection

    def __iter__(self):
        return iter(self._collection)

    def __repr__(self):
        return '{' + ', '.join(sorted(self._collection)) + '}'

    __str__ = __repr__


class _ZmqTransportImpl(ZmqTransport, _FlowControlMixin):

    _TCP_RE = re.compile('^tcp://(.+):(\d+)|\*$')

    def __init__(self, loop, zmq_type, zmq_sock, protocol, waiter=None):
        super().__init__(None)
        self._extra['zmq_socket'] = zmq_sock
        self._loop = loop
        self._zmq_sock = zmq_sock
        self._zmq_type = zmq_type
        self._protocol = protocol
        self._closing = False
        self._buffer = deque()
        self._buffer_size = 0
        self._bindings = set()
        self._connections = set()
        self._subscriptions = set()

        self._loop.add_reader(self._zmq_sock, self._read_ready)
        self._loop.call_soon(self._protocol.connection_made, self)
        if waiter is not None:
            self._loop.call_soon(waiter.set_result, None)

    def _read_ready(self):
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
            self._protocol.msg_received(tuple(data))

    def write(self, data):
        if not data:
            return
        for part in data:
            if not isinstance(part, (bytes, bytearray, memoryview)):
                raise TypeError('data argument must be iterable of '
                                'byte-ish (%r)' % data)
        data_len = sum(len(part) for part in data)
        if not data_len:
            return

        if not self._buffer:
            try:
                try:
                    self._zmq_sock.send_multipart(data, zmq.DONTWAIT)
                    return
                except zmq.ZMQError as exc:
                    if exc.errno in (errno.EAGAIN, errno.EINTR):
                        self._loop.add_writer(self._zmq_sock,
                                              self._write_ready)
                    else:
                        raise OSError(exc.errno, exc.strerror) from exc
            except Exception as exc:
                self._fatal_error(exc,
                                  'Fatal write error on zmq socket transport')
                return

        self._buffer.append(data)
        self._buffer_size += data_len
        self._maybe_pause_protocol()

    def _write_ready(self):
        assert self._buffer, 'Data should not be empty'

        try:
            try:
                self._zmq_sock.send_multipart(self._buffer[0], zmq.DONTWAIT)
            except zmq.ZMQError as exc:
                if exc.errno in (errno.EAGAIN, errno.EINTR):
                    pass
                else:
                    raise OSError(exc.errno, exc.strerror) from exc
        except Exception as exc:
            self._loop.remove_writer(self._zmq_sock)
            self._buffer.clear()
            self._buffer_size = 0
            self._fatal_error(exc,
                              'Fatal write error on zmq socket transport')
        else:
            sent_data = self._buffer.popleft()
            self._buffer_size -= sum(len(part) for part in sent_data)

            self._maybe_resume_protocol()

            if not self._buffer:
                self._loop.remove_writer(self._zmq_sock)
                if self._closing:
                    self._call_connection_lost(None)

    def can_write_eof(self):
        return False

    def abort(self):
        self._force_close(None)

    def close(self):
        if self._closing:
            return
        self._closing = True
        self._loop.remove_reader(self._zmq_sock)
        if not self._buffer:
            self._loop.call_soon(self._call_connection_lost, None)

    def _fatal_error(self, exc, message='Fatal error on transport'):
        # Should be called from exception handler only.
        self._loop.call_exception_handler({
            'message': message,
            'exception': exc,
            'transport': self,
            'protocol': self._protocol,
            })
        self._force_close(exc)

    def _force_close(self, exc):
        if self._buffer:
            self._buffer.clear()
            self._buffer_size = 0
            self._loop.remove_writer(self._zmq_sock)
        if not self._closing:
            self._closing = True
            self._loop.remove_reader(self._zmq_sock)
        self._loop.call_soon(self._call_connection_lost, exc)

    def _call_connection_lost(self, exc):
        try:
            self._protocol.connection_lost(exc)
        finally:
            self._zmq_sock.close()
            self._zmq_sock = None
            self._protocol = None
            self._loop = None

    def getsockopt(self, option):
        while True:
            try:
                ret = self._zmq_sock.getsockopt(option)
                if option == zmq.LAST_ENDPOINT:
                    ret = ret.decode('utf-8').rstrip('\x00')
                return ret
            except zmq.ZMQError as exc:
                if exc.errno == errno.EINTR:
                    continue
                raise OSError(exc.errno, exc.strerror) from exc

    def setsockopt(self, option, value):
        while True:
            try:
                self._zmq_sock.setsockopt(option, value)
                if option == zmq.SUBSCRIBE:
                    self._subscriptions.add(value)
                elif option == zmq.UNSUBSCRIBE:
                    self._subscriptions.discard(value)
                return
            except zmq.ZMQError as exc:
                if exc.errno == errno.EINTR:
                    continue
                raise OSError(exc.errno, exc.strerror) from exc

    def get_write_buffer_size(self):
        return self._buffer_size

    def bind(self, endpoint):
        while True:
            try:
                self._zmq_sock.bind(endpoint)
                real_endpoint = self.getsockopt(zmq.LAST_ENDPOINT)
            except zmq.ZMQError as exc:
                if exc.errno == errno.EINTR:
                    continue
                raise OSError(exc.errno, exc.strerror) from exc
            else:
                self._bindings.add(real_endpoint)
                return real_endpoint

    def unbind(self, endpoint):
        while True:
            try:
                self._zmq_sock.unbind(endpoint)
            except zmq.ZMQError as exc:
                if exc.errno == errno.EINTR:
                    continue
                raise OSError(exc.errno, exc.strerror) from exc
            else:
                self._bindings.discard(endpoint)
                return

    def bindings(self):
        return _EndpointsSet(self._bindings)

    def connect(self, endpoint):
        match = self._TCP_RE.match(endpoint)
        if match:
            ip_address(match.group(1))  # check for correct IPv4 or IPv6
        while True:
            try:
                self._zmq_sock.connect(endpoint)
            except zmq.ZMQError as exc:
                if exc.errno == errno.EINTR:
                    continue
                raise OSError(exc.errno, exc.strerror) from exc
            else:
                self._connections.add(endpoint)
                return endpoint

    def disconnect(self, endpoint):
        while True:
            try:
                self._zmq_sock.disconnect(endpoint)
            except zmq.ZMQError as exc:
                if exc.errno == errno.EINTR:
                    continue
                raise OSError(exc.errno, exc.strerror) from exc
            else:
                self._connections.discard(endpoint)
                return

    def connections(self):
        return _EndpointsSet(self._connections)

    def subscribe(self, value):
        if self._zmq_type != zmq.SUB:
            raise NotImplementedError("Not supported ZMQ socket type")
        if not isinstance(value, bytes):
            raise TypeError("value argument should be bytes")
        if value in self._subscriptions:
            return
        self.setsockopt(zmq.SUBSCRIBE, value)

    def unsubscribe(self, value):
        if self._zmq_type != zmq.SUB:
            raise NotImplementedError("Not supported ZMQ socket type")
        if not isinstance(value, bytes):
            raise TypeError("value argument should be bytes")
        self.setsockopt(zmq.UNSUBSCRIBE, value)

    def subscriptions(self):
        if self._zmq_type != zmq.SUB:
            raise NotImplementedError("Not supported ZMQ socket type")
        return _EndpointsSet(self._subscriptions)


class ZmqEventLoopPolicy(asyncio.AbstractEventLoopPolicy):
    """ZeroMQ policy implementation for accessing the event loop.

    In this policy, each thread has its own event loop.  However, we
    only automatically create an event loop by default for the main
    thread; other threads by default have no event loop.
    """

    class _Local(threading.local):
        _loop = None
        _set_called = False

    def __init__(self, *, io_threads=1):
        self._local = self._Local()
        self._watcher = None
        self._io_threads = io_threads

    def get_event_loop(self):
        """Get the event loop.

        If current thread is the main thread and there are no
        registered event loop for current thread then the call creates
        new event loop and registers it.

        Return an instance of ZmqEventLoop.
        Raise RuntimeError if there is no registered event loop
        for current thread.
        """
        if (self._local._loop is None and
                not self._local._set_called and
                isinstance(threading.current_thread(), threading._MainThread)):
            self.set_event_loop(self.new_event_loop())
        if self._local._loop is None:
            raise RuntimeError('There is no current event loop in thread %r.' %
                               threading.current_thread().name)
        return self._local._loop

    def new_event_loop(self):
        """Create a new event loop.

        You must call set_event_loop() to make this the current event
        loop.
        """
        return ZmqEventLoop(io_threads=self._io_threads)

    def _init_watcher(self):
        with asyncio.events._lock:
            if self._watcher is None:  # pragma: no branch
                self._watcher = SafeChildWatcher()
                if isinstance(threading.current_thread(),
                              threading._MainThread):
                    self._watcher.attach_loop(self._local._loop)

    def set_event_loop(self, loop):
        """Set the event loop.

        As a side effect, if a child watcher was set before, then calling
        .set_event_loop() from the main thread will call .attach_loop(loop) on
        the child watcher.
        """

        self._local._set_called = True
        if loop is not None and not isinstance(loop,
                                               asyncio.AbstractEventLoop):
            raise TypeError("loop should be None "
                            "or AbstractEventLoop instance")
        self._local._loop = loop

        if (self._watcher is not None and
                isinstance(threading.current_thread(), threading._MainThread)):
            self._watcher.attach_loop(loop)

    def get_child_watcher(self):
        """Get the child watcher.

        If not yet set, a SafeChildWatcher object is automatically created.
        """
        if self._watcher is None:
            self._init_watcher()

        return self._watcher

    def set_child_watcher(self, watcher):
        """Set the child watcher."""

        if (watcher is not None and
                not isinstance(watcher, asyncio.AbstractChildWatcher)):
            raise TypeError("watcher should be None or AbstractChildWatcher "
                            "instance")

        if self._watcher is not None:
            self._watcher.close()

        self._watcher = watcher
