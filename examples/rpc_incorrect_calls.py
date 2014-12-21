import asyncio
import aiozmq.rpc


class ServerHandler(aiozmq.rpc.AttrHandler):

    @aiozmq.rpc.method
    def remote_func(self, a: int, b: int) -> int:
        return a + b


@asyncio.coroutine
def go():
    server = yield from aiozmq.rpc.serve_rpc(
        ServerHandler(), bind='tcp://*:*')
    server_addr = next(iter(server.transport.bindings()))

    client = yield from aiozmq.rpc.connect_rpc(
        connect=server_addr)

    try:
        yield from client.call.unknown_function()
    except aiozmq.rpc.NotFoundError as exc:
        print("client.rpc.unknown_function(): {}".format(exc))

    try:
        yield from client.call.remote_func(bad_arg=1)
    except aiozmq.rpc.ParametersError as exc:
        print("client.rpc.remote_func(bad_arg=1): {}".format(exc))

    try:
        yield from client.call.remote_func(1)
    except aiozmq.rpc.ParametersError as exc:
        print("client.rpc.remote_func(1): {}".format(exc))

    try:
        yield from client.call.remote_func('a', 'b')
    except aiozmq.rpc.ParametersError as exc:
        print("client.rpc.remote_func('a', 'b'): {}".format(exc))

    server.close()
    yield from server.wait_closed()
    client.close()
    yield from client.wait_closed()


def main():
    asyncio.get_event_loop().run_until_complete(go())
    print("DONE")


if __name__ == '__main__':
    main()
