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
    listener = await aiozmq.rpc.serve_pipeline(handler, bind="tcp://*:*")
    listener_addr = list(listener.transport.bindings())[0]

    notifier = await aiozmq.rpc.connect_pipeline(connect=listener_addr)

    for step in count(0):
        await notifier.notify.remote_func(step, 1, 2)
        if handler.connected:
            break
        else:
            await asyncio.sleep(0.01)

    listener.close()
    await listener.wait_closed()
    notifier.close()
    await notifier.wait_closed()


def main():
    asyncio.run(go())
    print("DONE")


if __name__ == "__main__":
    main()
