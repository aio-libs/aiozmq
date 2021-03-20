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
    subscriber = yield from aiozmq.rpc.serve_pubsub(
        handler, subscribe="topic", bind="tcp://127.0.0.1:*", log_exceptions=True
    )
    subscriber_addr = list(subscriber.transport.bindings())[0]
    print("SERVE", subscriber_addr)

    publisher = yield from aiozmq.rpc.connect_pubsub(connect=subscriber_addr)

    for step in count(0):
        yield from publisher.publish("topic").remote_func(step, 1, 2)
        if handler.connected:
            break
        else:
            yield from asyncio.sleep(0.1)

    subscriber.close()
    yield from subscriber.wait_closed()
    publisher.close()
    yield from publisher.wait_closed()


def main():
    asyncio.get_event_loop().run_until_complete(go())
    print("DONE")


if __name__ == "__main__":
    main()
