import errno
import os
import random
import signal
import socket
from time import sleep
import unittest
from unittest import mock

try:
    from time import monotonic as time
except ImportError:
    from time import time as time
try:
    import resource
except ImportError:
    resource = None
import zmq

from aiozmq.selector import ZmqSelector, EVENT_READ, EVENT_WRITE, SelectorKey
from aiozmq._test_util import requires_mac_ver


if hasattr(socket, "socketpair"):
    socketpair = socket.socketpair
else:

    def socketpair(family=socket.AF_INET, type=socket.SOCK_STREAM, proto=0):
        with socket.socket(family, type, proto) as server:
            server.bind(("127.0.0.1", 0))
            server.listen(3)
            c = socket.socket(family, type, proto)
            try:
                c.connect(server.getsockname())
                caddr = c.getsockname()
                while True:
                    a, addr = server.accept()
                    # check that we've got the correct client
                    if addr == caddr:
                        return c, a
                    a.close()
            except OSError:
                c.close()
                raise


def find_ready_matching(ready, flag):
    match = []
    for key, events in ready:
        if events & flag:
            match.append(key.fileobj)
    return match


class SelectorTests(unittest.TestCase):

    SELECTOR = ZmqSelector

    def make_socketpair(self):
        rd, wr = socketpair()
        self.addCleanup(rd.close)
        self.addCleanup(wr.close)
        return rd, wr

    def test_register(self):
        s = self.SELECTOR()
        self.addCleanup(s.close)

        rd, wr = self.make_socketpair()

        key = s.register(rd, EVENT_READ, "data")
        self.assertIsInstance(key, SelectorKey)
        self.assertEqual(key.fileobj, rd)
        self.assertEqual(key.fd, rd.fileno())
        self.assertEqual(key.events, EVENT_READ)
        self.assertEqual(key.data, "data")

        # register an unknown event
        self.assertRaises(ValueError, s.register, 0, 999999)

        # register an invalid FD
        self.assertRaises(ValueError, s.register, -10, EVENT_READ)

        # register twice
        self.assertRaises(KeyError, s.register, rd, EVENT_READ)

        # register the same FD, but with a different object
        self.assertRaises(KeyError, s.register, rd.fileno(), EVENT_READ)

        # register an invalid fd type
        self.assertRaises(ValueError, s.register, "abc", EVENT_READ)

    def test_register_with_zmq_error(self):
        s = self.SELECTOR()
        self.addCleanup(s.close)

        m = mock.Mock()
        m.side_effect = zmq.ZMQError(errno.EFAULT, "not a socket")
        s._poller.register = m

        with self.assertRaises(OSError) as ctx:
            s.register(1, EVENT_READ)
        self.assertEqual(errno.EFAULT, ctx.exception.errno)
        self.assertNotIn(1, s.get_map())

    def test_unregister(self):
        s = self.SELECTOR()
        self.addCleanup(s.close)

        rd, wr = self.make_socketpair()

        s.register(rd, EVENT_READ)
        s.unregister(rd)

        # unregister an unknown file obj
        self.assertRaises(KeyError, s.unregister, 999999)

        # unregister twice
        self.assertRaises(KeyError, s.unregister, rd)

    def test_unregister_with_zmq_error(self):
        s = self.SELECTOR()
        self.addCleanup(s.close)

        rd, wr = self.make_socketpair()
        s.register(rd, EVENT_READ)

        m = mock.Mock()
        m.side_effect = zmq.ZMQError(errno.EFAULT, "not a socket")
        s._poller.unregister = m

        with self.assertRaises(OSError) as ctx:
            s.unregister(rd)
        self.assertEqual(errno.EFAULT, ctx.exception.errno)
        self.assertIn(rd, s.get_map())

    def test_unregister_after_fd_close(self):
        s = self.SELECTOR()
        self.addCleanup(s.close)
        rd, wr = self.make_socketpair()
        r, w = rd.fileno(), wr.fileno()
        s.register(r, EVENT_READ)
        s.register(w, EVENT_WRITE)
        rd.close()
        wr.close()
        s.unregister(r)
        s.unregister(w)

    @unittest.skipUnless(os.name == "posix", "requires posix")
    def test_unregister_after_fd_close_and_reuse(self):
        s = self.SELECTOR()
        self.addCleanup(s.close)
        rd, wr = self.make_socketpair()
        r, w = rd.fileno(), wr.fileno()
        s.register(r, EVENT_READ)
        s.register(w, EVENT_WRITE)
        rd2, wr2 = self.make_socketpair()
        rd.close()
        wr.close()
        os.dup2(rd2.fileno(), r)
        os.dup2(wr2.fileno(), w)
        self.addCleanup(os.close, r)
        self.addCleanup(os.close, w)
        s.unregister(r)
        s.unregister(w)

    def test_unregister_after_socket_close(self):
        s = self.SELECTOR()
        self.addCleanup(s.close)
        rd, wr = self.make_socketpair()
        s.register(rd, EVENT_READ)
        s.register(wr, EVENT_WRITE)
        rd.close()
        wr.close()
        s.unregister(rd)
        s.unregister(wr)

    def test_modify(self):
        s = self.SELECTOR()
        self.addCleanup(s.close)

        rd, wr = self.make_socketpair()

        key = s.register(rd, EVENT_READ)

        # modify events
        key2 = s.modify(rd, EVENT_WRITE)
        self.assertNotEqual(key.events, key2.events)
        self.assertEqual(key2, s.get_key(rd))

        s.unregister(rd)

        # modify data
        d1 = object()
        d2 = object()

        key = s.register(rd, EVENT_READ, d1)
        key2 = s.modify(rd, EVENT_READ, d2)
        self.assertEqual(key.events, key2.events)
        self.assertNotEqual(key.data, key2.data)
        self.assertEqual(key2, s.get_key(rd))
        self.assertEqual(key2.data, d2)

        key3 = s.modify(rd, EVENT_READ, d2)
        self.assertIs(key3, key2)

        # modify unknown file obj
        self.assertRaises(KeyError, s.modify, 999999, EVENT_READ)

        # modify use a shortcut
        d3 = object()
        s.register = mock.Mock()
        s.unregister = mock.Mock()

        s.modify(rd, EVENT_READ, d3)
        self.assertFalse(s.register.called)
        self.assertFalse(s.unregister.called)

    def test_modify_with_zmq_error(self):
        s = self.SELECTOR()
        self.addCleanup(s.close)

        rd, wr = self.make_socketpair()
        s.register(rd, EVENT_READ)

        m = mock.Mock()
        m.side_effect = zmq.ZMQError(errno.EFAULT, "not a socket")
        s._poller.modify = m

        with self.assertRaises(OSError) as ctx:
            s.modify(rd, EVENT_WRITE)
        self.assertEqual(errno.EFAULT, ctx.exception.errno)
        self.assertIn(rd, s.get_map())

    def test_close(self):
        s = self.SELECTOR()
        self.addCleanup(s.close)

        rd, wr = self.make_socketpair()

        s.register(rd, EVENT_READ)
        s.register(wr, EVENT_WRITE)

        s.close()
        self.assertRaises(KeyError, s.get_key, rd)
        self.assertRaises(KeyError, s.get_key, wr)

    def test_get_key(self):
        s = self.SELECTOR()
        self.addCleanup(s.close)

        rd, wr = self.make_socketpair()

        key = s.register(rd, EVENT_READ, "data")
        self.assertEqual(key, s.get_key(rd))

        # unknown file obj
        self.assertRaises(KeyError, s.get_key, 999999)

    def test_get_map(self):
        s = self.SELECTOR()
        self.addCleanup(s.close)

        rd, wr = self.make_socketpair()

        keys = s.get_map()
        self.assertFalse(keys)
        self.assertEqual(len(keys), 0)
        self.assertEqual(list(keys), [])
        key = s.register(rd, EVENT_READ, "data")
        self.assertIn(rd, keys)
        self.assertEqual(key, keys[rd])
        self.assertEqual(len(keys), 1)
        self.assertEqual(list(keys), [rd.fileno()])
        self.assertEqual(list(keys.values()), [key])

        # unknown file obj
        with self.assertRaises(KeyError):
            keys[999999]

        # Read-only mapping
        with self.assertRaises(TypeError):
            del keys[rd]

    def test_select(self):
        s = self.SELECTOR()
        self.addCleanup(s.close)

        rd, wr = self.make_socketpair()

        s.register(rd, EVENT_READ)
        wr_key = s.register(wr, EVENT_WRITE)

        result = s.select()
        for key, events in result:
            self.assertTrue(isinstance(key, SelectorKey))
            self.assertTrue(events)
            self.assertFalse(events & ~(EVENT_READ | EVENT_WRITE))

        self.assertEqual([(wr_key, EVENT_WRITE)], result)

    def test_select_with_zmq_error(self):
        s = self.SELECTOR()
        self.addCleanup(s.close)

        rd, wr = self.make_socketpair()
        s.register(rd, EVENT_READ)

        m = mock.Mock()
        m.side_effect = zmq.ZMQError(errno.EFAULT, "not a socket")
        s._poller.poll = m

        with self.assertRaises(OSError) as ctx:
            s.select()
        self.assertEqual(errno.EFAULT, ctx.exception.errno)

    def test_select_without_key(self):
        s = self.SELECTOR()
        self.addCleanup(s.close)

        rd, wr = self.make_socketpair()

        s.register(wr, EVENT_WRITE)

        s._fd_to_key = {}

        result = s.select()
        self.assertFalse(result)

    def test_context_manager(self):
        s = self.SELECTOR()
        self.addCleanup(s.close)

        rd, wr = self.make_socketpair()

        with s as sel:
            sel.register(rd, EVENT_READ)
            sel.register(wr, EVENT_WRITE)

        self.assertRaises(KeyError, s.get_key, rd)
        self.assertRaises(KeyError, s.get_key, wr)

    def test_fileno(self):
        s = self.SELECTOR()
        self.addCleanup(s.close)

        if hasattr(s, "fileno"):
            fd = s.fileno()
            self.assertTrue(isinstance(fd, int))
            self.assertGreaterEqual(fd, 0)

    def test_selector(self):
        s = self.SELECTOR()
        self.addCleanup(s.close)

        NUM_SOCKETS = 12
        MSG = b" This is a test."
        MSG_LEN = len(MSG)
        readers = []
        writers = []
        r2w = {}
        w2r = {}

        for i in range(NUM_SOCKETS):
            rd, wr = self.make_socketpair()
            s.register(rd, EVENT_READ)
            s.register(wr, EVENT_WRITE)
            readers.append(rd)
            writers.append(wr)
            r2w[rd] = wr
            w2r[wr] = rd

        bufs = []

        while writers:
            ready = s.select()
            ready_writers = find_ready_matching(ready, EVENT_WRITE)
            if not ready_writers:
                self.fail("no sockets ready for writing")
            wr = random.choice(ready_writers)
            wr.send(MSG)

            for i in range(10):
                ready = s.select()
                ready_readers = find_ready_matching(ready, EVENT_READ)
                if ready_readers:
                    break
                # there might be a delay between the write to the write end and
                # the read end is reported ready
                sleep(0.1)
            else:
                self.fail("no sockets ready for reading")
            self.assertEqual([w2r[wr]], ready_readers)
            rd = ready_readers[0]
            buf = rd.recv(MSG_LEN)
            self.assertEqual(len(buf), MSG_LEN)
            bufs.append(buf)
            s.unregister(r2w[rd])
            s.unregister(rd)
            writers.remove(r2w[rd])

        self.assertEqual(bufs, [MSG] * NUM_SOCKETS)

    def test_timeout(self):
        s = self.SELECTOR()
        self.addCleanup(s.close)

        rd, wr = self.make_socketpair()

        s.register(wr, EVENT_WRITE)
        t = time()
        self.assertEqual(1, len(s.select(0)))
        self.assertEqual(1, len(s.select(-1)))
        self.assertLess(time() - t, 0.5)

        s.unregister(wr)
        s.register(rd, EVENT_READ)
        t = time()
        self.assertFalse(s.select(0))
        self.assertFalse(s.select(-1))
        self.assertLess(time() - t, 0.5)

        t0 = time()
        self.assertFalse(s.select(1))
        t1 = time()
        dt = t1 - t0
        self.assertTrue(0.8 <= dt <= 1.6, dt)

    @unittest.skipUnless(
        hasattr(signal, "alarm"), "signal.alarm() required for this test"
    )
    def test_select_interrupt(self):
        s = self.SELECTOR()
        self.addCleanup(s.close)

        rd, wr = self.make_socketpair()

        orig_alrm_handler = signal.signal(signal.SIGALRM, lambda *args: None)
        self.addCleanup(signal.signal, signal.SIGALRM, orig_alrm_handler)
        self.addCleanup(signal.alarm, 0)

        signal.alarm(1)

        s.register(rd, EVENT_READ)
        t = time()
        self.assertFalse(s.select(2))
        self.assertLess(time() - t, 3.5)

    # see issue #18963 for why it's skipped on older OS X versions
    @requires_mac_ver(10, 5)
    @unittest.skipUnless(resource, "Test needs resource module")
    def test_above_fd_setsize(self):
        # A scalable implementation should have no problem with more than
        # FD_SETSIZE file descriptors. Since we don't know the value, we just
        # try to set the soft RLIMIT_NOFILE to the hard RLIMIT_NOFILE ceiling.
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (hard, hard))
            self.addCleanup(resource.setrlimit, resource.RLIMIT_NOFILE, (soft, hard))
            NUM_FDS = hard
        except (OSError, ValueError):
            NUM_FDS = soft

        # guard for already allocated FDs (stdin, stdout...)
        NUM_FDS -= 32

        s = self.SELECTOR()
        self.addCleanup(s.close)

        for i in range(NUM_FDS // 2):
            try:
                rd, wr = self.make_socketpair()
            except OSError:
                # too many FDs, skip - note that we should only catch EMFILE
                # here, but apparently *BSD and Solaris can fail upon connect()
                # or bind() with EADDRNOTAVAIL, so let's be safe
                self.skipTest("FD limit reached")

            try:
                s.register(rd, EVENT_READ)
                s.register(wr, EVENT_WRITE)
            except OSError as e:
                if e.errno == errno.ENOSPC:
                    # this can be raised by epoll if we go over
                    # fs.epoll.max_user_watches sysctl
                    self.skipTest("FD limit reached")
                raise

        self.assertEqual(NUM_FDS // 2, len(s.select()))
