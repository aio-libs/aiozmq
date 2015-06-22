
'''
This example demonstrates how to use the ZMQ socket monitor to receive
socket events.
'''

import asyncio
import aiozmq
import zmq


class Protocol(aiozmq.ZmqProtocol):

    def __init__(self):
        self.wait_ready = asyncio.Future()
        self.wait_done = asyncio.Future()
        self.wait_closed = asyncio.Future()

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

    def __init__(self):
        self.wait_ready = asyncio.Future()
        self.wait_closed = asyncio.Future()

    def connection_made(self, transport):
        self.transport = transport
        self.wait_ready.set_result(True)

    def connection_lost(self, exc):
        self.wait_closed.set_result(exc)

    def event_received(self, event):
        print(event)


@asyncio.coroutine
def go():
    loop = asyncio.get_event_loop()
    st, sp = yield from aiozmq.create_zmq_connection(
        Protocol,
        zmq.ROUTER,
        bind='tcp://127.0.0.1:*',
        loop=loop)
    yield from sp.wait_ready
    addr = list(st.bindings())[0]

    ct, cp = yield from aiozmq.create_zmq_connection(
        Protocol,
        zmq.DEALER,
        loop=loop)

    # Establish a socket event monitor on the client
    mon_sock = ct.get_monitor_socket()
    mt, mp = yield from aiozmq.create_zmq_connection(
        EventProtocol,
        zmq.PAIR,
        zmq_sock=mon_sock,
        loop=loop)
    yield from mp.wait_ready

    # Now that the socket event monitor is established lets connect the
    # client to the server which will trigger some events.
    yield from ct.connect(addr)
    yield from cp.wait_ready

    # Send a message to the server. The server should respond and this
    # completes the test.
    ct.write([b'Hello'])
    yield from cp.wait_done

    ct.disable_monitor_socket()

    ct.close()
    yield from cp.wait_closed
    st.close()
    yield from sp.wait_closed
    mt.close()
    yield from mp.wait_closed


def main():
    asyncio.get_event_loop().run_until_complete(go())
    print("DONE")


if __name__ == '__main__':
    main()
