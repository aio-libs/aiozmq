Tulip integration with ZeroMQ
=============================

Experimental Tulip (PEP 3156) compatibility with ZeroMQ.

Event loop
----------

To use tulip with zmq event loop you have to install new event loop::

   import tulip
   import aiozmq

   loop = aiozmq.new_event_loop()
   tulip.set_event_loop(loop)


Usage
-----

Instead of using `zmq.Context` directly, use `aiozmq.Context`.
All `recvXXX` methods of Socket object are coroutines::

  # simple client

  import tulip
  import zmq
  import aiozmq

  @tulip.coroutine
  def read_socket(sock):
      while True:
          msg = yield from sock.recv()

          # do_some_work(msg)

  if __name__ == '__main__':
      loop = aiozmq.new_event_loop()
      tulip.set_event_loop(loop)

      ctx = aiozmq.Context(loop=loop) # create a new context
      sock = ctx.socket(zmq.PULL)
      sock.connect('ipc:///tmp/zmqtest')

      t = tulip.Task(read_socket(sock))
      loop.run_forever()


Requirements
------------

- Python 3.3

- pyzmq 13.1

- tulip http://code.google.com/p/tulip/


License
-------

pyaiozmq is offered under the BSD license.
