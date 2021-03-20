import asyncio
import aiozmq
import zmq
import argparse
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--addr",
        default="tcp://127.0.0.1:7777",
        help="Address to use, default `%(default)s`",
    )
    gr = ap.add_mutually_exclusive_group()
    gr.add_argument(
        "--sync",
        action="store_const",
        dest="mode",
        const=sync_main,
        default=None,
        help="Run synchronous example",
    )
    gr.add_argument(
        "--async",
        action="store_const",
        dest="mode",
        const=async_main,
        help="Run asynchronous example",
    )

    ap.add_argument(
        "--client", action="store_true", default=False, help="Run client part"
    )
    ap.add_argument(
        "--server", action="store_true", default=False, help="Run server part"
    )

    options = ap.parse_args()
    return options.mode(options)


def read_data():
    return input("Enter some phrase: ").encode("utf-8").split()


def sync_main(options):
    print("Running sync at {!r}".format(options.addr))

    ctx = zmq.Context()
    srv_sock = cl_sock = None
    if options.server:
        srv_sock = ctx.socket(zmq.ROUTER)
        srv_sock.bind(options.addr)

    if options.client:
        cl_sock = ctx.socket(zmq.DEALER)
        cl_sock.connect(options.addr)
        data = read_data()
        cl_sock.send_multipart(data)
        print("Sync client write: {!r}".format(data))

    while True:
        if srv_sock:
            try:
                data = srv_sock.recv_multipart(zmq.NOBLOCK)
                print("Sync server read: {!r}".format(data))
                srv_sock.send_multipart(data)
                print("Sync server write: {!r}".format(data))
            except zmq.ZMQError:
                pass
        if cl_sock:
            try:
                data = cl_sock.recv_multipart(zmq.NOBLOCK)
                print("Sync client read: {!r}".format(data))
                return
            except zmq.ZMQError:
                pass
        time.sleep(0.1)


def async_main(options):
    print("Running async at {!r}".format(options.addr))
    loop = asyncio.get_event_loop()

    stop = asyncio.Future()

    async def server():
        router = await aiozmq.create_zmq_stream(zmq.ROUTER, bind=options.addr)
        while True:
            try:
                data = await router.read()
            except asyncio.CancelledError:
                break
            print("Async server read: {!r}".format(data))
            router.write(data)
            print("Async server write: {!r}".format(data))
        router.close()

    async def client():
        dealer = await aiozmq.create_zmq_stream(zmq.DEALER, connect=options.addr)
        data = read_data()
        dealer.write(data)
        print("Async client write: {!r}".format(data))
        echo = await dealer.read()
        print("Async client read: {!r}".format(echo))
        stop.set_result(None)

    tasks = []
    if options.server:
        tasks.append(asyncio.ensure_future(server()))

    if options.client:
        tasks.append(asyncio.ensure_future(client()))

    if tasks:
        try:
            loop.run_until_complete(stop)
        except KeyboardInterrupt:
            loop.call_soon(loop.stop)
            loop.run_forever()
            loop.close()


if __name__ == "__main__":
    main()
