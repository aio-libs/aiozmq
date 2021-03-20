import asyncio
import aiozmq.rpc


class ServerHandler(aiozmq.rpc.AttrHandler):
    @aiozmq.rpc.method
    def remote_func(self, a: int, b: int) -> int:
        return a + b


async def go():
    server = await aiozmq.rpc.serve_rpc(ServerHandler(), bind="tcp://*:*")
    server_addr = list(server.transport.bindings())[0]

    client = await aiozmq.rpc.connect_rpc(connect=server_addr)

    ret = await client.call.remote_func(1, 2)
    assert 3 == ret

    server.close()
    await server.wait_closed()
    client.close()
    await client.wait_closed()


def main():
    asyncio.run(go())
    print("DONE")


if __name__ == "__main__":
    main()
