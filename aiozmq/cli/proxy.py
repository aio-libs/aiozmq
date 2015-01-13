import zmq
import sys
import argparse
from datetime import datetime


def get_arguments():
    ap = argparse.ArgumentParser(description="ZMQ Proxy tool")

    def common_arguments(ap):
        ap.add_argument('--front-bind', metavar="ADDR", action='append',
                        help="Binds frontend socket to specified address")
        ap.add_argument('--front-connect', metavar="ADDR", action='append',
                        help="Connects frontend socket to specified address")

        ap.add_argument('--back-bind', metavar="ADDR", action='append',
                        help="Binds backend socket to specified address")
        ap.add_argument('--back-connect', metavar="ADDR", action='append',
                        help="Connects backend socket to specified address")

        ap.add_argument('--monitor-bind', metavar="ADDR", action='append',
                        help="Creates and binds monitor socket"
                             " to specified address")
        ap.add_argument('--monitor-connect', metavar="ADDR", action='append',
                        help="Creates and connects monitor socket"
                             " to specified address")

    parsers = ap.add_subparsers(
        title="Commands", help="ZMQ Proxy tool commands")

    sub = parsers.add_parser(
        'queue',
        help="Creates Shared Queue proxy"
             " (frontend/backend sockets are ZMQ_ROUTER/ZMQ_DEALER)")
    sub.set_defaults(sock_types=(zmq.ROUTER, zmq.DEALER),
                     action=serve_proxy)
    common_arguments(sub)
    sub = parsers.add_parser(
        'forwarder',
        help="Creates Forwarder proxy"
             " (frontend/backend sockets are ZMQ_XSUB/ZMQ_XPUB)")
    sub.set_defaults(sock_types=(zmq.XSUB, zmq.XPUB),
                     action=serve_proxy)
    common_arguments(sub)
    sub = parsers.add_parser(
        'streamer',
        help="Creates Streamer proxy"
             " (frontend/backend sockets are ZMQ_PULL/ZMQ_PUSH)")
    sub.set_defaults(sock_types=(zmq.PULL, zmq.PUSH),
                     action=serve_proxy)
    common_arguments(sub)

    sub = parsers.add_parser(
        'monitor',
        help="Connects/binds to monitor socket and dumps all traffic")
    sub.set_defaults(action=monitor)
    sub.add_argument('--connect', metavar="ADDR",
                     help="Connect to monitor socket")
    sub.add_argument('--bind', metavar="ADDR",
                     help="Bind monitor socket")
    return ap


def main():
    ap = get_arguments()
    options = ap.parse_args()
    options.action(options)


def serve_proxy(options):
    if not (options.front_connect or options.front_bind):
        print("No frontend socket address specified!", file=sys.stderr)
        sys.exit(1)
    if not (options.back_connect or options.back_bind):
        print("No backend socket address specified!", file=sys.stderr)
        sys.exit(1)

    ctx = zmq.Context().instance()

    front_type, back_type = options.sock_types

    front = ctx.socket(front_type)
    back = ctx.socket(back_type)

    if options.monitor_bind or options.monitor_connect:
        monitor = ctx.socket(zmq.PUB)
        bind_connect(monitor, options.monitor_bind, options.monitor_connect)
    else:
        monitor = None

    bind_connect(front, options.front_bind, options.front_connect)
    bind_connect(back, options.back_bind, options.back_connect)
    try:
        if monitor:
            zmq.proxy(front, back, monitor)
        else:
            zmq.proxy(front, back)
    except:
        return
    finally:
        front.close()
        back.close()


def bind_connect(sock, bind=None, connect=None):
    if bind:
        for address in bind:
            sock.bind(address)
    if connect:
        for address in connect:
            sock.connect(address)


def monitor(options):
    ctx = zmq.Context.instance()
    sock = ctx.socket(zmq.SUB)

    bind = [options.bind] if options.bind else []
    connect = [options.connect] if options.connect else []
    bind_connect(sock, bind, connect)
    sock.setsockopt(zmq.SUBSCRIBE, b'')

    try:
        while True:
            try:
                data = sock.recv()
            except KeyboardInterrupt:
                break
            except Exception as err:
                print("Error receiving message: {!r}".format(err))
            else:
                print(datetime.now().isoformat(),
                      "Message received: {!r}".format(data))
    finally:
        sock.close()
        ctx.term()


if __name__ == "__main__":
    main()
