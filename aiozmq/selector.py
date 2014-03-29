"""ZMQ pooler for asyncio."""


__all__ = ['ZmqSelector']

import math

try:
    from asyncio.selectors import (BaseSelector, SelectorKey,
                                   EVENT_READ, EVENT_WRITE)
except ImportError:  # pragma: no cover
    from selectors import BaseSelector, SelectorKey, EVENT_READ, EVENT_WRITE
from collections import Mapping
from errno import EINTR
from zmq import (ZMQError, POLLIN, POLLOUT, POLLERR,
                 Socket as ZMQSocket, Poller as ZMQPoller)


def _fileobj_to_fd(fileobj):
    """Return a file descriptor from a file object.

    Parameters:
    fileobj -- file object or file descriptor

    Returns:
    corresponding file descriptor or zmq.Socket instance

    Raises:
    ValueError if the object is invalid
    """
    if isinstance(fileobj, int):
        fd = fileobj
    elif isinstance(fileobj, ZMQSocket):
        return fileobj
    else:
        try:
            fd = int(fileobj.fileno())
        except (AttributeError, TypeError, ValueError):
            raise ValueError("Invalid file object: "
                             "{!r}".format(fileobj)) from None
    if fd < 0:
        raise ValueError("Invalid file descriptor: {}".format(fd))
    return fd


class _SelectorMapping(Mapping):
    """Mapping of file objects to selector keys."""

    def __init__(self, selector):
        self._selector = selector

    def __len__(self):
        return len(self._selector._fd_to_key)

    def __getitem__(self, fileobj):
        try:
            fd = self._selector._fileobj_lookup(fileobj)
            return self._selector._fd_to_key[fd]
        except KeyError:
            raise KeyError("{!r} is not registered".format(fileobj)) from None

    def __iter__(self):
        return iter(self._selector._fd_to_key)


class ZmqSelector(BaseSelector):
    """A selector that can be used with asyncio's selector base event loops."""

    def __init__(self):
        # this maps file descriptors to keys
        self._fd_to_key = {}
        # read-only mapping returned by get_map()
        self._map = _SelectorMapping(self)
        self._poller = ZMQPoller()

    def _fileobj_lookup(self, fileobj):
        """Return a file descriptor from a file object.

        This wraps _fileobj_to_fd() to do an exhaustive search in case
        the object is invalid but we still have it in our map.  This
        is used by unregister() so we can unregister an object that
        was previously registered even if it is closed.  It is also
        used by _SelectorMapping.
        """
        try:
            return _fileobj_to_fd(fileobj)
        except ValueError:
            # Do an exhaustive search.
            for key in self._fd_to_key.values():
                if key.fileobj is fileobj:
                    return key.fd
            # Raise ValueError after all.
            raise

    def register(self, fileobj, events, data=None):
        if (not events) or (events & ~(EVENT_READ | EVENT_WRITE)):
            raise ValueError("Invalid events: {!r}".format(events))

        key = SelectorKey(fileobj, self._fileobj_lookup(fileobj), events, data)

        if key.fd in self._fd_to_key:
            raise KeyError("{!r} (FD {}) is already registered"
                           .format(fileobj, key.fd))

        z_events = 0
        if events & EVENT_READ:
            z_events |= POLLIN
        if events & EVENT_WRITE:
            z_events |= POLLOUT
        try:
            self._poller.register(key.fd, z_events)
        except ZMQError as exc:
            raise OSError(exc.errno, exc.strerror) from exc

        self._fd_to_key[key.fd] = key
        return key

    def unregister(self, fileobj):
        try:
            key = self._fd_to_key.pop(self._fileobj_lookup(fileobj))
        except KeyError:
            raise KeyError("{!r} is not registered".format(fileobj)) from None
        try:
            self._poller.unregister(key.fd)
        except ZMQError as exc:
            self._fd_to_key[key.fd] = key
            raise OSError(exc.errno, exc.strerror) from exc
        return key

    def modify(self, fileobj, events, data=None):
        try:
            fd = self._fileobj_lookup(fileobj)
            key = self._fd_to_key[fd]
        except KeyError:
            raise KeyError("{!r} is not registered".format(fileobj)) from None
        if data == key.data and events == key.events:
            return key
        if events != key.events:
            z_events = 0
            if events & EVENT_READ:
                z_events |= POLLIN
            if events & EVENT_WRITE:
                z_events |= POLLOUT
            try:
                self._poller.modify(fd, z_events)
            except ZMQError as exc:
                raise OSError(exc.errno, exc.strerror) from exc

        key = key._replace(data=data, events=events)
        self._fd_to_key[key.fd] = key
        return key

    def close(self):
        self._fd_to_key.clear()
        self._poller = None

    def get_map(self):
        return self._map

    def _key_from_fd(self, fd):
        """Return the key associated to a given file descriptor.

        Parameters:
        fd -- file descriptor

        Returns:
        corresponding key, or None if not found
        """
        try:
            return self._fd_to_key[fd]
        except KeyError:
            return None

    def select(self, timeout=None):
        if timeout is None:
            timeout = None
        elif timeout <= 0:
            timeout = 0
        else:
            # poll() has a resolution of 1 millisecond, round away from
            # zero to wait *at least* timeout seconds.
            timeout = math.ceil(timeout * 1e3)

        ready = []
        try:
            z_events = self._poller.poll(timeout)
        except ZMQError as exc:
            if exc.errno == EINTR:
                return ready
            else:
                raise OSError(exc.errno, exc.strerror) from exc

        for fd, evt in z_events:
            events = 0
            if evt & POLLIN:
                events |= EVENT_READ
            if evt & POLLOUT:
                events |= EVENT_WRITE
            if evt & POLLERR:
                events = EVENT_READ | EVENT_WRITE

            key = self._key_from_fd(fd)
            if key:
                ready.append((key, events & key.events))

        return ready
