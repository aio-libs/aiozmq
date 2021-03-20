import asyncio
import aiozmq.rpc
from itertools import count


class Handler(aiozmq.rpc.AttrHandler):
    def __init__(self):
        self.connected = False

    @aiozmq.rpc.method
    def remote_func(self, step, a: int, b: int):
        self.connected = True
        print("HANDLER", step, a, b)


async def go():
    handler = Handler()
    subscriber = await aiozmq.rpc.serve_pubsub(
        handler, subscribe="topic", bind="tcp://127.0.0.1:*", log_exceptions=True
    )
    subscriber_addr = list(subscriber.transport.bindings())[0]
    print("SERVE", subscriber_addr)

    publisher = await aiozmq.rpc.connect_pubsub(connect=subscriber_addr)

    for step in count(0):
        await publisher.publish("topic").remote_func(step, 1, 2)
        if handler.connected:
            break
        else:
            await asyncio.sleep(0.1)

    subscriber.close()
    await subscriber.wait_closed()
    publisher.close()
    await publisher.wait_closed()


def main():
    asyncio.run(go())
    print("DONE")


if __name__ == "__main__":
    main()
