import asyncio
import aiozmq
import zmq


class ZmqDealerProtocol(aiozmq.ZmqProtocol):

    transport = None

    def __init__(self, queue, on_close):
        self.queue = queue
        self.on_close = on_close

    def connection_made(self, transport):
        self.transport = transport

    def msg_received(self, msg):
        self.queue.put_nowait(msg)

    def connection_lost(self, exc):
        self.on_close.set_result(exc)


class ZmqRouterProtocol(aiozmq.ZmqProtocol):

    transport = None

    def __init__(self, on_close):
        self.on_close = on_close

    def connection_made(self, transport):
        self.transport = transport

    def msg_received(self, msg):
        self.transport.write(msg)

    def connection_lost(self, exc):
        self.on_close.set_result(exc)


@asyncio.coroutine
def go():
    router_closed = asyncio.Future()
    dealer_closed = asyncio.Future()
    router, _ = yield from aiozmq.create_zmq_connection(
        lambda: ZmqRouterProtocol(router_closed), zmq.ROUTER, bind="tcp://127.0.0.1:*"
    )

    addr = list(router.bindings())[0]
    queue = asyncio.Queue()
    dealer, _ = yield from aiozmq.create_zmq_connection(
        lambda: ZmqDealerProtocol(queue, dealer_closed), zmq.DEALER, connect=addr
    )

    for i in range(10):
        msg = (b"data", b"ask", str(i).encode("utf-8"))
        dealer.write(msg)
        answer = yield from queue.get()
        print(answer)
    dealer.close()
    yield from dealer_closed
    router.close()
    yield from router_closed


def main():
    asyncio.get_event_loop().run_until_complete(go())
    print("DONE")


if __name__ == "__main__":
    main()
