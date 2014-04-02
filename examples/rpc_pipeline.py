import asyncio
import aiozmq
import aiozmq.rpc


class ServerHandler(aiozmq.rpc.AttrHandler):

    @aiozmq.rpc.method
    def remote_func(self, a: int, b: int):
        pass


@asyncio.coroutine
def go():
    server = yield from aiozmq.rpc.serve_pipeline(
        ServerHandler(), bind='tcp://*:*')
    server_addr = next(iter(server.transport.bindings()))

    client = yield from aiozmq.rpc.connect_pipeline(
        connect=server_addr)

    yield from client.notify.remote_func(1, 2)

    server.close()
    client.close()


def main():
    asyncio.set_event_loop_policy(aiozmq.ZmqEventLoopPolicy())
    asyncio.get_event_loop().run_until_complete(go())
    print("DONE")


if __name__ == '__main__':
    main()
