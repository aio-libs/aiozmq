import asyncio
import aiozmq.rpc


class Handler(aiozmq.rpc.AttrHandler):

    @aiozmq.rpc.method
    def handle_some_event(self, a: int, b: int):
        pass


@asyncio.coroutine
def go():
    listener = yield from aiozmq.rpc.serve_pipeline(
        Handler(), bind='tcp://*:*')
    listener_addr = next(iter(listener.transport.bindings()))

    notifier = yield from aiozmq.rpc.connect_pipeline(
        connect=listener_addr)

    yield from notifier.notify.handle_some_event(1, 2)

    listener.close()
    notifier.close()


def main():
    asyncio.get_event_loop().run_until_complete(go())
    print("DONE")


if __name__ == '__main__':
    main()
