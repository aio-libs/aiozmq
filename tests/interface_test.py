import asyncio
import unittest
import aiozmq

from aiozmq.core import SocketEvent


class ZmqTransportTests(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()
        asyncio.set_event_loop(None)

    def test_interface(self):
        tr = aiozmq.ZmqTransport()
        self.assertRaises(NotImplementedError, tr.write, [b"data"])
        self.assertRaises(NotImplementedError, tr.abort)
        self.assertRaises(NotImplementedError, tr.getsockopt, 1)
        self.assertRaises(NotImplementedError, tr.setsockopt, 1, 2)
        self.assertRaises(NotImplementedError, tr.set_write_buffer_limits)
        self.assertRaises(NotImplementedError, tr.get_write_buffer_limits)
        self.assertRaises(NotImplementedError, tr.get_write_buffer_size)
        self.assertRaises(NotImplementedError, tr.pause_reading)
        self.assertRaises(NotImplementedError, tr.resume_reading)
        self.assertRaises(NotImplementedError, tr.bind, "endpoint")
        self.assertRaises(NotImplementedError, tr.unbind, "endpoint")
        self.assertRaises(NotImplementedError, tr.bindings)
        self.assertRaises(NotImplementedError, tr.connect, "endpoint")
        self.assertRaises(NotImplementedError, tr.disconnect, "endpoint")
        self.assertRaises(NotImplementedError, tr.connections)
        self.assertRaises(NotImplementedError, tr.subscribe, b"filter")
        self.assertRaises(NotImplementedError, tr.unsubscribe, b"filter")
        self.assertRaises(NotImplementedError, tr.subscriptions)
        with self.assertRaises(NotImplementedError):
            self.loop.run_until_complete(tr.enable_monitor())
        with self.assertRaises(NotImplementedError):
            self.loop.run_until_complete(tr.disable_monitor())


class ZmqProtocolTests(unittest.TestCase):
    def test_interface(self):
        pr = aiozmq.ZmqProtocol()
        self.assertIsNone(pr.msg_received((b"data",)))
        self.assertIsNone(
            pr.event_received(
                SocketEvent(event=1, value=1, endpoint="tcp://127.0.0.1:12345")
            )
        )


class ZmqEventProtocolTests(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()
        asyncio.set_event_loop(None)

    def test_interface(self):
        pr = aiozmq.ZmqProtocol()
        epr = aiozmq.core._ZmqEventProtocol(self.loop, pr)

        # event messages are two frames
        with self.assertRaises(RuntimeError):
            epr.msg_received([b""])

        # event messages expect 6 bytes in the first frame
        with self.assertRaises(RuntimeError):
            epr.msg_received([b"12345", b""])
        with self.assertRaises(RuntimeError):
            epr.msg_received([b"1234567", b""])
