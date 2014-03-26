import unittest
import aiozmq


class ZmqTransportTests(unittest.TestCase):

    def test_interface(self):
        tr = aiozmq.ZmqTransport()
        self.assertRaises(NotImplementedError, tr.write, [b'data'])
        self.assertRaises(NotImplementedError, tr.abort)
        self.assertRaises(NotImplementedError, tr.getsockopt, 1)
        self.assertRaises(NotImplementedError, tr.setsockopt, 1, 2)
        self.assertRaises(NotImplementedError, tr.set_write_buffer_limits)
        self.assertRaises(NotImplementedError, tr.get_write_buffer_size)
        self.assertRaises(NotImplementedError, tr.bind, 'endpoint')
        self.assertRaises(NotImplementedError, tr.unbind, 'endpoint')
        self.assertRaises(NotImplementedError, tr.bindings)
        self.assertRaises(NotImplementedError, tr.connect, 'endpoint')
        self.assertRaises(NotImplementedError, tr.disconnect, 'endpoint')
        self.assertRaises(NotImplementedError, tr.connections)
        self.assertRaises(NotImplementedError, tr.subscribe, b'filter')
        self.assertRaises(NotImplementedError, tr.unsubscribe, b'filter')
        self.assertRaises(NotImplementedError, tr.subscriptions)


class ZmqProtocolTests(unittest.TestCase):

    def test_interface(self):
        pr = aiozmq.ZmqProtocol()
        self.assertIsNone(pr.msg_received((b'data',)))
