import asyncio
import aiozmq.rpc


class DynamicHandler(aiozmq.rpc.AttrHandler):

    def __init__(self, namespace=()):
        self.namespace = namespace

    def __getitem__(self, key):
        try:
            return getattr(self, key)
        except AttributeError:
            return DynamicHandler(self.namespace + (key,))

    @aiozmq.rpc.method
    def func(self):
        return (self.namespace, 'val')


@asyncio.coroutine
def go():
    server = yield from aiozmq.rpc.serve_rpc(
        DynamicHandler(), bind='tcp://*:*')
    server_addr = list(server.transport.bindings())[0]

    client = yield from aiozmq.rpc.connect_rpc(
        connect=server_addr)

    ret = yield from client.call.func()
    assert ((), 'val') == ret, ret

    ret = yield from client.call.a.func()
    assert (('a',), 'val') == ret, ret

    ret = yield from client.call.a.b.func()
    assert (('a', 'b'), 'val') == ret, ret

    server.close()
    yield from server.wait_closed()
    client.close()
    yield from client.wait_closed()


def main():
    asyncio.get_event_loop().run_until_complete(go())
    print("DONE")


if __name__ == '__main__':
    main()
