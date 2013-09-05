"""Tulip compatibility with zeromq."""
__all__ = ['Socket', 'Context']

import collections
import functools
import pickle
import tulip
import zmq


class Socket(zmq.Socket):
    """Tulip's version of zmq.Socket"""

    _loop = None
    _sock_fd = None
    _buffer = None
    _send_exc = None

    def __init__(self, context, socket_type, *, loop=None):
        super().__init__(context, socket_type)

        if loop is None:
            loop = tulip.get_event_loop()

        self._loop = loop
        self._buffer = collections.deque()
        self._sock_fd = self.getsockopt(zmq.FD)
        self._send_exc = None

    def exception(self):
        return self._send_exc

    @tulip.coroutine
    def recv(self, flags=0, copy=True, track=False):
        if flags & zmq.NOBLOCK:
            return super().recv(flags, copy, track)

        # ensure the zmq.NOBLOCK flag is part of flags
        flags |= zmq.NOBLOCK

        # Attempt to complete this operation indefinitely
        try:
            return super().recv(flags, copy, track)
        except zmq.ZMQError as e:
            if e.errno != zmq.EAGAIN:
                raise

        # defer to the event loop until we're notified the socket is readable
        fut = tulip.Future(loop=self._loop)
        self._recv(fut, False, flags, copy, track)
        return (yield from fut)

    def _recv(self, fut, registered, *args):
        if registered:
            self._loop.remove_reader(self._sock_fd)
        if fut.cancelled():
            return

        try:
            data = super().recv(*args)
        except zmq.ZMQError as exc:
            if exc.errno != zmq.EAGAIN:
                fut.set_exception(exc)
                return
            self._loop.add_reader(self._sock_fd, self._recv, fut, True, *args)
        except Exception as exc:
            fut.set_exception(exc)
        else:
            fut.set_result(data)

    def send(self, data, flags=0, copy=True, track=False):
        assert isinstance(data, bytes), repr(data)
        if not data:
            return

        # fatal error
        if self._send_exc:
            raise self._send_exc

        if not self._buffer:
            # if we're given the NOBLOCK flag act as normal
            # and let the EAGAIN get raised
            if flags & zmq.NOBLOCK:
                super().send(data, flags, copy, track)

            # ensure the zmq.NOBLOCK flag is part of flags
            flags |= zmq.NOBLOCK

            # Attempt to complete this operation indefinitely
            try:
                super().send(data, flags, copy, track)
            except zmq.ZMQError as e:
                if e.errno != zmq.EAGAIN:
                    raise
            else:
                return

            self._loop.add_writer(self._sock_fd, self._send_ready)

        self._buffer.append((data, flags, copy, track))

    def _send_ready(self):
        while self._buffer:
            args = self._buffer.popleft()

            try:
                data = super().send(*args)
            except zmq.ZMQError as exc:
                self._buffer.appendleft(args)

                if exc.errno != zmq.EAGAIN:
                    self._send_exc = exc
                    self._loop.remove_writer(self._sock_fd)
                    return
            except Exception as exc:
                self._send_exc = exc
                self._loop.remove_writer(self._sock_fd)
                return

        self._loop.remove_writer(self._sock_fd)

    def recv_pyobj(self, flags=0):
        s = yield from self.recv(flags)
        return pickle.loads(s)


class Context(zmq.Context):
    """Replacement for `zmq.Context`.

    Creates special version of Socket object."""

    _loop = None
    _socket_class = None

    def __init__(self, io_threads=1, *, loop=None):
        super().__init__(io_threads)

        if loop is None:
            loop = tulip.get_event_loop()

        self._loop = loop
        self._socket_class = functools.partial(Socket, loop=loop)
