.. _aiozmq-rpc:

:mod:`aiozmq.rpc` --- Remote Procedure Calls
============================================

.. module:: aiozmq.rpc
   :synopsis: RPC for ZeroMQ transports
.. currentmodule:: aiozmq.rpc


Intro
-----

While :ref:`low-level API <aiozmq-low-level>` provides core support for
:term:`ZeroMQ` transports an :term:`End User <enduser>` usually needs for
some high-level API.

Thus we have the :mod:`aiozmq.rpc` for Remote Procedure Calls.

The main goal of the module is to provide *easy-to-use interface* for
calling some method from remote process, which may be
started on other host.

:term:`ZeroMQ` itself gives handy sockets but says nothing about RPC.

In other hand this module provides human API but is not compatible with
other implementations.

If you need to support some RPC protocol over ZeroMQ layer please feel
free to build your own implementation on top of :ref:`low level
primitives <aiozmq-low-level>`.

This module uses :term:`ZeroMQ` *DEALER*/*ROUTER* sockets and custom
communication protocol (which uses :term:`msgpack` by the way).


.. _aiozmq-rpc-client:

RPC Client
----------

The basic usage is::

   import asyncio
   from aiozmq import rpc

   @asyncio.coroutine
   def func():
       client = yield from rpc.open_client(connect='tcp://127.0.0.1:5555')

       val = yield from client.rpc.func1(arg1, arg2)

       client.close()
       yield from client.wait_closed()


    event_loop.run_until_complete(func())


.. function:: open_client(*, connect=None, bind=None, loop=None, \
                          error_table=None)

    A :ref:`coroutine<coroutine>` that creates and connects/binds RPC client.

    Usually for this function you need to use *connect* parameter, but
    :term:`ZeroMQ` does not forbid to use *bind*.

    Either *connect* or *bind* parameter should be not *None*.

    .. seealso:: Please take a look on
       :meth:`aiozmq.ZmqEventLoop.create_zmq_connection` for valid
       values to *connect* and *bind* parameters.

    :param aiozmq.ZmqEventLoop loop: an optional parameter to point
       :ref:`asyncio-event-loop`.  if *loop* is *None* then default
       event loop will be given by :func:`asyncio.get_event_loop` call.

    :param dict error_table: an optional table for custom exception translators.

       .. seealso:: :ref:`aiozmq-rpc-exception-translation`

    :return: :class:`RPCClient` instance.


.. class:: RPCClient

   Class that returned by :func:`open_client` call. Implements
   :class:`asyncio.AbstractServer` interface providing
   :meth:`RPCClient.close` and :meth:`RPCClient.wait_closed` methods.

   For RPC calls use :attr:`~RPCClient.rpc` property.

   .. attribute:: rpc

      The readonly property that returns ephemeral object used to making
      RPC call.

      Construction like::

          ret = yield from client.rpc.ns.method(1, 2, 3)

      makes a remote call with arguments(1, 2, 3) and returns answer
      from this call.

      You can also pass *named parameters*::

          ret = yield from client.rpc.ns.method(1, b=2, c=3)

      If the call raises exception that exception propagates to client side.

      Say, if remote raises :class:`ValueError` client catches
      *ValueError* instance with *args* sent by remote::

          try:
              yield from client.rpc.raise_value_error()
          except ValueError as exc:
              process_error(exc)

      .. seealso::
         :ref:`aiozmq-rpc-exception-translation` and
         :ref:`aiozmq-rpc-signature-validation`

   .. warning::

      You should never instantiate :class:`RPCClient` by hand, use
      :func:`open_client` instead.

.. _aiozmq-rpc-server:

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
       return yield from rpc.start_server(Handler(),
                                          bind='tcp://127.0.0.1:5555')

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

    .. seealso:: Please take a look on
       :meth:`aiozmq.ZmqEventLoop.create_zmq_connection` for valid
       values to *connect* and *bind* parameters.

    :param AbstractHander handler:

       instance of :class:`AbstractHander` which processes incoming
       RPC calls.

      Usually you like to pass :class:`AttrHandler` instance.

    :return: :class:`asyncio.AbstractServer` instance.

RPC exceptions
--------------

.. exception:: Error

   Base class for :mod:`aiozmq.rpc` exceptions. Derived from :exc:`Exception`.

.. exception:: GenericError

   Subclass of :exc:`Error`, raised when a remote call producess
   exception which cannot be translated.

   .. seealso:: :ref:`aiozmq-rpc-exception-translation`

.. exception:: NotFoundError

   Subclass of both :exc:`Error` and :exc:`LookupError`, raised when a
   remote call name is not found at RPC server.

.. exception:: ParameterError

   Subclass of both :exc:`Error` and :exc:`ValueError`, raised by
   remote call when parameter substitution or :ref:`remote method
   signature validation <aiozmq-rpc-signature-validation>` is failed.

.. _aiozmq-rpc-exception-translation:

RPC exception translation at client side
----------------------------------------

If remote server method raises an exception that exception is passed
back to client and raised on client side, as follows::

    try:
        yield from client.rpc.func_raises_value_error()
    except ValueError as exc:
        log.exception(exc)

The rule for exception translation is:

   * if remote method raises an exception server answers with *full
     exception class name* (like ``package.subpackage.MyError``) and
     *exception constructor arguments* (:attr:`~BaseException.args`).
   * *translator table* is a *mapping* of ``{name: exc_class}`` where
     keys are *full names* of exception class (str) and values are
     exception classes.
   * if translation is found then client code got exception ``raise
     exc_class(args)``.
   * user defined translators are searched first.
   * all :ref:`builtin exceptions <bltin-exceptions>` are translated.
   * :exc:`NotFoundError` and :exc:`ParameterError` are translated.
   * if there is no registered traslation then
     ``GenericError(name, args)`` is raised at client side.

For example if custom RPC server handler can raise ``mod1.Error1`` and
``pack.mod2.Error2`` then *error_table* should be::

    {'mod1.Error1': Error1,
     'pack.mod2.Error2': Error2}

.. seealso:: :func:`open_client` function.

.. _aiozmq-rpc-signature-validation:

RPC signature validation
------------------------

The library supports **optional** validation of remote call signatures.

If validation fails :exc:`ParameterError` raises on client side.

All validations are done on RPC server side, than errors translated
back to client.

Let's take a look on example of user-defined RPC handler::

   class Handler(rpc.AttrHandler):

       @rpc.method
       def func(self, arg1: int, arg2) -> float:
           return arg1 + arg2

*Parameter* *arg1* and *return value* has :term:`annotaions <annotaion>`,
*int* and *float* correspondingly.

At call time if *parameter* has an *annotaion* then *actual value* passed to
RPC method is calculated as ``actual_value = annotation(value)``. If
there is no annotaion for parameter the value is passed as-is.

Annotaion should be any *callable* that accepts a value as single argument
and returns *actual value*.

If annotation call raises exception that exception throws to client
wrapped in :exc:`ParameterError`.

Value, returned by RPC call, can be checked by optional *return annotation*.

Thus :class:`int` can be good annotation: it raises :exc:`TypeError`
if *arg1* cannot be converted to *int*.

Often you need for more complex check, say parameter can be *int* or *None*.

You always can write custom validators::

   def int_or_none(val):
      if isinstance(val, int) or val is None:
          return val
      else:
          raise ValueError('bad value')

   class Handler(rpc.AttrHandler):

       @rpc.method
       def func(self, arg: int_or_none):
           return arg

Writing a tons of custom validators is inconvinient, so we recommend
to use :term:`trafaret` library (can be installed via ``pip3 install
trafaret``).

There is examples of trararet annotations::

   import trafaret as t

   class Handler(rpc.AttrHandler):

       @rpc.method
       def func(self, arg: t.Int|t.Null):
           return arg

Trafaret has advanced types like *List* and *Dict*, so you can put
structure of your complex JSON-like structure as RPC method
annotation. Also you can create custom trafaret classes if needed.

.. _aiozmq-rpc-custom-object-hooks:

RPC custom object hooks
-----------------------

aiozmq.rpc uses :term:`msgpack` for transfering python objects from
client to server and back.

You can think about :term:`msgpack` as: this is a-like JSON but fast
and compact.

Every object that can be passed to :func:`json.dump` can be passed to
:func:`msgpack.dump` also. The same for unpacking.

But sometimes you want to call remote side with *non-plain-json* arguments.

:class:`datetime.datetime` is a good example.

:mod:`aiozmq.rpc` supports all family of dates, times and timezones
from :mod:`datetime` *in-the-box*.

If you need to transfer a custom object via RPC you should to register
**translator** at both server and client side.
