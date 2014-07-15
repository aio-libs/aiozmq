import asyncio
import aiozmq
import aiozmq.rpc


class Handler(aiozmq.rpc.AttrHandler):

    @aiozmq.rpc.method
    def remote_func(self, a: int, b: int):
        pass


@asyncio.coroutine
def go():
    subscriber = yield from aiozmq.rpc.serve_pubsub(
        Handler(), subscribe='topic', bind='tcp://*:*')
    subscriber_addr = next(iter(subscriber.transport.bindings()))

    publisher = yield from aiozmq.rpc.connect_pubsub(
        connect=subscriber_addr)

    yield from publisher.publish('topic').remote_func(1, 2)

    subscriber.close()
    publisher.close()


def main():
    asyncio.set_event_loop_policy(aiozmq.ZmqEventLoopPolicy())
    asyncio.get_event_loop().run_until_complete(go())
    print("DONE")


if __name__ == '__main__':
    main()
