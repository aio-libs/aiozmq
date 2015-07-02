import asyncio
import aiozmq
import zmq


@asyncio.coroutine
def monitor_stream(stream):
    try:
        while True:
            event = yield from stream.read_event()
            print(event)
    except aiozmq.ZmqStreamClosed:
        pass


@asyncio.coroutine
def go():
    router = yield from aiozmq.create_zmq_stream(
        zmq.ROUTER,
        bind='tcp://127.0.0.1:*')
    addr = list(router.transport.bindings())[0]

    dealer = yield from aiozmq.create_zmq_stream(
        zmq.DEALER)

    yield from dealer.transport.enable_monitor()

    asyncio.Task(monitor_stream(dealer))

    yield from dealer.transport.connect(addr)

    for i in range(10):
        msg = (b'data', b'ask', str(i).encode('utf-8'))
        dealer.write(msg)
        data = yield from router.read()
        router.write(data)
        answer = yield from dealer.read()
        print(answer)

    router.close()
    dealer.close()


def main():
    asyncio.get_event_loop().run_until_complete(go())
    print("DONE")


if __name__ == '__main__':
    main()
