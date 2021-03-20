import asyncio
import unittest
import unittest.mock

import aiozmq
import zmq

from aiozmq._test_util import find_unused_port


ZMQ_EVENTS = [getattr(zmq, attr) for attr in dir(zmq) if attr.startswith("EVENT_")]


class Protocol(aiozmq.ZmqProtocol):
    def __init__(self, loop):
        self.wait_ready = asyncio.Future(loop=loop)
        self.wait_done = asyncio.Future(loop=loop)
        self.wait_closed = asyncio.Future(loop=loop)
        self.events_received = asyncio.Queue(loop=loop)

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
            if msg == b"Hello":
                self.transport.write([identity, b"World"])
        else:
            msg = data[0]
            if msg == b"World":
                self.wait_done.set_result(True)

    def event_received(self, event):
        self.events_received.put_nowait(event)


class ZmqSocketMonitorTests(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(None)

    def tearDown(self):
        self.loop.close()
        asyncio.set_event_loop(None)

    @unittest.skipIf(
        zmq.zmq_version_info() < (4,)
        or zmq.pyzmq_version_info()
        < (
            14,
            4,
        ),
        "Socket monitor requires libzmq >= 4 and pyzmq >= 14.4",
    )
    def test_socket_monitor(self):
        port = find_unused_port()

        @asyncio.coroutine
        def go():

            # Create server and bind
            st, sp = yield from aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop),
                zmq.ROUTER,
                bind="tcp://127.0.0.1:{}".format(port),
                loop=self.loop,
            )
            yield from sp.wait_ready
            addr = list(st.bindings())[0]

            # Create client but don't connect it yet.
            ct, cp = yield from aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop), zmq.DEALER, loop=self.loop
            )
            yield from cp.wait_ready

            # Establish an event monitor on the client socket
            yield from ct.enable_monitor()

            # Now that the socket event monitor is established, connect
            # the client to the server which will generate some events.
            yield from ct.connect(addr)
            yield from asyncio.sleep(0.1, loop=self.loop)
            yield from ct.disconnect(addr)
            yield from asyncio.sleep(0.1, loop=self.loop)
            yield from ct.connect(addr)

            # Send a message to the server. The server should respond and
            # this is used to compete the wait_done future.
            ct.write([b"Hello"])
            yield from cp.wait_done

            yield from ct.disable_monitor()

            ct.close()
            yield from cp.wait_closed
            st.close()
            yield from sp.wait_closed

            # Confirm that the events received by the monitor were valid.
            self.assertGreater(cp.events_received.qsize(), 0)
            while not cp.events_received.empty():
                event = yield from cp.events_received.get()
                self.assertIn(event.event, ZMQ_EVENTS)

        self.loop.run_until_complete(go())

    def test_unsupported_dependencies(self):
        @asyncio.coroutine
        def go():

            ct, cp = yield from aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop), zmq.DEALER, loop=self.loop
            )
            yield from cp.wait_ready

            with unittest.mock.patch.object(zmq, "zmq_version_info", return_value=(3,)):
                with self.assertRaises(NotImplementedError):
                    yield from ct.enable_monitor()

            with unittest.mock.patch.object(
                zmq, "pyzmq_version_info", return_value=(14, 3)
            ):
                with self.assertRaises(NotImplementedError):
                    yield from ct.enable_monitor()

            ct.close()
            yield from cp.wait_closed

        self.loop.run_until_complete(go())

    @unittest.skipIf(
        zmq.zmq_version_info() < (4,)
        or zmq.pyzmq_version_info()
        < (
            14,
            4,
        ),
        "Socket monitor requires libzmq >= 4 and pyzmq >= 14.4",
    )
    def test_double_enable_disable(self):
        @asyncio.coroutine
        def go():

            ct, cp = yield from aiozmq.create_zmq_connection(
                lambda: Protocol(self.loop), zmq.DEALER, loop=self.loop
            )
            yield from cp.wait_ready

            yield from ct.enable_monitor()

            # Enabling the monitor after it is already enabled should not
            # cause an error
            yield from ct.enable_monitor()

            yield from ct.disable_monitor()

            # Disabling the monitor after it is already disabled should not
            # cause an error
            yield from ct.disable_monitor()

            ct.close()
            yield from cp.wait_closed

        self.loop.run_until_complete(go())


if __name__ == "__main__":
    unittest.main()
