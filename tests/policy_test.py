import asyncio
import threading
import unittest
from unittest import mock
import aiozmq


class PolicyTests(unittest.TestCase):

    def setUp(self):
        self.policy = aiozmq.ZmqEventLoopPolicy(io_threads=5)

    def test_ctor(self):
        self.assertEqual(5, self.policy._io_threads)

    def test_get_event_loop(self):
        self.assertIsNone(self.policy._local._loop)

        loop = self.policy.get_event_loop()
        self.assertIsInstance(loop, asyncio.AbstractEventLoop)

        self.assertIs(self.policy._local._loop, loop)
        self.assertIs(loop, self.policy.get_event_loop())
        loop.close()

    def test_get_event_loop_calls_set_event_loop(self):
        with mock.patch.object(
                self.policy, "set_event_loop",
                wraps=self.policy.set_event_loop) as m_set_event_loop:

            loop = self.policy.get_event_loop()

            # policy._local._loop must be set through .set_event_loop()
            # (the unix DefaultEventLoopPolicy needs this call to attach
            # the child watcher correctly)
            m_set_event_loop.assert_called_with(loop)

        loop.close()

    def test_get_event_loop_after_set_none(self):
        self.policy.set_event_loop(None)
        self.assertRaises(AssertionError, self.policy.get_event_loop)

    @mock.patch('aiozmq.core.threading.current_thread')
    def test_get_event_loop_thread(self, m_current_thread):

        def f():
            self.assertRaises(AssertionError, self.policy.get_event_loop)

        th = threading.Thread(target=f)
        th.start()
        th.join()

    def test_new_event_loop(self):
        loop = self.policy.new_event_loop()
        self.assertIsInstance(loop, asyncio.AbstractEventLoop)
        loop.close()

    def test_set_event_loop(self):
        old_loop = self.policy.get_event_loop()

        self.assertRaises(AssertionError, self.policy.set_event_loop, object())

        loop = self.policy.new_event_loop()
        self.policy.set_event_loop(loop)
        self.assertIs(loop, self.policy.get_event_loop())
        self.assertIsNot(old_loop, self.policy.get_event_loop())
        loop.close()
        old_loop.close()

    def test_get_child_watcher(self):
        self.assertIsNone(self.policy._watcher)

        watcher = self.policy.get_child_watcher()
        self.assertIsInstance(watcher, asyncio.SafeChildWatcher)

        self.assertIs(self.policy._watcher, watcher)

        self.assertIs(watcher, self.policy.get_child_watcher())
        self.assertIsNone(watcher._loop)

    def test_get_child_watcher_after_set(self):
        watcher = asyncio.FastChildWatcher()

        self.policy.set_child_watcher(watcher)
        self.assertIs(self.policy._watcher, watcher)
        self.assertIs(watcher, self.policy.get_child_watcher())

    def test_get_child_watcher_with_mainloop_existing(self):
        loop = self.policy.get_event_loop()

        self.assertIsNone(self.policy._watcher)
        watcher = self.policy.get_child_watcher()

        self.assertIsInstance(watcher, asyncio.SafeChildWatcher)
        self.assertIs(watcher._loop, loop)

        loop.close()

    def test_get_child_watcher_thread(self):

        def f():
            self.policy.set_event_loop(self.policy.new_event_loop())

            self.assertIsInstance(self.policy.get_event_loop(),
                                  asyncio.AbstractEventLoop)
            watcher = self.policy.get_child_watcher()

            self.assertIsInstance(watcher, asyncio.SafeChildWatcher)
            self.assertIsNone(watcher._loop)

            self.policy.get_event_loop().close()

        th = threading.Thread(target=f)
        th.start()
        th.join()

    def test_child_watcher_replace_mainloop_existing(self):
        loop = self.policy.get_event_loop()

        watcher = self.policy.get_child_watcher()

        self.assertIs(watcher._loop, loop)

        new_loop = self.policy.new_event_loop()
        self.policy.set_event_loop(new_loop)

        self.assertIs(watcher._loop, new_loop)

        self.policy.set_event_loop(None)

        self.assertIs(watcher._loop, None)

        loop.close()
        new_loop.close()

    def test_get_child_watcher_to_override_existing_one(self):
        watcher = asyncio.FastChildWatcher()

        # initializes default watcher as side-effect
        self.policy.get_child_watcher()

        self.policy.set_child_watcher(watcher)
        self.assertIs(self.policy._watcher, watcher)
        self.assertIs(watcher, self.policy.get_child_watcher())
