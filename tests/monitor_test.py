import unittest
import asyncio
import aiozmq
import zmq

from aiozmq._test_util import find_unused_port


class Protocol(aiozmq.ZmqProtocol):

    def __init__(self, loop):
        self.wait_ready = asyncio.Future(loop=loop)
        self.wait_done = asyncio.Future(loop=loop)
        self.wait_closed = asyncio.Future(loop=loop)

    def connection_made(self, transport):
        self.transport = transport
        self.wait_ready.set_result(True)

    def connection_lost(self, exc):
        self.wait_closed.set_result(exc)

    def msg_received(self, data):
        # This protocol is used by both the Router and Dealer sockets.
        # Messages received by the router come prefixed with an 'identity'
        # and hence contain two frames in this simple test protocol.
        if len(data) == 2:
            identity, msg = data
            if msg == b'Hello':
                self.transport.write([identity, b'World'])
        else:
            msg = data[0]
            if msg == b'World':
                self.wait_done.set_result(True)


class EventProtocol(aiozmq.ZmqEventProtocol):

    def __init__(self, loop):
        self.wait_ready = asyncio.Future(loop=loop)
        self.wait_closed = asyncio.Future(loop=loop)
        self.received = asyncio.Queue(loop=loop)

    def connection_made(self, transport):
        self.transport = transport
        self.wait_ready.set_result(True)

    def connection_lost(self, exc):
        self.wait_closed.set_result(exc)

    def event_received(self, event):
        self.received.put_nowait(event)


class ZmqSocketMonitorTests(unittest.TestCase):

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(None)

    def tearDown(self):
        self.loop.close()
        asyncio.set_event_loop(None)

    def test_socket_monitor(self):
        port = find_unused_port()

        @asyncio.coroutine
        def go():

            # Create server and bind
            st, sp = yield from aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.ROUTER,
                bind='tcp://127.0.0.1:{}'.format(port),
                loop=self.loop)
            yield from sp.wait_ready
            addr = list(st.bindings())[0]

            # Create client but don't connect it yet.
            ct, cp = yield from aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.DEALER,
                loop=self.loop)

            # Establish the socket monitor on the client socket
            mon_sock = ct.get_monitor_socket()
            mt, mp = yield from aiozmq.create_zmq_connection(
                lambda: EventProtocol(self.loop),
                zmq.PAIR,
                zmq_sock=mon_sock,
                loop=self.loop)
            yield from mp.wait_ready

            # Now that the socket event monitor is established, connect
            # the client to the server which will generate some events.
            yield from ct.connect(addr)
            yield from cp.wait_ready

            # Send a message to the server. The server should respond and
            # this is used to compete the wait_done future.
            ct.write([b'Hello'])
            yield from cp.wait_done

            ct.disable_monitor_socket()

            ct.close()
            yield from cp.wait_closed
            st.close()
            yield from sp.wait_closed
            mt.close()
            yield from mp.wait_closed

            # Confirm that the events received by the monitor were valid.
            while not mp.received.empty():
                event = yield from mp.received.get()
                self.assertIn(event['event'], aiozmq.MonitorEvents)

        self.loop.run_until_complete(go())


if __name__ == '__main__':
    unittest.main()
