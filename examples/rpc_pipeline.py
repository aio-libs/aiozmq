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


@asyncio.coroutine
def go():
    handler = Handler()
    listener = yield from aiozmq.rpc.serve_pipeline(
        handler, bind='tcp://*:*')
    listener_addr = list(listener.transport.bindings())[0]

    notifier = yield from aiozmq.rpc.connect_pipeline(
        connect=listener_addr)

    for step in count(0):
        yield from notifier.notify.remote_func(step, 1, 2)
        if handler.connected:
            break
        else:
            yield from asyncio.sleep(0.01)

    listener.close()
    yield from listener.wait_closed()
    notifier.close()
    yield from notifier.wait_closed()


def main():
    asyncio.get_event_loop().run_until_complete(go())
    print("DONE")


if __name__ == '__main__':
    main()
