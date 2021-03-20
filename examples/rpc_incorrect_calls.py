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

    try:
        await client.call.unknown_function()
    except aiozmq.rpc.NotFoundError as exc:
        print("client.rpc.unknown_function(): {}".format(exc))

    try:
        await client.call.remote_func(bad_arg=1)
    except aiozmq.rpc.ParametersError as exc:
        print("client.rpc.remote_func(bad_arg=1): {}".format(exc))

    try:
        await client.call.remote_func(1)
    except aiozmq.rpc.ParametersError as exc:
        print("client.rpc.remote_func(1): {}".format(exc))

    try:
        await client.call.remote_func("a", "b")
    except aiozmq.rpc.ParametersError as exc:
        print("client.rpc.remote_func('a', 'b'): {}".format(exc))

    server.close()
    await server.wait_closed()
    client.close()
    await client.wait_closed()


def main():
    asyncio.run(go())
    print("DONE")


if __name__ == "__main__":
    main()
