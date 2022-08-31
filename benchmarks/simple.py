import aiozmq
import aiozmq.rpc
import argparse
import asyncio
import gc
import multiprocessing
import random
import sys
import threading
import time
import zmq
import uvloop

from scipy.stats import norm, tmean, tvar, tstd
from numpy import array, arange
import matplotlib.pyplot as plt
from matplotlib import cm


def test_raw_zmq(count):
    """single thread raw zmq"""
    print(".", end="", flush=True)
    ctx = zmq.Context()
    router = ctx.socket(zmq.ROUTER)
    router.bind("tcp://127.0.0.1:*")
    address = router.getsockopt(zmq.LAST_ENDPOINT).rstrip(b"\0")
    dealer = ctx.socket(zmq.DEALER)
    dealer.connect(address)
    msg = b"func", b"\0" * 200

    gc.collect()
    t1 = time.monotonic()
    for i in range(count):
        dealer.send_multipart(msg)
        addr, m1, m2 = router.recv_multipart()
        router.send_multipart((addr, m1, m2))
        dealer.recv_multipart()
    t2 = time.monotonic()
    gc.collect()
    router.close()
    dealer.close()
    ctx.destroy()
    return t2 - t1


def test_zmq_with_poller(count):
    """single thread zmq with poller"""
    print(".", end="", flush=True)
    ctx = zmq.Context()
    router = ctx.socket(zmq.ROUTER)
    router.bind("tcp://127.0.0.1:*")
    address = router.getsockopt(zmq.LAST_ENDPOINT).rstrip(b"\0")
    dealer = ctx.socket(zmq.DEALER)
    dealer.connect(address)
    msg = b"func", b"\0" * 200

    poller = zmq.Poller()
    poller.register(router)
    poller.register(dealer)

    def wait(socket, event=zmq.POLLIN):
        while True:
            ret = poller.poll()
            for sock, ev in ret:
                if ev & event and sock == socket:
                    return

    gc.collect()
    t1 = time.monotonic()
    for i in range(count):
        dealer.send_multipart(msg, zmq.DONTWAIT)
        wait(router)
        addr, m1, m2 = router.recv_multipart(zmq.NOBLOCK)
        router.send_multipart((addr, m1, m2), zmq.DONTWAIT)
        wait(dealer)
        dealer.recv_multipart(zmq.NOBLOCK)
    t2 = time.monotonic()
    gc.collect()
    router.close()
    dealer.close()
    ctx.destroy()
    return t2 - t1


def test_zmq_with_thread(count):
    """zmq with threads"""
    print(".", end="", flush=True)
    ctx = zmq.Context()
    dealer = ctx.socket(zmq.DEALER)
    dealer.bind("tcp://127.0.0.1:*")
    address = dealer.getsockopt(zmq.LAST_ENDPOINT).rstrip(b"\0")
    msg = b"func", b"\0" * 200

    def router_thread():
        router = ctx.socket(zmq.ROUTER)
        router.connect(address)

        for i in range(count):
            addr, m1, m2 = router.recv_multipart()
            router.send_multipart((addr, m1, m2))

        router.close()

    th = threading.Thread(target=router_thread)
    th.start()
    gc.collect()
    t1 = time.monotonic()
    for i in range(count):
        dealer.send_multipart(msg)
        dealer.recv_multipart()
    t2 = time.monotonic()
    gc.collect()
    th.join()
    dealer.close()
    ctx.destroy()
    return t2 - t1


class ZmqRouterProtocol(aiozmq.ZmqProtocol):

    transport = None

    def __init__(self, on_close):
        self.on_close = on_close

    def connection_made(self, transport):
        self.transport = transport

    def msg_received(self, msg):
        self.transport.write(msg)

    def connection_lost(self, exc):
        self.on_close.set_result(exc)


class ZmqDealerProtocol(aiozmq.ZmqProtocol):

    transport = None

    def __init__(self, count, on_close):
        self.count = count
        self.on_close = on_close

    def connection_made(self, transport):
        self.transport = transport

    def msg_received(self, msg):
        self.count -= 1
        if self.count:
            self.transport.write(msg)
        else:
            self.transport.close()

    def connection_lost(self, exc):
        self.on_close.set_result(exc)


def test_core_aiozmq_uvloop(count):
    """core aiozmq with uvloop"""
    loop = uvloop.new_event_loop()
    return _test_core_aiozmq(count, loop)


def test_core_aiozmq_loopless(count):
    """core aiozmq loopless"""
    loop = asyncio.new_event_loop()
    return _test_core_aiozmq(count, loop)


def _test_core_aiozmq(count, loop):
    print(".", end="", flush=True)

    async def go():
        router_closed = asyncio.Future()
        dealer_closed = asyncio.Future()
        router, _ = await aiozmq.create_zmq_connection(
            lambda: ZmqRouterProtocol(router_closed),
            zmq.ROUTER,
            bind="tcp://127.0.0.1:*",
            loop=loop,
        )

        addr = next(iter(router.bindings()))
        dealer, _ = await aiozmq.create_zmq_connection(
            lambda: ZmqDealerProtocol(count, dealer_closed),
            zmq.DEALER,
            connect=addr,
            loop=loop,
        )

        msg = b"func", b"\0" * 200

        gc.collect()
        t1 = time.monotonic()
        dealer.write(msg)
        await dealer_closed
        t2 = time.monotonic()
        gc.collect()
        router.close()
        await router_closed
        return t2 - t1

    ret = loop.run_until_complete(go())
    loop.close()
    return ret


def test_core_aiozmq_legacy(count):
    """core aiozmq legacy"""
    print(".", end="", flush=True)
    loop = aiozmq.ZmqEventLoop()

    async def go():
        router_closed = asyncio.Future()
        dealer_closed = asyncio.Future()
        router, _ = await aiozmq.create_zmq_connection(
            lambda: ZmqRouterProtocol(router_closed),
            zmq.ROUTER,
            bind="tcp://127.0.0.1:*",
            loop=loop,
        )

        addr = next(iter(router.bindings()))
        dealer, _ = await aiozmq.create_zmq_connection(
            lambda: ZmqDealerProtocol(count, dealer_closed),
            zmq.DEALER,
            connect=addr,
            loop=loop,
        )

        msg = b"func", b"\0" * 200

        gc.collect()
        t1 = time.monotonic()
        dealer.write(msg)
        await dealer_closed
        t2 = time.monotonic()
        gc.collect()
        router.close()
        await router_closed
        return t2 - t1

    ret = loop.run_until_complete(go())
    loop.close()
    return ret


class Handler(aiozmq.rpc.AttrHandler):
    @aiozmq.rpc.method
    def func(self, data):
        return data


def test_aiozmq_rpc(count):
    """aiozmq.rpc"""
    print(".", end="", flush=True)
    loop = asyncio.new_event_loop()

    async def go():
        server = await aiozmq.rpc.serve_rpc(
            Handler(), bind="tcp://127.0.0.1:*", loop=loop
        )
        addr = next(iter(server.transport.bindings()))
        client = await aiozmq.rpc.connect_rpc(connect=addr, loop=loop)

        data = b"\0" * 200

        gc.collect()
        t1 = time.monotonic()
        for i in range(count):
            await client.call.func(data)
        t2 = time.monotonic()
        gc.collect()
        server.close()
        await server.wait_closed()
        client.close()
        await client.wait_closed()
        return t2 - t1

    ret = loop.run_until_complete(go())
    loop.close()
    return ret


avail_tests = {
    f.__name__: f
    for f in [
        test_raw_zmq,
        test_zmq_with_poller,
        test_aiozmq_rpc,
        test_core_aiozmq_legacy,
        test_core_aiozmq_uvloop,
        test_core_aiozmq_loopless,
        test_zmq_with_thread,
    ]
}


ARGS = argparse.ArgumentParser(description="Run benchmark.")
ARGS.add_argument(
    "-n",
    "--count",
    action="store",
    nargs="?",
    type=int,
    default=1000,
    help="iterations count",
)
ARGS.add_argument(
    "-t",
    "--tries",
    action="store",
    nargs="?",
    type=int,
    default=30,
    help="count of tries",
)
ARGS.add_argument(
    "-p",
    "--plot-file-name",
    action="store",
    type=str,
    default=None,
    dest="plot_file_name",
    help="file name for plot",
)
ARGS.add_argument("-v", "--verbose", action="count", help="verbosity level")
ARGS.add_argument(
    "--without-multiprocessing",
    action="store_false",
    default=True,
    dest="use_multiprocessing",
    help="don't use multiprocessing",
)
ARGS.add_argument(
    dest="tests",
    type=str,
    nargs="*",
    help="tests, {} by default".format(list(sorted(avail_tests))),
)


def run_tests(tries, count, use_multiprocessing, funcs):
    results = {func.__doc__: [] for func in funcs}
    queue = []
    print("Run tests for {}*{} iterations: {}".format(tries, count, sorted(results)))
    test_plan = [func for func in funcs for i in range(tries)]
    random.shuffle(test_plan)

    if use_multiprocessing:
        with multiprocessing.Pool() as pool:
            for test in test_plan:
                res = pool.apply_async(test, (count,))
                queue.append((test.__doc__, res))
            pool.close()
            pool.join()
        for name, res in queue:
            results[name].append(res.get())
    else:
        for test in test_plan:
            results[test.__doc__].append(test(count))
    print()
    return results


def print_and_plot_results(count, results, verbose, plot_file_name):
    print("RPS calculated as 95% confidence interval")

    rps_mean_ar = []
    rps_err_ar = []
    test_name_ar = []

    for test_name in sorted(results):
        data = results[test_name]
        rps = count / array(data)
        rps_mean = tmean(rps)
        rps_var = tvar(rps)
        low, high = norm.interval(0.95, loc=rps_mean, scale=rps_var**0.5)
        times = array(data) * 1000000 / count
        times_mean = tmean(times)
        times_stdev = tstd(times)
        print("Results for", test_name)
        print(
            "RPS: {:d}: [{:d}, {:d}],\tmean: {:.3f} μs,"
            "\tstandard deviation {:.3f} μs".format(
                int(rps_mean), int(low), int(high), times_mean, times_stdev
            )
        )

        test_name_ar.append(test_name)
        rps_mean_ar.append(rps_mean)
        rps_err_ar.append(high - rps_mean)

        if verbose:
            print("    from", times)
        print()

    if plot_file_name is not None:
        fig = plt.figure()
        ax = fig.add_subplot(111)
        L = len(rps_mean_ar)
        color = [cm.autumn(float(c) / (L - 1)) for c in arange(L)]
        bars = ax.bar(arange(L), rps_mean_ar, color=color, yerr=rps_err_ar, ecolor="k")
        # order of legend is reversed for visual appeal
        ax.legend(
            reversed(bars), reversed(test_name_ar), loc="upper left", framealpha=0.5
        )
        ax.get_xaxis().set_visible(False)
        plt.ylabel("Requets per Second", fontsize=16)
        plt.savefig(plot_file_name, dpi=300)
        print("Plot is saved to {}".format(plot_file_name))
        if verbose:
            plt.show()


def main(argv):
    args = ARGS.parse_args()

    count = args.count
    tries = args.tries
    verbose = args.verbose
    plot_file_name = args.plot_file_name
    use_multiprocessing = args.use_multiprocessing
    tests = args.tests
    if tests:
        tests = [avail_tests[t] for t in tests]
    else:
        tests = avail_tests.values()

    res = run_tests(tries, count, use_multiprocessing, tests)

    print()

    print_and_plot_results(count, res, verbose, plot_file_name)


if __name__ == "__main__":
    asyncio.set_event_loop(None)
    sys.exit(main(sys.argv))
