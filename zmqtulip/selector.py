"""ZMQ pooler for Tulip."""
__all__ = ['ZmqSelector']
import zmq
from zmq import ZMQError, POLLIN, POLLOUT, POLLERR
from tulip.selectors import BaseSelector, EVENT_READ, EVENT_WRITE

EVENT_ALL = EVENT_READ | EVENT_WRITE


class ZmqSelector(BaseSelector):
    """A selector that can be used with tulip's selector base event loops."""

    def __init__(self):
        super().__init__()
        self._poller = zmq.Poller()

    def register(self, fileobj, events, data=None):
        key = super().register(fileobj, events, data)

        z_events = 0
        if events & EVENT_READ:
            z_events |= POLLIN
        if events & EVENT_WRITE:
            z_events |= POLLOUT
        self._poller.register(key.fd, z_events)

        return key

    def unregister(self, fileobj):
        key = super().unregister(fileobj)
        self._poller.unregister(key.fd)
        return key

    def select(self, timeout=None):
        timeout = None if timeout is None else max(timeout, 0)

        ready = []
        try:
            z_events = self._poller.poll(timeout)
        except ZMQError:
            return ready

        for fd, evt in z_events:
            events = 0
            if evt & POLLIN:
                events |= EVENT_READ
            if evt & POLLOUT:
                events |= EVENT_WRITE
            if evt & POLLERR:
                events = EVENT_ALL

            key = self._key_from_fd(fd)
            if key:
                ready.append((key, events & key.events))

        return ready
