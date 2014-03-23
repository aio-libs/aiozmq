.. _aiozmq-rpc:

:mod:`aiozmq.rpc` --- Remote Procedure Calls
============================================

.. module:: aiozmq.rpc
   :synopsis: RPC for ZeroMQ transports
.. currentmodule:: aiozmq.rpc


Intro
-----

While :ref:`low-level API <aiozmq-low-level>` provides core support for
:term:`ZeroMQ` transports :term:`End User <enduser>` usually need for
some high-level API.

Thus we have :mod:`aiozmq.rpc` for Remote Procedure Calls.

The main goal of module is to provide *easy-to-use interface* for calling
some method from remote process, which probably has been started on other
machine.

:term:`ZeroMQ` itself gives handy sockets but says nothing about RPC.

In other hand this module provides human API but it's compatible with
our implementaion only.

If you need something other please feel free to build your own
implementation based on :ref:`low level primitives <aiozmq-low-level>`.

This module uses :term:`ZeroMQ` *DEALER*/*ROUTER* sockets and custom
communication protocol (which use :term:`msgpack`).


RPC Client
----------

The basic usage is::

   import asyncio
   from aiozmq import rpc

   @asyncio.coroutine
   def func():
       client = yield from open_client(connect='tcp://127.0.0.1:5555')

       val = yield from client.rpc.func1(arg1, arg2)

       client.close()
       yield from client.wait_closed()


    event_loop.run_until_complete(func())

.. function:: open_client(*, connect=None, bind=None, loop=None)

    A :ref:`coroutine<coroutine>` that creates and connects/binds RPC client.

    Usually for this function you need to use *connect* parameter, but
    :term:`ZeroMQ` does not forbid to use *bind*.

    Either *connect* or *bind* parameter should be not *None*.

    Please take a look on
    :meth:`aiozmq.ZmqEventLoop.create_zmq_connection` for valid values
    to *connect* and *bind* parameters.

    :return: :class:`RPCClient` instance.


.. class:: RPCClient

   Class that returned by :func:`open_client` call. Implements
   :class:`asyncio.AbstractServer` interface providing
   :meth:`RPCClient.close` and :meth:`RPCClient.wait_closed` methods.

   For RPC calls has :attr:`RPCClient.rpc` property.

   .. warning::

      You should never create this class instance by hand. Use
      :func:`open_client` instead.

   .. attribute:: rpc

      Readonly property that returns ephemeral object used to making
      RPC call (see example above).


RPC Server
----------

To start RPC server you need to create handler and pass it into start_server::

   import asyncio
   from aiozmq import rpc


   class Handler(rpc.AttrHandler):

       def __init__(self):
           self.inner = SubHandler()

       @rpc.method
       def func(self, arg1, arg2):
           return arg1 + arg2

       @rpc.method
       def bad(self):
           raise RuntimeError("Bad method")

       @rpc.method
       @asyncio.coroutine
       def coro(self):
           ret = yield from some_long_running()
           return ret

   class SubHandler(rpc.AttrHandler):

       @rpc.method
       def inner_func(self):
           return 'inner'


   @asyncio.coroutine
   def start():
       return yield from start_server(Handler(), bind='tcp://127.0.0.1:5555')

   @asyncio.coroutine
   def stop(server):
       server.close()
       yield from server.wait_closed()

   server = event_loop.run_until_complete(start())
   event_loop.run_until_complete(stop(server))


.. function:: start_server(handler, *, connect=None, bind=None, loop=None)

    A :ref:`coroutine<coroutine>` that creates and connects/binds RPC
    server instance.

    Usually for this function you need to use *bind* parameter, but
    :term:`ZeroMQ` does not forbid to use *connect*.

    Either *connect* or *bind* parameter should be not *None*.

    Please take a look on
    :meth:`aiozmq.ZmqEventLoop.create_zmq_connection` for valid values
    to *connect* and *bind* parameters.

    :param AbstractHander handler:

       instance of :class:`AbstractHander` which processes incoming
       RPC calls.

      Usually you like to pass :class:`AttrHandler` instance.

    :return: :class:`asyncio.AbstractServer` instance.