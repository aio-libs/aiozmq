import asyncio
import aiozmq, aiozmq.rpc
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
    server = yield from aiozmq.rpc.start_server(
        ServerHandler(), bind='tcp://127.0.0.1:5555',
        translation_table=translation_table)
    client = yield from aiozmq.rpc.open_client(
        connect='tcp://127.0.0.1:5555',
        translation_table=translation_table)

    ret = yield from client.rpc.remote(Point(1, 2))
    assert ret == Point(1, 2)

    server.close()
    client.close()


def main():
    asyncio.set_event_loop_policy(aiozmq.ZmqEventLoopPolicy())
    asyncio.get_event_loop().run_until_complete(go())
    print("DONE")

if __name__ == '__main__':
    main()
