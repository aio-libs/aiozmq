import aiozmq
import aiozmq.rpc
import argparse
import asyncio
import gc
import random
import sys
import threading
import time
import zmq


def test_raw_zmq(count):
    """single thread raw zmq"""
    ctx = zmq.Context()
    router = ctx.socket(zmq.ROUTER)
    router.bind('tcp://127.0.0.1:*')
    address = router.getsockopt(zmq.LAST_ENDPOINT).rstrip(b'\0')
    dealer = ctx.socket(zmq.DEALER)
    dealer.connect(address)
    msg = b'func', b'\0'*200

    for i in range(count):
        dealer.send_multipart(msg)
        addr, m1, m2 = router.recv_multipart()
        router.send_multipart((addr, m1, m2))
        dealer.recv_multipart()


def test_zmq_with_poller(count):
    """single thread zmq with poller"""
    ctx = zmq.Context()
    router = ctx.socket(zmq.ROUTER)
    router.bind('tcp://127.0.0.1:*')
    address = router.getsockopt(zmq.LAST_ENDPOINT).rstrip(b'\0')
    dealer = ctx.socket(zmq.DEALER)
    dealer.connect(address)
    msg = b'func', b'\0'*200

    poller = zmq.Poller()
    poller.register(router)
    poller.register(dealer)

    def wait(socket, event=zmq.POLLIN):
        while True:
            ret = poller.poll()
            for sock, ev in ret:
                if ev & event and sock == socket:
                    return

    for i in range(count):
        dealer.send_multipart(msg, zmq.DONTWAIT)
        wait(router)
        addr, m1, m2 = router.recv_multipart(zmq.NOBLOCK)
        router.send_multipart((addr, m1, m2), zmq.DONTWAIT)
        wait(dealer)
        dealer.recv_multipart(zmq.NOBLOCK)


def test_zmq_with_thread(count):
    """zmq with threads"""
    ctx = zmq.Context()
    dealer = ctx.socket(zmq.DEALER)
    dealer.bind('tcp://127.0.0.1:*')
    address = dealer.getsockopt(zmq.LAST_ENDPOINT).rstrip(b'\0')
    msg = b'func', b'\0'*200

    def router_thread():
        router = ctx.socket(zmq.ROUTER)
        router.connect(address)

        for i in range(count):
            addr, m1, m2 = router.recv_multipart()
            router.send_multipart((addr, m1, m2))

    th = threading.Thread(target=router_thread)
    th.start()
    for i in range(count):
        dealer.send_multipart(msg)
        dealer.recv_multipart()
    th.join()


class ZmqRouterProtocol(aiozmq.ZmqProtocol):

    transport = None

    def connection_made(self, transport):
        self.transport = transport

    def msg_received(self, msg):
        self.transport.write(msg)


class ZmqDealerProtocol(aiozmq.ZmqProtocol):

    transport = None

    def __init__(self, queue):
        self.queue = queue

    def connection_made(self, transport):
        self.transport = transport

    def msg_received(self, msg):
        self.queue.put_nowait(msg)


def test_core_aiozmq(count):
    """core aiozmq"""
    loop = asyncio.get_event_loop()

    @asyncio.coroutine
    def go():
        router, _ = yield from loop.create_zmq_connection(
            ZmqRouterProtocol,
            zmq.ROUTER,
            bind='tcp://127.0.0.1:*')

        addr = next(iter(router.bindings()))
        queue = asyncio.Queue()
        dealer, _ = yield from loop.create_zmq_connection(
            lambda: ZmqDealerProtocol(queue),
            zmq.DEALER,
            connect=addr)

        msg = b'func', b'\0'*200

        for i in range(count):
            dealer.write(msg)
            yield from queue.get()

    loop.run_until_complete(go())


class Handler(aiozmq.rpc.AttrHandler):

    @aiozmq.rpc.method
    def func(self, data):
        return data


def test_aiozmq_rpc(count):
    """aiozmq.rpc"""
    loop = asyncio.get_event_loop()

    @asyncio.coroutine
    def go():
        server = yield from aiozmq.rpc.serve_rpc(Handler(),
                                                 bind='tcp://127.0.0.1:*')
        addr = next(iter(server.transport.bindings()))
        client = yield from aiozmq.rpc.connect_rpc(connect=addr)

        data = b'\0'*200

        for i in range(count):
            yield from client.call.func(data)

    loop.run_until_complete(go())


ARGS = argparse.ArgumentParser(description="Run benchmark.")
ARGS.add_argument(
    '-n', '--count', action="store",
    nargs='?', type=int, default=1000, help='iterations count')
ARGS.add_argument(
    '-t', '--tries', action="store",
    nargs='?', type=int, default=10, help='count of tries')
ARGS.add_argument(
    '-v', '--verbose', action="count",
    help='count of tries')


def run_tests(tries, count, funcs):
    results = {func.__doc__: [] for func in funcs}
    print('Run tests for {}*{} iterations: {}'
          .format(tries, count, sorted(results)))
    test_plan = [func for func in funcs for i in range(tries)]
    random.shuffle(test_plan)
    for test in test_plan:
        print('.', end='', flush=True)
        gc.collect()
        t1 = time.monotonic()
        test(count)
        t2 = time.monotonic()
        gc.collect()
        results[test.__doc__].append(t2 - t1)
    print()
    return results


def print_results(count, results, verbose):
    for test_name in sorted(results):
        times = results[test_name]
        ave = sum(times)/len(times)
        print('Results for', test_name, 'test')
        print('RPS: {:d},\t average: {:.3f} ms'.format(int(count/ave),
                                                       ave*1000/count))
        if verbose:
            print('    from', times)
        print()


def main(argv):
    args = ARGS.parse_args()

    count = args.count
    tries = args.tries
    verbose = args.verbose

    res = run_tests(tries, count,
                    [test_raw_zmq, test_zmq_with_poller,
                     test_aiozmq_rpc, test_core_aiozmq,
                     test_zmq_with_thread])

    print()

    print_results(count, res, verbose)


if __name__ == '__main__':
    asyncio.set_event_loop_policy(aiozmq.ZmqEventLoopPolicy())
    sys.exit(main(sys.argv))
