import asyncio
import aiozmq.rpc


class ServerHandler(aiozmq.rpc.AttrHandler):
    @aiozmq.rpc.method
    def remote_func(self, a: int, b: int) -> int:
        return a + b


@asyncio.coroutine
def go():
    server = yield from aiozmq.rpc.serve_rpc(ServerHandler(), bind="tcp://*:*")
    server_addr = list(server.transport.bindings())[0]

    client = yield from aiozmq.rpc.connect_rpc(connect=server_addr)

    ret = yield from client.call.remote_func(1, 2)
    assert 3 == ret

    server.close()
    yield from server.wait_closed()
    client.close()
    yield from client.wait_closed()


def main():
    asyncio.get_event_loop().run_until_complete(go())
    print("DONE")


if __name__ == "__main__":
    main()
