import tulip
import zmq
import zmqtulip

loop = zmqtulip.new_event_loop()
tulip.set_event_loop(loop)

# server
print(zmqtulip.Context)
ctx = zmqtulip.Context()
sock1 = ctx.socket(zmq.PUSH)
sock1.bind('ipc:///tmp/zmqtest')


def send_data():
    sock1.send_pyobj(('this', 'is', 'a', 'python', 'tuple'))
    yield from tulip.sleep(1.0)
    sock1.send_pyobj({'hi': 1234})
    yield from tulip.sleep(1.0)
    sock1.send_pyobj(
        ({'this': ['is a more complicated object', ':)']}, 42, 42, 42))
    yield from tulip.sleep(1.0)
    sock1.send_pyobj('foobar')
    yield from tulip.sleep(1.0)
    sock1.send_pyobj('quit')


# client
ctx = zmqtulip.Context()  # create a new context to kick the wheels
sock2 = ctx.socket(zmq.PULL)
sock2.connect('ipc:///tmp/zmqtest')


def get_objs(sock):
    while True:
        o = yield from sock.recv_pyobj()
        print('received python object:', o)
        if o == 'quit':
            print('exiting.')
            break


def print_every(s, t=None):
    while 1:
        print(s)
        yield from tulip.sleep(t)


t0 = tulip.Task(send_data())
t1 = tulip.Task(print_every('printing every half second', 0.5))
t2 = tulip.Task(get_objs(sock2))

loop.run_until_complete(t2)
