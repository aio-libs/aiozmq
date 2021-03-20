import asyncio
import aiozmq.rpc
import msgpack


class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def __eq__(self, other):
        if isinstance(other, Point):
            return (self.x, self.y) == (other.x, other.y)
        return NotImplemented


translation_table = {
    0: (
        Point,
        lambda value: msgpack.packb((value.x, value.y)),
        lambda binary: Point(*msgpack.unpackb(binary)),
    ),
}


class ServerHandler(aiozmq.rpc.AttrHandler):
    @aiozmq.rpc.method
    def remote(self, val):
        return val


async def go():
    server = await aiozmq.rpc.serve_rpc(
        ServerHandler(), bind="tcp://*:*", translation_table=translation_table
    )
    server_addr = list(server.transport.bindings())[0]

    client = await aiozmq.rpc.connect_rpc(
        connect=server_addr, translation_table=translation_table
    )

    ret = await client.call.remote(Point(1, 2))
    assert ret == Point(1, 2)

    server.close()
    await server.wait_closed()
    client.close()
    await client.wait_closed()


def main():
    asyncio.run(go())
    print("DONE")


if __name__ == "__main__":
    main()
