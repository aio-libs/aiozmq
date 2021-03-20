import asyncio
import aiozmq
import zmq


async def go():
    router = await aiozmq.create_zmq_stream(zmq.ROUTER, bind="tcp://127.0.0.1:*")

    addr = list(router.transport.bindings())[0]
    dealer = await aiozmq.create_zmq_stream(zmq.DEALER, connect=addr)

    for i in range(10):
        msg = (b"data", b"ask", str(i).encode("utf-8"))
        dealer.write(msg)
        data = await router.read()
        router.write(data)
        answer = await dealer.read()
        print(answer)
    dealer.close()
    router.close()


def main():
    asyncio.run(go())
    print("DONE")


if __name__ == "__main__":
    main()
