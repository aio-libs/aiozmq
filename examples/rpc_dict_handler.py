import asyncio
import aiozmq.rpc


@aiozmq.rpc.method
def a():
    return 'a'


@aiozmq.rpc.method
def b():
    return 'b'


handlers_dict = {'a': a,
                 'subnamespace': {'b': b}}


@asyncio.coroutine
def go():
    server = yield from aiozmq.rpc.serve_rpc(
        handlers_dict, bind='tcp://*:*')
    server_addr = next(iter(server.transport.bindings()))

    client = yield from aiozmq.rpc.connect_rpc(
        connect=server_addr)

    ret = yield from client.call.a()
    assert 'a' == ret

    ret = yield from client.call.subnamespace.b()
    assert 'b' == ret

    server.close()
    yield from server.wait_closed()
    client.close()
    yield from client.wait_closed()


def main():
    asyncio.get_event_loop().run_until_complete(go())
    print("DONE")


if __name__ == '__main__':
    main()
