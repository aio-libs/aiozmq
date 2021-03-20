import asyncio
import aiozmq.rpc


class CustomError(Exception):
    def __init__(self, val):
        self.val = val
        super().__init__(val)


exc_name = CustomError.__module__ + "." + CustomError.__name__
error_table = {exc_name: CustomError}


class ServerHandler(aiozmq.rpc.AttrHandler):
    @aiozmq.rpc.method
    def remote(self, val):
        raise CustomError(val)


@asyncio.coroutine
def go():
    server = yield from aiozmq.rpc.serve_rpc(ServerHandler(), bind="tcp://*:*")
    server_addr = list(server.transport.bindings())[0]

    client = yield from aiozmq.rpc.connect_rpc(
        connect=server_addr, error_table=error_table
    )

    try:
        yield from client.call.remote("value")
    except CustomError as exc:
        exc.val == "value"

    server.close()
    client.close()


def main():
    asyncio.get_event_loop().run_until_complete(go())
    print("DONE")


if __name__ == "__main__":
    main()
