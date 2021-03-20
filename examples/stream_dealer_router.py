import asyncio
import aiozmq
import zmq


@asyncio.coroutine
def go():
    router = yield from aiozmq.create_zmq_stream(zmq.ROUTER, bind="tcp://127.0.0.1:*")

    addr = list(router.transport.bindings())[0]
    dealer = yield from aiozmq.create_zmq_stream(zmq.DEALER, connect=addr)

    for i in range(10):
        msg = (b"data", b"ask", str(i).encode("utf-8"))
        dealer.write(msg)
        data = yield from router.read()
        router.write(data)
        answer = yield from dealer.read()
        print(answer)
    dealer.close()
    router.close()


def main():
    asyncio.get_event_loop().run_until_complete(go())
    print("DONE")


if __name__ == "__main__":
    main()
