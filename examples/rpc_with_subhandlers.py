import asyncio
import aiozmq.rpc


class Handler(aiozmq.rpc.AttrHandler):

    def __init__(self, ident):
        self.ident = ident
        self.subhandler = SubHandler(self.ident, 'subident')

    @aiozmq.rpc.method
    def a(self):
        return (self.ident, 'a')


class SubHandler(aiozmq.rpc.AttrHandler):

    def __init__(self, ident, subident):
        self.ident = ident
        self.subident = subident

    @aiozmq.rpc.method
    def b(self):
        return (self.ident, self.subident, 'b')


@asyncio.coroutine
def go():
    server = yield from aiozmq.rpc.serve_rpc(
        Handler('ident'), bind='tcp://*:*')
    server_addr = next(iter(server.transport.bindings()))

    client = yield from aiozmq.rpc.connect_rpc(
        connect=server_addr)

    ret = yield from client.call.a()
    assert ('ident', 'a') == ret

    ret = yield from client.call.subhandler.b()
    assert ('ident', 'subident', 'b') == ret

    server.close()
    yield from server.wait_closed()
    client.close()
    yield from client.wait_closed()


def main():
    asyncio.get_event_loop().run_until_complete(go())
    print("DONE")


if __name__ == '__main__':
    main()
