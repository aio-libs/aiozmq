import asyncio
import asyncio.events
import errno
import struct
import sys
import threading
import weakref
import zmq

from collections import deque, namedtuple
from collections.abc import Iterable

from .interface import ZmqTransport, ZmqProtocol
from .log import logger
from .selector import ZmqSelector
from .util import _EndpointsSet


if sys.platform == "win32":
    from asyncio.windows_events import SelectorEventLoop
else:
    from asyncio.unix_events import SelectorEventLoop, SafeChildWatcher


__all__ = ["ZmqEventLoop", "ZmqEventLoopPolicy", "create_zmq_connection"]


SocketEvent = namedtuple("SocketEvent", "event value endpoint")


async def create_zmq_connection(
    protocol_factory, zmq_type, *, bind=None, connect=None, zmq_sock=None, loop=None
):
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
        ret = await loop.create_zmq_connection(
            protocol_factory, zmq_type, bind=bind, connect=connect, zmq_sock=zmq_sock
        )
        return ret

    try:
        if zmq_sock is None:
            zmq_sock = zmq.Context.instance().socket(zmq_type)
        elif zmq_sock.getsockopt(zmq.TYPE) != zmq_type:
            raise ValueError("Invalid zmq_sock type")
    except zmq.ZMQError as exc:
        raise OSError(exc.errno, exc.strerror) from exc

    protocol = protocol_factory()
    waiter = asyncio.Future()
    transport = _ZmqLooplessTransportImpl(loop, zmq_type, zmq_sock, protocol, waiter)
    await waiter

    try:
        if bind is not None:
            if isinstance(bind, str):
                bind = [bind]
            else:
                if not isinstance(bind, Iterable):
                    raise ValueError("bind should be str or iterable")
            for endpoint in bind:
                await transport.bind(endpoint)
        if connect is not None:
            if isinstance(connect, str):
                connect = [connect]
            else:
                if not isinstance(connect, Iterable):
                    raise ValueError("connect should be " "str or iterable")
            for endpoint in connect:
                await transport.connect(endpoint)
        return transport, protocol
    except OSError:
        # don't care if zmq_sock.close can raise exception
        # that should never happen
        zmq_sock.close()
        raise


class ZmqEventLoop(SelectorEventLoop):
    """ZeroMQ event loop.

    Follows asyncio.AbstractEventLoop specification, in addition implements
    create_zmq_connection method for working with ZeroMQ sockets.
    """

    def __init__(self, *, zmq_context=None):
        super().__init__(selector=ZmqSelector())
        if zmq_context is None:
            self._zmq_context = zmq.Context.instance()
        else:
            self._zmq_context = zmq_context
        self._zmq_sockets = weakref.WeakSet()

    def close(self):
        for zmq_sock in self._zmq_sockets:
            if not zmq_sock.closed:
                zmq_sock.close()
        super().close()

    async def create_zmq_connection(
        self, protocol_factory, zmq_type, *, bind=None, connect=None, zmq_sock=None
    ):
        """A coroutine which creates a ZeroMQ connection endpoint.

        See aiozmq.create_zmq_connection() coroutine for details.
        """

        try:
            if zmq_sock is None:
                zmq_sock = self._zmq_context.socket(zmq_type)
            elif zmq_sock.getsockopt(zmq.TYPE) != zmq_type:
                raise ValueError("Invalid zmq_sock type")
        except zmq.ZMQError as exc:
            raise OSError(exc.errno, exc.strerror) from exc

        protocol = protocol_factory()
        waiter = asyncio.Future(loop=self)
        transport = _ZmqTransportImpl(self, zmq_type, zmq_sock, protocol, waiter)
        await waiter

        try:
            if bind is not None:
                if isinstance(bind, str):
                    bind = [bind]
                else:
                    if not isinstance(bind, Iterable):
                        raise ValueError("bind should be str or iterable")
                for endpoint in bind:
                    await transport.bind(endpoint)
            if connect is not None:
                if isinstance(connect, str):
                    connect = [connect]
                else:
                    if not isinstance(connect, Iterable):
                        raise ValueError("connect should be str or iterable")
                for endpoint in connect:
                    await transport.connect(endpoint)
            self._zmq_sockets.add(zmq_sock)
            return transport, protocol
        except OSError:
            # don't care if zmq_sock.close can raise exception
            # that should never happen
            zmq_sock.close()
            raise


class _ZmqEventProtocol(ZmqProtocol):
    """This protocol is used internally by aiozmq to receive messages
    from a socket event monitor socket. This protocol decodes each event
    message into a namedtuple and then passes them through to the
    protocol running the socket that is being monitored via the
    ZmqProtocol.event_received method.

    This design simplifies the API visible to the developer at the cost
    of adding some internal complexity - a hidden protocol that transfers
    events from the monitor protocol to the monitored socket's protocol.
    """

    def __init__(self, loop, main_protocol):
        self._protocol = main_protocol
        self.wait_ready = asyncio.Future()
        self.wait_closed = asyncio.Future()

    def connection_made(self, transport):
        self.transport = transport
        self.wait_ready.set_result(True)

    def connection_lost(self, exc):
        self.wait_closed.set_result(exc)

    def msg_received(self, data):
        if len(data) != 2 or len(data[0]) != 6:
            raise RuntimeError("Invalid event message format: {}".format(data))
        event, value = struct.unpack("=hi", data[0])
        endpoint = data[1].decode()
        self.event_received(SocketEvent(event, value, endpoint))

    def event_received(self, evt):
        self._protocol.event_received(evt)


class _BaseTransport(ZmqTransport):

    LOG_THRESHOLD_FOR_CONNLOST_WRITES = 5
    ZMQ_TYPES = {
        getattr(zmq, name): name
        for name in (
            "PUB",
            "SUB",
            "REP",
            "REQ",
            "PUSH",
            "PULL",
            "DEALER",
            "ROUTER",
            "XPUB",
            "XSUB",
            "PAIR",
            "STREAM",
        )
        if hasattr(zmq, name)
    }

    def __init__(self, loop, zmq_type, zmq_sock, protocol):
        super().__init__(None)
        self._protocol_paused = False
        self._set_write_buffer_limits()
        self._extra["zmq_socket"] = zmq_sock
        self._extra["zmq_type"] = zmq_type
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
        self._paused = False
        self._conn_lost = 0
        self._monitor = None

    def __repr__(self):
        info = [
            "ZmqTransport",
            "sock={}".format(self._zmq_sock),
            "type={}".format(self.ZMQ_TYPES[self._zmq_type]),
        ]
        try:
            events = self._zmq_sock.getsockopt(zmq.EVENTS)
            if events & zmq.POLLIN:
                info.append("read=polling")
            else:
                info.append("read=idle")
            if events & zmq.POLLOUT:
                state = "polling"
            else:
                state = "idle"
            bufsize = self.get_write_buffer_size()
            info.append("write=<{}, bufsize={}>".format(state, bufsize))
        except zmq.ZMQError:
            pass
        return "<{}>".format(" ".join(info))

    def write(self, data):
        if not data:
            return
        for part in data:
            if not isinstance(part, (bytes, bytearray, memoryview)):
                raise TypeError(
                    "data argument must be iterable of " "byte-ish (%r)" % data
                )
        data_len = sum(len(part) for part in data)

        if self._conn_lost:
            if self._conn_lost >= self.LOG_THRESHOLD_FOR_CONNLOST_WRITES:
                logger.warning("write to closed ZMQ socket.")
            self._conn_lost += 1
            return

        if not self._buffer:
            try:
                if self._do_send(data):
                    return
            except Exception as exc:
                self._fatal_error(exc, "Fatal write error on zmq socket transport")
                return

        self._buffer.append((data_len, data))
        self._buffer_size += data_len
        self._maybe_pause_protocol()

    def can_write_eof(self):
        return False

    def abort(self):
        self._force_close(None)

    def _fatal_error(self, exc, message="Fatal error on transport"):
        # Should be called from exception handler only.
        self._loop.call_exception_handler(
            {
                "message": message,
                "exception": exc,
                "transport": self,
                "protocol": self._protocol,
            }
        )
        self._force_close(exc)

    def _call_connection_lost(self, exc):
        try:
            self._protocol.connection_lost(exc)
        finally:
            if not self._zmq_sock.closed:
                self._zmq_sock.close()
            self._zmq_sock = None
            self._protocol = None
            self._loop = None

    def _maybe_pause_protocol(self):
        size = self.get_write_buffer_size()
        if size <= self._high_water:
            return
        if not self._protocol_paused:
            self._protocol_paused = True
            try:
                self._protocol.pause_writing()
            except Exception as exc:
                self._loop.call_exception_handler(
                    {
                        "message": "protocol.pause_writing() failed",
                        "exception": exc,
                        "transport": self,
                        "protocol": self._protocol,
                    }
                )

    def _maybe_resume_protocol(self):
        if self._protocol_paused and self.get_write_buffer_size() <= self._low_water:
            self._protocol_paused = False
            try:
                self._protocol.resume_writing()
            except Exception as exc:
                self._loop.call_exception_handler(
                    {
                        "message": "protocol.resume_writing() failed",
                        "exception": exc,
                        "transport": self,
                        "protocol": self._protocol,
                    }
                )

    def _set_write_buffer_limits(self, high=None, low=None):
        if high is None:
            if low is None:
                high = 64 * 1024
            else:
                high = 4 * low
        if low is None:
            low = high // 4
        if not high >= low >= 0:
            raise ValueError("high (%r) must be >= low (%r) must be >= 0" % (high, low))
        self._high_water = high
        self._low_water = low

    def get_write_buffer_limits(self):
        return (self._low_water, self._high_water)

    def set_write_buffer_limits(self, high=None, low=None):
        self._set_write_buffer_limits(high=high, low=low)
        self._maybe_pause_protocol()

    def pause_reading(self):
        if self._closing:
            raise RuntimeError("Cannot pause_reading() when closing")
        if self._paused:
            raise RuntimeError("Already paused")
        self._paused = True
        self._do_pause_reading()

    def resume_reading(self):
        if not self._paused:
            raise RuntimeError("Not paused")
        self._paused = False
        if self._closing:
            return
        self._do_resume_reading()

    def getsockopt(self, option):
        while True:
            try:
                ret = self._zmq_sock.getsockopt(option)
                if option == zmq.LAST_ENDPOINT:
                    ret = ret.decode("utf-8").rstrip("\x00")
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
        fut = asyncio.Future(loop=self._loop)
        try:
            if not isinstance(endpoint, str):
                raise TypeError("endpoint should be str, got {!r}".format(endpoint))
            try:
                self._zmq_sock.bind(endpoint)
                real_endpoint = self.getsockopt(zmq.LAST_ENDPOINT)
            except zmq.ZMQError as exc:
                raise OSError(exc.errno, exc.strerror) from exc
        except Exception as exc:
            fut.set_exception(exc)
        else:
            self._bindings.add(real_endpoint)
            fut.set_result(real_endpoint)
        return fut

    def unbind(self, endpoint):
        fut = asyncio.Future(loop=self._loop)
        try:
            if not isinstance(endpoint, str):
                raise TypeError("endpoint should be str, got {!r}".format(endpoint))
            try:
                self._zmq_sock.unbind(endpoint)
            except zmq.ZMQError as exc:
                raise OSError(exc.errno, exc.strerror) from exc
            else:
                self._bindings.discard(endpoint)
        except Exception as exc:
            fut.set_exception(exc)
        else:
            fut.set_result(None)
        return fut

    def bindings(self):
        return _EndpointsSet(self._bindings)

    def connect(self, endpoint):
        fut = asyncio.Future(loop=self._loop)
        try:
            if not isinstance(endpoint, str):
                raise TypeError("endpoint should be str, got {!r}".format(endpoint))
            try:
                self._zmq_sock.connect(endpoint)
            except zmq.ZMQError as exc:
                raise OSError(exc.errno, exc.strerror) from exc
        except Exception as exc:
            fut.set_exception(exc)
        else:
            self._connections.add(endpoint)
            fut.set_result(endpoint)
        return fut

    def disconnect(self, endpoint):
        fut = asyncio.Future(loop=self._loop)
        try:
            if not isinstance(endpoint, str):
                raise TypeError("endpoint should be str, got {!r}".format(endpoint))
            try:
                self._zmq_sock.disconnect(endpoint)
            except zmq.ZMQError as exc:
                raise OSError(exc.errno, exc.strerror) from exc
        except Exception as exc:
            fut.set_exception(exc)
        else:
            self._connections.discard(endpoint)
            fut.set_result(None)
        return fut

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

    async def enable_monitor(self, events=None):

        # The standard approach of binding and then connecting does not
        # work in this specific case. The event loop does not properly
        # detect messages on the inproc transport which means that event
        # messages get missed.
        # pyzmq's 'get_monitor_socket' method can't be used because this
        # performs the actions in the wrong order for use with an event
        # loop.
        # For more information on this issue see:
        # http://lists.zeromq.org/pipermail/zeromq-dev/2015-July/029181.html

        if zmq.zmq_version_info() < (4,) or zmq.pyzmq_version_info() < (14, 4):
            raise NotImplementedError(
                "Socket monitor requires libzmq >= 4 and pyzmq >= 14.4, "
                "have libzmq:{}, pyzmq:{}".format(
                    zmq.zmq_version(), zmq.pyzmq_version()
                )
            )

        if self._monitor is None:
            addr = "inproc://monitor.s-{}".format(self._zmq_sock.FD)
            events = events or zmq.EVENT_ALL
            _, self._monitor = await create_zmq_connection(
                lambda: _ZmqEventProtocol(self._loop, self._protocol),
                zmq.PAIR,
                connect=addr,
                loop=self._loop,
            )
            # bind must come after connect
            self._zmq_sock.monitor(addr, events)
            await self._monitor.wait_ready

    async def disable_monitor(self):
        self._disable_monitor()

    def _disable_monitor(self):
        if self._monitor:
            self._zmq_sock.disable_monitor()
            self._monitor.transport.close()
            self._monitor = None


class _ZmqTransportImpl(_BaseTransport):
    def __init__(self, loop, zmq_type, zmq_sock, protocol, waiter=None):
        super().__init__(loop, zmq_type, zmq_sock, protocol)

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
            self._fatal_error(exc, "Fatal read error on zmq socket transport")
        else:
            self._protocol.msg_received(data)

    def _do_send(self, data):
        try:
            self._zmq_sock.send_multipart(data, zmq.DONTWAIT)
            return True
        except zmq.ZMQError as exc:
            if exc.errno in (errno.EAGAIN, errno.EINTR):
                self._loop.add_writer(self._zmq_sock, self._write_ready)
                return False
            else:
                raise OSError(exc.errno, exc.strerror) from exc

    def _write_ready(self):
        assert self._buffer, "Data should not be empty"

        try:
            try:
                self._zmq_sock.send_multipart(self._buffer[0][1], zmq.DONTWAIT)
            except zmq.ZMQError as exc:
                if exc.errno in (errno.EAGAIN, errno.EINTR):
                    return
                else:
                    raise OSError(exc.errno, exc.strerror) from exc
        except Exception as exc:
            self._fatal_error(exc, "Fatal write error on zmq socket transport")
        else:
            sent_len, sent_data = self._buffer.popleft()
            self._buffer_size -= sent_len

            self._maybe_resume_protocol()

            if not self._buffer:
                self._loop.remove_writer(self._zmq_sock)
                if self._closing:
                    self._call_connection_lost(None)

    def close(self):
        if self._closing:
            return
        self._closing = True
        if self._monitor:
            self._disable_monitor()
        if not self._paused:
            self._loop.remove_reader(self._zmq_sock)
        if not self._buffer:
            self._conn_lost += 1
            self._loop.call_soon(self._call_connection_lost, None)

    def _force_close(self, exc):
        if self._conn_lost:
            return
        if self._monitor:
            self._disable_monitor()
        if self._buffer:
            self._buffer.clear()
            self._buffer_size = 0
            self._loop.remove_writer(self._zmq_sock)
        if not self._closing:
            self._closing = True
            if not self._paused:
                if self._zmq_sock.closed:
                    self._loop._remove_reader(self._zmq_sock)
                else:
                    self._loop.remove_reader(self._zmq_sock)
        self._conn_lost += 1
        self._loop.call_soon(self._call_connection_lost, exc)

    def _do_pause_reading(self):
        self._loop.remove_reader(self._zmq_sock)

    def _do_resume_reading(self):
        self._loop.add_reader(self._zmq_sock, self._read_ready)


class _ZmqLooplessTransportImpl(_BaseTransport):
    def __init__(self, loop, zmq_type, zmq_sock, protocol, waiter):
        super().__init__(loop, zmq_type, zmq_sock, protocol)

        fd = zmq_sock.getsockopt(zmq.FD)
        self._fd = fd
        self._loop.add_reader(fd, self._read_ready)

        self._loop.call_soon(self._protocol.connection_made, self)
        self._loop.call_soon(waiter.set_result, None)
        self._soon_call = None

    def _read_ready(self):
        self._soon_call = None
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
                self._soon_call = self._loop.call_soon(self._read_ready)

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
            self._fatal_error(exc, "Fatal read error on zmq socket transport")
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
                    if self._soon_call is None:
                        self._soon_call = self._loop.call_soon(self._read_ready)
                    return
                else:
                    raise OSError(exc.errno, exc.strerror) from exc
        except Exception as exc:
            self._fatal_error(exc, "Fatal write error on zmq socket transport")
        else:
            sent_len, sent_data = self._buffer.popleft()
            self._buffer_size -= sent_len

            self._maybe_resume_protocol()

            if not self._buffer and self._closing:
                self._loop.remove_reader(self._fd)
                self._call_connection_lost(None)
            else:
                if self._soon_call is None:
                    self._soon_call = self._loop.call_soon(self._read_ready)

    def _do_send(self, data):
        try:
            self._zmq_sock.send_multipart(data, zmq.DONTWAIT)
            if self._soon_call is None:
                self._soon_call = self._loop.call_soon(self._read_ready)
            return True
        except zmq.ZMQError as exc:
            if exc.errno not in (errno.EAGAIN, errno.EINTR):
                raise OSError(exc.errno, exc.strerror) from exc
            else:
                if self._soon_call is None:
                    self._soon_call = self._loop.call_soon(self._read_ready)
                return False

    def close(self):
        if self._closing:
            return
        self._closing = True
        if self._monitor:
            self._disable_monitor()
        if not self._buffer:
            self._conn_lost += 1
            if not self._paused:
                self._loop.remove_reader(self._fd)
            self._loop.call_soon(self._call_connection_lost, None)

    def _force_close(self, exc):
        if self._conn_lost:
            return
        if self._monitor:
            self._disable_monitor()
        if self._buffer:
            self._buffer.clear()
            self._buffer_size = 0
        self._closing = True
        self._loop.remove_reader(self._fd)
        self._conn_lost += 1
        self._loop.call_soon(self._call_connection_lost, exc)

    def _do_pause_reading(self):
        pass

    def _do_resume_reading(self):
        self._read_ready()

    def _call_connection_lost(self, exc):
        try:
            super()._call_connection_lost(exc)
        finally:
            self._soon_call = None


class ZmqEventLoopPolicy(asyncio.AbstractEventLoopPolicy):
    """ZeroMQ policy implementation for accessing the event loop.

    In this policy, each thread has its own event loop.  However, we
    only automatically create an event loop by default for the main
    thread; other threads by default have no event loop.
    """

    class _Local(threading.local):
        _loop = None
        _set_called = False

    def __init__(self):
        self._local = self._Local()
        self._watcher = None

    def get_event_loop(self):
        """Get the event loop.

        If current thread is the main thread and there are no
        registered event loop for current thread then the call creates
        new event loop and registers it.

        Return an instance of ZmqEventLoop.
        Raise RuntimeError if there is no registered event loop
        for current thread.
        """
        if (
            self._local._loop is None
            and not self._local._set_called
            and isinstance(threading.current_thread(), threading._MainThread)
        ):
            self.set_event_loop(self.new_event_loop())
        assert self._local._loop is not None, (
            "There is no current event loop in thread %r."
            % threading.current_thread().name
        )
        return self._local._loop

    def new_event_loop(self):
        """Create a new event loop.

        You must call set_event_loop() to make this the current event
        loop.
        """
        return ZmqEventLoop()

    def set_event_loop(self, loop):
        """Set the event loop.

        As a side effect, if a child watcher was set before, then calling
        .set_event_loop() from the main thread will call .attach_loop(loop) on
        the child watcher.
        """

        self._local._set_called = True
        assert loop is None or isinstance(
            loop, asyncio.AbstractEventLoop
        ), "loop should be None or AbstractEventLoop instance"
        self._local._loop = loop

        if self._watcher is not None and isinstance(
            threading.current_thread(), threading._MainThread
        ):
            self._watcher.attach_loop(loop)

    if sys.platform != "win32":

        def _init_watcher(self):
            with asyncio.events._lock:
                if self._watcher is None:  # pragma: no branch
                    self._watcher = SafeChildWatcher()
                    if isinstance(threading.current_thread(), threading._MainThread):
                        self._watcher.attach_loop(self._local._loop)

        def get_child_watcher(self):
            """Get the child watcher.

            If not yet set, a SafeChildWatcher object is automatically created.
            """
            if self._watcher is None:
                self._init_watcher()

            return self._watcher

        def set_child_watcher(self, watcher):
            """Set the child watcher."""

            assert watcher is None or isinstance(
                watcher, asyncio.AbstractChildWatcher
            ), "watcher should be None or AbstractChildWatcher instance"

            if self._watcher is not None:
                self._watcher.close()

            self._watcher = watcher
