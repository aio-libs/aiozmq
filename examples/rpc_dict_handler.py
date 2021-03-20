import asyncio
import aiozmq.rpc


@aiozmq.rpc.method
def a():
    return "a"


@aiozmq.rpc.method
def b():
    return "b"


handlers_dict = {"a": a, "subnamespace": {"b": b}}


async def go():
    server = await aiozmq.rpc.serve_rpc(handlers_dict, bind="tcp://*:*")
    server_addr = list(server.transport.bindings())[0]

    client = await aiozmq.rpc.connect_rpc(connect=server_addr)

    ret = await client.call.a()
    assert "a" == ret

    ret = await client.call.subnamespace.b()
    assert "b" == ret

    server.close()
    await server.wait_closed()
    client.close()
    await client.wait_closed()


def main():
    asyncio.run(go())
    print("DONE")


if __name__ == "__main__":
    main()
