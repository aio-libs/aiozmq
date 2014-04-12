import aiozmq
import aiozmq.rpc
import argparse
import asyncio
import gc
import random
import sys
import time
import zmq


def test_raw_zmq(count):
    """raw zmq"""
    ctx = zmq.Context()
    router = ctx.socket(zmq.ROUTER)
    router.bind('tcp://127.0.0.1:*')
    addr = router.getsockopt(zmq.LAST_ENDPOINT).rstrip(b'\0')
    dealer = ctx.socket(zmq.DEALER)
    dealer.connect(addr)
    msg = b'func', b'\0'*200

    gc.collect()
    t1 = time.monotonic()

    for i in range(count):
        dealer.send_multipart(msg)
        addr, m1, m2 = router.recv_multipart()
        router.send_multipart((addr, m1, m2))
        m3 = dealer.recv_multipart()

    t2 = time.monotonic()
    gc.collect()
    return t2 - t1


def test_zmq_with_poller(count):
    """zmq with poller"""
    ctx = zmq.Context()
    router = ctx.socket(zmq.ROUTER)
    router.bind('tcp://127.0.0.1:*')
    addr = router.getsockopt(zmq.LAST_ENDPOINT).rstrip(b'\0')
    dealer = ctx.socket(zmq.DEALER)
    dealer.connect(addr)
    msg = b'func', b'\0'*200

    poller = zmq.Poller()
    poller.register(router)
    poller.register(dealer)

    def skip(event, socket):
        ret = poller.poll()
        assert len(ret) == 1, ret
        while event == ret[0] and socket == ret[1]:
            assert len(ret) == 1, ret
            ret = poller.poll()
        return ret

    gc.collect()
    t1 = time.monotonic()

    for i in range(count):
        dealer.send_multipart(msg, zmq.DONTWAIT)
        ret = skip(zmq.POLLIN, dealer)
        assert ret == [(zmq.POLLIN, router)], ret
        addr, m1, m2 = router.recv_multipart(zmq.NOBLOCK)
        router.send_multipart((addr, m1, m2), zmq.DONTWAIT)
        ret = poller.poll()
        assert ret == [(zmq.POLLIN, dealer)], ret
        m3 = dealer.recv_multipart(zmq.NOBLOCK)

    t2 = time.monotonic()
    gc.collect()
    return t2 - t1


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

        gc.collect()
        t1 = time.monotonic()

        for i in range(count):
            dealer.write(msg)
            yield from queue.get()

        t2 = time.monotonic()
        gc.collect()
        return t2 - t1

    return loop.run_until_complete(go())
    ctx = zmq.Context()
    router = ctx.socket(zmq.ROUTER)
    router.bind('tcp://127.0.0.1:*')
    addr = router.getsockopt(zmq.LAST_ENDPOINT).rstrip(b'\0')
    dealer = ctx.socket(zmq.DEALER)
    dealer.connect(addr)
    msg = b'func', b'\0'*200

    gc.collect()
    t1 = time.monotonic()

    for i in range(count):
        dealer.send_multipart(msg)
        addr, m1, m2 = router.recv_multipart()
        router.send_multipart((addr, m1, m2))
        m3 = dealer.recv_multipart()

    t2 = time.monotonic()
    gc.collect()
    return t2 - t1


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

        gc.collect()
        t1 = time.monotonic()

        for i in range(count):
            ret = yield from client.call.func(data)

        t2 = time.monotonic()
        gc.collect()
        return t2 - t1

    return loop.run_until_complete(go())


ARGS = argparse.ArgumentParser(description="Run benchmark.")
ARGS.add_argument(
    '--count', action="store",
    nargs='?', type=int, default=1000, help='iterations count')
ARGS.add_argument(
    '--tries', action="store",
    nargs='?', type=int, default=10, help='count of tries')


def run_tests(tries, count, funcs):
    results = {func.__doc__: [] for func in funcs}
    print('Run tests')
    test_plan = [func for func in funcs for i in range(tries)]
    random.shuffle(test_plan)
    for test in test_plan:
        gc.collect()
        results[test.__doc__].append(test(count))
        gc.collect()
    return results

def print_results(results):
    for test_name in sorted(results):
        times = results[test_name]
        ave = sum(times)/len(times)
        print('Results for', test_name, 'test')
        print('average: \t{}\nfrom \t{}'.format(ave, times))
        print()


def main(argv):
    args = ARGS.parse_args()

    count = args.count
    tries = args.tries

    res = run_tests(tries, count,
                    [test_raw_zmq,
                     #test_zmq_with_poller,
                     test_aiozmq_rpc, test_core_aiozmq])

    print('benchmark run for {}*{} iterations'.format(tries, count))
    print()

    print_results(res)


if __name__ == '__main__':
    asyncio.set_event_loop_policy(aiozmq.ZmqEventLoopPolicy())
    sys.exit(main(sys.argv))
