import asyncio
import aiozmq
import aiozmq.rpc


@aiozmq.rpc.method
def a():
    return 'a'


@aiozmq.rpc.method
def b():
    return 'b'


handlers_dict = {'a': a,
                 'subnamespace': {'b': b}
                }


@asyncio.coroutine
def go():
    server = yield from aiozmq.rpc.start_server(
        handlers_dict, bind='tcp://*:*')
    server_addr = next(iter(server.transport.bindings()))

    client = yield from aiozmq.rpc.open_client(
        connect=server_addr)

    ret = yield from client.rpc.a()
    assert 'a' == ret

    ret = yield from client.rpc.subnamespace.b()
    assert 'b' == ret

    server.close()
    client.close()


def main():
    asyncio.set_event_loop_policy(aiozmq.ZmqEventLoopPolicy())
    asyncio.get_event_loop().run_until_complete(go())
    print("DONE")


if __name__ == '__main__':
    main()
