import asyncio
import aiozmq
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
    server = yield from aiozmq.rpc.start_server(
        DynamicHandler(), bind='tcp://*:*')
    server_addr = next(iter(server.transport.bindings()))

    client = yield from aiozmq.rpc.open_client(
        connect=server_addr)

    ret = yield from client.rpc.func()
    assert ((), 'val') == ret, ret

    ret = yield from client.rpc.a.func()
    assert (('a',), 'val') == ret, ret

    ret = yield from client.rpc.a.b.func()
    assert (('a', 'b'), 'val') == ret, ret

    server.close()
    client.close()


def main():
    asyncio.set_event_loop_policy(aiozmq.ZmqEventLoopPolicy())
    asyncio.get_event_loop().run_until_complete(go())
    print("DONE")


if __name__ == '__main__':
    main()
