asyncio integration with ZeroMQ
=============================

Experimental asyncio (PEP 3156) compatibility with ZeroMQ.

Event loop
----------

To use asyncio with zmq event loop you have to install new event loop::

   import asyncio
   import aiozmq

   loop = aiozmq.new_event_loop()
   asyncio.set_event_loop(loop)


Usage
-----

Instead of using `zmq.Context` directly, use `aiozmq.Context`.
All `recvXXX` methods of Socket object are coroutines::

  # simple client

  import asyncio
  import zmq
  import aiozmq

  @asyncio.coroutine
  def read_socket(sock):
      while True:
          msg = yield from sock.recv()

          # do_some_work(msg)

  if __name__ == '__main__':
      loop = aiozmq.new_event_loop()
      asyncio.set_event_loop(loop)

      ctx = aiozmq.Context(loop=loop) # create a new context
      sock = ctx.socket(zmq.PULL)
      sock.connect('ipc:///tmp/zmqtest')

      t = asyncio.Task(read_socket(sock))
      loop.run_forever()


Requirements
------------

- Python 3.3+

- pyzmq 13.1

- asyncio http://code.google.com/p/tulip/ or Python 3.4+



License
-------

aiozmq is offered under the BSD license.
