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

   .. attribute:: exc_type

      A string contains *full name* of unknown
      exception(``"package.module.MyError"``).

   .. attribute:: arguments

      A tuple of arguments passed to *unknown exception* constructor

      .. seealso:: :attr:`parameters for exception constructor
                   <BaseException.args>`

   .. seealso:: :ref:`aiozmq-rpc-exception-translation`

.. exception:: NotFoundError

   Subclass of both :exc:`Error` and :exc:`LookupError`, raised when a
   remote call name is not found at RPC server.

.. exception:: ParameterError

   Subclass of both :exc:`Error` and :exc:`ValueError`, raised by
   remote call when parameter substitution or :ref:`remote method
   signature validation <aiozmq-rpc-signature-validation>` is failed.

.. exception:: ServiceClosedError

   Subclass of :exc:`Error`, raised :class:`Service` has been closed.

   .. seealso::

      :attr:`Service.transport`


RPC clases
----------

.. class:: Service

   RPC service base class.

   Instances of *Service* (or descendants) are returned by
   coroutines that creates clients or servers (:func:`open_client`,
   :func:`start_server` and others).

   Implements :class:`asyncio.AbstractServer`.

   .. attribute:: transport

      The readonly property that returns service's :class:`transport
      <aiozmq.ZmqTransport>`.

      You can use the transport to dynamically bind/unbind,
      connect/disconnect etc.

      :raise aiozmq.rpc.ServiceClosedError: if the service has been closed.

   .. method:: close()

      Stop serving.

      This leaves existing connections open.

   .. method:: wait_closed()

      :ref:`Coroutine <coroutine>` to wait until service is closed.

   .. warning:: You should never instantiate :class:`Service` by hand.

.. class:: RPCClient

   Class that returned by :func:`open_client` call. Inherited from
   :class:`Service`.

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

.. _aiozmq-rpc-exception-translation:

RPC exception translation at client side
----------------------------------------

If remote server method raises an exception that error is passed
back to client and raised on client side, as follows::

    try:
        yield from client.rpc.func_raises_value_error()
    except ValueError as exc:
        log.exception(exc)

The rule for exception translation is:
   * if remote method raises an exception --- server answers with
     *full exception class name* (like ``package.subpackage.MyError``)
     and *exception constructor arguments*
     (:attr:`~BaseException.args`).
   * *translator table* is a *mapping* of ``{excpetion_name:
     exc_class}`` where keys are *full names* of exception class (str)
     and values are exception classes.
   * if translation is found then client code gives exception ``raise
     exc_class(args)``.
   * user defined translators are searched first.
   * all :ref:`builtin exceptions <bltin-exceptions>` are translated.
   * :exc:`NotFoundError` and :exc:`ParameterError` are translated.
   * if there is no registered traslation then
     ``GenericError(excpetion_name, args)`` is raised.

For example if custom RPC server handler can raise ``mod1.Error1`` and
``pack.mod2.Error2`` then *error_table* should be::

    from mod1 import Error1
    from pack.mod2 import Error2

    error_table = {'mod1.Error1': Error1,
                   'pack.mod2.Error2': Error2}

    client = loop.run_until_complete(
        rpc.open_client(connect='tcp://127.0.0.1:5555',
                        error_table=error_table))

You have to have the way to import exception classes from server-side.
Or you can build your own translators without server-side code, use
only string for *full exception class name* and tuple of *args* ---
that's up to you.

.. seealso:: *error_table* argument in :func:`open_client` function.

.. _aiozmq-rpc-signature-validation:

RPC signature validation
------------------------

The library supports **optional** validation of remote call signatures.

If validation fails then :exc:`ParameterError` raises on client side.

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

Usually you need for more complex check, say parameter can be *int* or
*None*.

You always can write custom validator::

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

This is example of trararet annotation::

   import trafaret as t

   class Handler(rpc.AttrHandler):
       @rpc.method
       def func(self, arg: t.Int|t.Null):
           return arg

Trafaret has advanced types like *List* and *Dict*, so you can put
your complex JSON-like structure as RPC method annotation. Also you
can create custom trafarets if needed. It's easy, trust me.

.. _aiozmq-rpc-value-translators:

RPC value translators
---------------------

aiozmq.rpc uses :term:`msgpack` for transfering python objects from
client to server and back.

You can think about :term:`msgpack` as: this is a-like JSON but fast
and compact.

Every object that can be passed to :func:`json.dump` can be passed to
:func:`msgpack.dump` also. The same for unpacking.

The only difference is: *aiozmq.rpc* converts all :class:`lists
<list>` to :class:`tuples <tuple>`.

The reasons is are:

  * you never need to modify given list as it is your *incoming*
    value.  If you still need to use :class:`list` data type you can
    easy do it by ``list(val)`` call.
  * tuples a bit faster for unpacking.
  * tuple can be a *key* in :class:`dict`, so you can pack something
    like ``{(1,2): 'a'}`` and unpack it on other side without any
    error. Lists cannot be *keys* in dicts, they are unhashable.

    This is the main reason for choosing tuples. Unfortunatelly
    msgpack gives no way to mix tuples and lists in the same pack.

But sometimes you want to call remote side with *non-plain-json* arguments.

:class:`datetime.datetime` is a good example.

:mod:`aiozmq.rpc` supports all family of dates, times and timezones
from :mod:`datetime` *in-the-box*.

If you need to transfer a custom object via RPC you should to register
**translator** at both server and client side.
