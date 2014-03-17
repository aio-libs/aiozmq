import asyncio
import collections
import zmq

from asyncio.unix_events import SelectorEventLoop, DefaultEventLoopPolicy
from .selector import ZmqSelector
from .interface import ZmqTransport

from collections import Iterable

__all__ = ['ZmqEventLoop', 'ZmqEventLoopPolicy']


class ZmqEventLoop(SelectorEventLoop):

    def __init__(self, *, io_threads=1):
        super().__init__(selector=ZmqSelector())
        self._zmq_context = zmq.Context(io_threads)

    def close(self):
        super().close()
        self._zmq_context.destroy()

    @asyncio.coroutine
    def create_zmq_connection(self, protocol_factory, zmq_type, *,
                               bind=None, connect=None, zmq_sock=None):
        if 1 != sum(
                1 if i is not None else 0 for i in [zmq_sock, bind, connect]):
            raise ValueError(
                "the only bind, connect or zmq_sock should be specified "
                "at the same time", bind, connect, zmq_sock)
        if zmq_sock is None:
            zmq_sock = self._zmq_context.socket(zmq_type)
            if bind is not None:
                if isinstance(bind, str):
                    bind = [bind]
                else:
                    if not isinstance(bind, Iterable):
                        raise ValueError('bind should be str or iterable')
                for endpoint in bind:
                    zmq_sock.bind(endpoint)
            elif connect is not None:
                if isinstance(connect, str):
                    connect = [connect]
                else:
                    if not isinstance(connect, Iterable):
                        raise ValueError('connect should be str or iterable')
                for endpoint in connect:
                    zmq_sock.connect(endpoint)
        else:
            if zmq_sock.getsockopt(zmq.TYPE) != zmq_type:
                raise ValueError('Invalid zmq_sock type')

        protocol = protocol_factory()
        waiter = asyncio.Future(loop=self)
        transport = _ZmqTransportImpl(self, zmq_sock, protocol, waiter)
        yield from waiter
        return transport, protocol


class _ZmqTransportImpl(ZmqTransport):

    def __init__(self, loop, zmq_sock, protocol, waiter):
        super().__init__()
        self._extra['zmq_socket'] = zmq_sock
        self._loop = loop
        self._zmq_sock = zmq_sock
        self._protocol = protocol
        self._closing = False
        self._buffer = collections.deque()
        self._loop.add_reader(self._zmq_sock, self._read_ready)
        self._loop.call_soon(self._protocol.connection_made, self)
        if waiter is not None:
            self._loop.call_soon(waiter.set_result, None)

    def _read_ready(self):
        try:
            data = self._zmq_sock.recv_multipart(zmq.NOBLOCK)
        except zmq.ZMQError as exc:
            if exc.errno in (errno.EAGAIN, errno.EINTR):
                pass
            else:
                self._fatal_error(exc,
                                  'Fatal read error on zmq socket transport')
        except Exception as exc:
            self._fatal_error(exc, 'Fatal read error on zmq socket transport')
        else:
            self._protocol.msg_received(*data)

    def write(self, data, *multipart):
        if multipart:
            data = (data,) + multipart
        else:
            data = (data,)
        for part in data:
            if not isinstance(part, (bytes, bytearray, memoryview)):
                raise TypeError('data argument must be byte-ish (%r)' %
                                type(part))
        if not data:
            return

        if not self._buffer:
            try:
                try:
                    self._zmq_sock.send_multipart(data)
                    return
                except ZMQError as exc:
                    if exc.errno in (errno.EAGAIN, errno.EINTR):
                        pass
                    else:
                        raise
            except Exception as exc:
                self._fatal_error(exc,
                                  'Fatal write error on zmq socket transport')
                return

        self._buffer.append(data)

    def _write_ready(self):
        assert self._buffer, 'Data should not be empty'

        while self._buffer:
            try:
                try:
                    self._zmq_sock.send_multipart(self._buffer[0])
                except ZMQError as exc:
                    if exc.errno in (errno.EAGAIN, errno.EINTR):
                        return
                    else:
                        raise
            except Exception as exc:
                self._loop.remove_writer(self._zmq_sock)
                self._buffer.clear()
                self._fatal_error(exc,
                                  'Fatal write error on zmq socket transport')
                return
            else:
                self._buffer.popleft()

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


class ZmqEventLoopPolicy(DefaultEventLoopPolicy):

    _loop_factory = ZmqEventLoop()
