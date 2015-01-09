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
    0: (Point,
        lambda value: msgpack.packb((value.x, value.y)),
        lambda binary: Point(*msgpack.unpackb(binary))),
}


class ServerHandler(aiozmq.rpc.AttrHandler):
    @aiozmq.rpc.method
    def remote(self, val):
        return val


@asyncio.coroutine
def go():
    server = yield from aiozmq.rpc.serve_rpc(
        ServerHandler(), bind='tcp://*:*',
        translation_table=translation_table)
    server_addr = list(server.transport.bindings())[0]

    client = yield from aiozmq.rpc.connect_rpc(
        connect=server_addr,
        translation_table=translation_table)

    ret = yield from client.call.remote(Point(1, 2))
    assert ret == Point(1, 2)

    server.close()
    yield from server.wait_closed()
    client.close()
    yield from client.wait_closed()


def main():
    asyncio.get_event_loop().run_until_complete(go())
    print("DONE")


if __name__ == '__main__':
    main()
