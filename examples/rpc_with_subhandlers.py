import asyncio
import aiozmq.rpc


class Handler(aiozmq.rpc.AttrHandler):
    def __init__(self, ident):
        self.ident = ident
        self.subhandler = SubHandler(self.ident, "subident")

    @aiozmq.rpc.method
    def a(self):
        return (self.ident, "a")


class SubHandler(aiozmq.rpc.AttrHandler):
    def __init__(self, ident, subident):
        self.ident = ident
        self.subident = subident

    @aiozmq.rpc.method
    def b(self):
        return (self.ident, self.subident, "b")


async def go():
    server = await aiozmq.rpc.serve_rpc(Handler("ident"), bind="tcp://*:*")
    server_addr = list(server.transport.bindings())[0]

    client = await aiozmq.rpc.connect_rpc(connect=server_addr)

    ret = await client.call.a()
    assert ("ident", "a") == ret

    ret = await client.call.subhandler.b()
    assert ("ident", "subident", "b") == ret

    server.close()
    await server.wait_closed()
    client.close()
    await client.wait_closed()


def main():
    asyncio.run(go())
    print("DONE")


if __name__ == "__main__":
    main()
