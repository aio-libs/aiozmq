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
        return (self.namespace, "val")


async def go():
    server = await aiozmq.rpc.serve_rpc(DynamicHandler(), bind="tcp://*:*")
    server_addr = list(server.transport.bindings())[0]

    client = await aiozmq.rpc.connect_rpc(connect=server_addr)

    ret = await client.call.func()
    assert ((), "val") == ret, ret

    ret = await client.call.a.func()
    assert (("a",), "val") == ret, ret

    ret = await client.call.a.b.func()
    assert (("a", "b"), "val") == ret, ret

    server.close()
    await server.wait_closed()
    client.close()
    await client.wait_closed()


def main():
    asyncio.run(go())
    print("DONE")


if __name__ == "__main__":
    main()
