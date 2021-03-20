import asyncio
import aiozmq
import zmq


async def monitor_stream(stream):
    try:
        while True:
            event = await stream.read_event()
            print(event)
    except aiozmq.ZmqStreamClosed:
        pass


async def go():
    router = await aiozmq.create_zmq_stream(zmq.ROUTER, bind="tcp://127.0.0.1:*")
    addr = list(router.transport.bindings())[0]

    dealer = await aiozmq.create_zmq_stream(zmq.DEALER)

    await dealer.transport.enable_monitor()

    asyncio.Task(monitor_stream(dealer))

    await dealer.transport.connect(addr)

    for i in range(10):
        msg = (b"data", b"ask", str(i).encode("utf-8"))
        dealer.write(msg)
        data = await router.read()
        router.write(data)
        answer = await dealer.read()
        print(answer)

    router.close()
    dealer.close()


def main():
    asyncio.run(go())
    print("DONE")


if __name__ == "__main__":
    main()
