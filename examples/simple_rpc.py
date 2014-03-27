import asyncio
import aiozmq
import aiozmq.rpc


class ServerHandler(aiozmq.rpc.AttrHandler):

    @aiozmq.rpc.method
    def remote_func(self, a:int, b:int) -> int:
        return a + b


@asyncio.coroutine
def go():
    server = yield from aiozmq.rpc.serve_rpc(
        ServerHandler(), bind='tcp://127.0.0.1:5555')
    client = yield from aiozmq.rpc.connect_rpc(
        connect='tcp://127.0.0.1:5555')

    ret = yield from client.rpc.remote_func(1, 2)
    assert 3 == ret

    server.close()
    client.close()

def main():
    asyncio.set_event_loop_policy(aiozmq.ZmqEventLoopPolicy())
    asyncio.get_event_loop().run_until_complete(go())
    print("DONE")

if __name__ == '__main__':
    main()
