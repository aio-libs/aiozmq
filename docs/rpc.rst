.. _aiozmq-rpc:

:mod:`aiozmq.rpc` --- Remote Procedure Calls
============================================

.. module:: aiozmq.rpc
   :synopsis: RPC for ZeroMQ transports
.. currentmodule:: aiozmq.rpc


Intro
-----

While :ref:`core API <aiozmq-core>` provides a core support for
:term:`ZeroMQ` transports, the :term:`End User <enduser>` may need
some high-level API.

Thus we have the *aiozmq.rpc* module for Remote Procedure Calls.

The main goal of the module is to provide *easy-to-use interface* for
calling some method from the remote process (which can be
running on the other host).

:term:`ZeroMQ` itself gives some handy sockets but says nothing about RPC.

On the other hand, this module provides *human* API, but it is not
compatible with *other implementations*.

If you need to support a custom protocol over :term:`ZeroMQ` layer,
please feel free to build your own implementation on top of the
:ref:`core primitives <aiozmq-core>`.

The :mod:`aiozmq.rpc` supports three pairs of communications:
   * :ref:`aiozmq-rpc-rpc`
   * :ref:`aiozmq-rpc-pushpull`
   * :ref:`aiozmq-rpc-pubsub`

.. warning:: :mod:`aiozmq.rpc` module is **optional** and requires
   :term:`msgpack`. You can install *msgpack-python* by::

       pip3 install msgpack-python


.. _aiozmq-rpc-rpc:

Request-Reply
-------------

This is a **Remote Procedure Call** pattern itself. Client calls a remote
function on server and waits for the returned value. If the remote function
raises an exception, that exception instance also raises on the client side.

Let's assume we have *N* clients bound to *M* servers.  Any client can
connect to several servers and any server can listen to multiple
*endpoints*.

When client sends a message, the message will be delivered to any server
that is ready (doesn't processes another message).

When the server sends a reply with the result of the remote call back, the result is
routed to the client that has sent the request originally.

This pair uses *DEALER*/*ROUTER* :term:`ZeroMQ` sockets.


The basic usage is::

   import asyncio
   from aiozmq import rpc

   class Handler(rpc.AttrHandler):

       @rpc.method
       def remote(self, arg1, arg2):
           return arg1 + arg2

   @asyncio.coroutine
   def go():
       server =  yield from rpc.serve_rpc(Handler(),
                                          bind='tcp://127.0.0.1:5555')

       client = yield from rpc.connect_rpc(connect='tcp://127.0.0.1:5555')

       ret = yield from client.call.remote(1, 2)
       assert ret == 3

   event_loop.run_until_complete(go())


.. function:: connect_rpc(*, connect=None, bind=None, loop=None, \
                          error_table=None, timeout=None, \
                          translation_table=None)

    A :ref:`coroutine<coroutine>` that creates and connects/binds
    *RPC* client.

    Usually for this function you need to use *connect* parameter, but
    :term:`ZeroMQ` does not forbid to use *bind*.

    :param aiozmq.ZmqEventLoop loop: an optional parameter to point
       :ref:`asyncio-event-loop`.  if *loop* is *None* then default
       event loop will be given by :func:`asyncio.get_event_loop` call.

    :param dict error_table: an optional table for custom exception translators.

       .. seealso:: :ref:`aiozmq-rpc-exception-translation`

    :param float timeout: an optional timeout for RPC calls. If
       *timeout* is not *None* and remote call takes longer than
       *timeout* seconds then :exc:`asyncio.TimeoutError` will be raised
       at client side. If the server will return an answer after timeout
       has been raised that answer **is ignored**.

       .. seealso:: :meth:`RPCClient.with_timeout` method.

    :param dict translation_table:
       an optional table for custom value translators.

       .. seealso:: :ref:`aiozmq-rpc-value-translators`

    :return: :class:`RPCClient` instance.

    .. seealso::

       Please take a look on
       :meth:`aiozmq.ZmqEventLoop.create_zmq_connection` for valid
       values to *connect* and *bind* parameters.


.. function:: serve_rpc(handler, *, connect=None, bind=None, loop=None, \
                        translation_table=None)

    A :ref:`coroutine<coroutine>` that creates and connects/binds *RPC*
    server instance.

    Usually for this function you need to use *bind* parameter, but
    :term:`ZeroMQ` does not forbid to use *connect*.

    :param aiozmq.rpc.AbstractHander handler:

       an object which processes incoming RPC calls.

      Usually you like to pass :class:`AttrHandler` instance.

    :param dict translation_table:
       an optional table for custom value translators.

       .. seealso:: :ref:`aiozmq-rpc-value-translators`

    :return: :class:`Service` instance.

    .. seealso::

       Please take a look on
       :meth:`aiozmq.ZmqEventLoop.create_zmq_connection` for valid
       values for *connect* and *bind* parameters.

.. _aiozmq-rpc-pushpull:

Push-Pull
---------

This is a **Notify** aka **Pipeline** pattern. Client calls a remote function
on the server and **doesn't** wait for the result. If a *remote function call*
raises an exception, this exception is only **logged** at the server side.  Client
**cannot** get any information about *processing the remote call on server*.

Thus this is **one-way** communication: **fire and forget**.

Let's assume that we have *N* clients bound to *M* servers.  Any client can
connect to several servers and any server can listen to multiple
*endpoints*.

When client sends a message, the message is delivered to any server
that is *ready* (doesn't processes another message).

That's all.

This pair uses *PUSH*/*PULL* :term:`ZeroMQ` sockets.


The basic usage is::

   import asyncio
   from aiozmq import rpc

   class Handler(rpc.AttrHandler):

       @rpc.method
       def remote(self):
           do_something(arg)

   @asyncio.coroutine
   def go():
       server =  yield from rpc.serve_pipeline(Handler(),
                                               bind='tcp://127.0.0.1:5555')

       client = yield from rpc.connect_pipeline(connect='tcp://127.0.0.1:5555')

       ret = yield from client.notify.remote(1)

   event_loop.run_until_complete(go())


.. function:: connect_pipeline(*, connect=None, bind=None, loop=None, \
                               error_table=None, translation_table=None)

    A :ref:`coroutine<coroutine>` that creates and connects/binds
    *pipeline* client.

    Usually for this function you need to use *connect* parameter, but
    :term:`ZeroMQ` does not forbid to use *bind*.

    :param aiozmq.ZmqEventLoop loop: an optional parameter to point
       :ref:`asyncio-event-loop`.  if *loop* is *None* then default
       event loop will be given by :func:`asyncio.get_event_loop` call.

    :param dict translation_table:
       an optional table for custom value translators.

       .. seealso:: :ref:`aiozmq-rpc-value-translators`

    :return: :class:`PipelineClient` instance.

    .. seealso::

       Please take a look on
       :meth:`aiozmq.ZmqEventLoop.create_zmq_connection` for valid
       values to *connect* and *bind* parameters.



.. function:: serve_pipeline(handler, *, connect=None, bind=None, loop=None, \
                        translation_table=None)

    A :ref:`coroutine<coroutine>` that creates and connects/binds *pipeline*
    server instance.

    Usually for this function you need to use *bind* parameter, but
    :term:`ZeroMQ` does not forbid to use *connect*.

    :param aiozmq.rpc.AbstractHander handler:

       an object which processes incoming *pipeline* calls.

      Usually you like to pass :class:`AttrHandler` instance.

    :param dict translation_table:
       an optional table for custom value translators.

       .. seealso:: :ref:`aiozmq-rpc-value-translators`

    :return: :class:`Service` instance.

    .. seealso::

       Please take a look on
       :meth:`aiozmq.ZmqEventLoop.create_zmq_connection` for valid
       values for *connect* and *bind* parameters.


.. _aiozmq-rpc-pubsub:

Publish-Subscribe
-----------------

This is **PubSub** pattern. It's very close to :ref:`aiozmq-rpc-pubsub`
but has some difference:

  * server *subscribes* to *topics* in order to receive messages only from that
    *topics*.
  * client sends a message to concrete *topic*.

Let's assume we have *N* clients bound to *M* servers.  Any client can
connect to several servers and any server can listen to multiple
*endpoints*.

When client sends a message to *topic*, the message will be delivered
to servers that only has been subscribed to this *topic*.

This pair uses *PUB*/*SUB* :term:`ZeroMQ` sockets.


The basic usage is::

   import asyncio
   from aiozmq import rpc

   class Handler(rpc.AttrHandler):

       @rpc.method
       def remote(self):
           do_something(arg)

   @asyncio.coroutine
   def go():
       server =  yield from rpc.serve_pubsub(Handler(),
                                             subscribe='topic',
                                             bind='tcp://127.0.0.1:5555')

       client = yield from rpc.connect_pubsub(connect='tcp://127.0.0.1:5555')

       ret = yield from client.publish('topic').remote(1)

   event_loop.run_until_complete(go())


.. function:: connect_pubsub(*, connect=None, bind=None, loop=None, \
                             error_table=None, translation_table=None)

    A :ref:`coroutine<coroutine>` that creates and connects/binds
    *pubsub* client.

    Usually for this function you need to use *connect* parameter, but
    :term:`ZeroMQ` does not forbid to use *bind*.

    :param aiozmq.ZmqEventLoop loop: an optional parameter to point
       :ref:`asyncio-event-loop`.  if *loop* is *None* then default
       event loop will be given by :func:`asyncio.get_event_loop` call.

    :param dict translation_table:
       an optional table for custom value translators.

       .. seealso:: :ref:`aiozmq-rpc-value-translators`

    :return: :class:`PubSubClient` instance.

    .. seealso:: Please take a look on
       :meth:`aiozmq.ZmqEventLoop.create_zmq_connection` for valid
       values to *connect* and *bind* parameters.


.. function:: serve_pubsub(handler, *, connect=None, bind=None, subscribe=None,\
              loop=None, translation_table=None)

    A :ref:`coroutine<coroutine>` that creates and connects/binds *pubsub*
    server instance.

    Usually for this function you need to use *bind* parameter, but
    :term:`ZeroMQ` does not forbid to use *connect*.

    :param aiozmq.rpc.AbstractHander handler:

       an object which processes incoming *pipeline* calls.

      Usually you like to pass :class:`AttrHandler` instance.

   :param subscribe: subscription specification.

      Subscribe server to *topics*.

      Allowed parameters are :class:`str`, :class:`bytes`, *iterable* of
      *str* or *bytes*.

   :param dict translation_table:
       an optional table for custom value translators.

       .. seealso:: :ref:`aiozmq-rpc-value-translators`

   :return: :class:`PubSubService` instance.
   :raises: :exc:`OSError` on system error.
   :raises: :exc:`TypeError` if arguments have inappropriate type

   .. seealso::

      Please take a look on
      :meth:`aiozmq.ZmqEventLoop.create_zmq_connection` for valid
      values for *connect* and *bind* parameters.


.. _aiozmq-rpc-exception-translation:

Exception translation at client side
----------------------------------------

If a remote server method raises an exception, that exception is passed
back to the client and raises on the client side, as follows::

    try:
        yield from client.call.func_raises_value_error()
    except ValueError as exc:
        log.exception(exc)

The rules for exception translation are:

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
   * all :ref:`builtin exceptions <bltin-exceptions>` are translated
     by default.
   * :exc:`NotFoundError` and :exc:`ParameterError` are translated by
     default also.
   * if there is no registered traslation then
     ``GenericError(excpetion_name, args)`` is raised.

For example if custom RPC server handler can raise ``mod1.Error1`` and
``pack.mod2.Error2`` then *error_table* should be::

    from mod1 import Error1
    from pack.mod2 import Error2

    error_table = {'mod1.Error1': Error1,
                   'pack.mod2.Error2': Error2}

    client = loop.run_until_complete(
        rpc.connect_rpc(connect='tcp://127.0.0.1:5555',
                        error_table=error_table))

You have to have the way to import exception classes from server-side.
Or you can build your own translators without server-side code, use
only string for *full exception class name* and tuple of *args* ---
that's up to you.

.. seealso:: *error_table* argument in :func:`connect_rpc` function.

.. _aiozmq-rpc-signature-validation:

Signature validation
------------------------

The library supports **optional** validation of the remote call signatures.

If validation fails then :exc:`ParameterError` raises on client side.

All validations are done on RPC server side, then errors are translated
back to client.

Let's take a look on example of user-defined RPC handler::

   class Handler(rpc.AttrHandler):

       @rpc.method
       def func(self, arg1: int, arg2) -> float:
           return arg1 + arg2

*Parameter* *arg1* and *return value* has :term:`annotaions <annotaion>`,
*int* and *float* correspondingly.

At the call time, if *parameter* has an :term:`annotaion`, then *actual
value* passed and RPC method is calculated as ``actual_value =
annotation(value)``. If there is no annotaion for parameter, the value
is passed as-is.

Annotaion should be any :term:`callable` that accepts a value as single argument
and returns *actual value*.

If annotation call raises exceptionб that exception is sent to the client
wrapped in :exc:`ParameterError`.

Value, returned by RPC call, can be checked by optional *return annotation*.

Thus :class:`int` can be a good annotation: it raises :exc:`TypeError`
if *arg1* cannot be converted to *int*.

Usually you need more complex check, say parameter can be *int* or
*None*.

You always can write a custom validator::

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

Value translators
---------------------

aiozmq.rpc uses :term:`msgpack` for transfering python objects from
client to server and back.

You can think about :term:`msgpack` as: this is a-like JSON but fast
and compact.

Every object that can be passed to :func:`json.dump`, can be passed to
:func:`msgpack.dump` also. The same for unpacking.

The only difference is: *aiozmq.rpc* converts all :class:`lists
<list>` to :class:`tuples <tuple>`.  The reasons is are:

  * you never need to modify given list as it is your *incoming*
    value.  If you still want to use :class:`list` data type you can
    do it easy by ``list(val)`` call.
  * tuples are a bit faster for unpacking.
  * tuple can be a *key* in :class:`dict`, so you can pack something
    like ``{(1,2): 'a'}`` and unpack it on other side without any
    error. Lists cannot be *keys* in dicts, they are unhashable.

    This point is the main reason for choosing tuples. Unfortunatelly
    msgpack gives no way to mix tuples and lists in the same pack.

But sometimes you want to call remote side with *non-plain-json*
arguments.  :class:`datetime.datetime` is a good example.
:mod:`aiozmq.rpc` supports all family of dates, times and timezones
from :mod:`datetime` *from-the-box*
(:ref:`predefined translators <aiozmq-rpc-predifined-translators>`).

If you need to transfer a custom object via RPC you should register
**translator** at both server and client side.  Say, you need to pass the 
instances of your custom class ``Point`` via RPC. There is an
example::

    import asyncio
    import aiozmq, aiozmq.rpc
    import msgpack

    class Point:
        def __init__(self, x, y):
            self.x = x
            self.y = y

        def __eq__(self, other):
            if isinstance(other, Point):
                return (self.x, self.y) == (other.x, other.y)
            return NotImplemented

    translation_table = {
        0: (Point,
            lambda value: msgpack.packb((value.x, value.y)),
            lambda binary: Point(*msgpack.unpackb(binary))),
    }

    class ServerHandler(aiozmq.rpc.AttrHandler):
        @aiozmq.rpc.method
        def remote(self, val):
            return val

    @asyncio.coroutine
    def go():
        server = yield from aiozmq.rpc.serve_rpc(
            ServerHandler(), bind='tcp://127.0.0.1:5555',
            translation_table=translation_table)
        client = yield from aiozmq.rpc.connect_rpc(
            connect='tcp://127.0.0.1:5555',
            translation_table=translation_table)

        ret = yield from client.call.remote(Point(1, 2))
        assert ret == Point(1, 2)

You should create a *translation table* and pass it to both
:func:`connect_rpc` and :func:`serve_rpc`. That's all, server and
client now have all information about passing your ``Point`` via the
wire.

* Translation table is the dict.

* Keys should be an integers in range [0, 127]. We recommend to use
  keys starting from 0 for custom translators, high numbers are
  reserved for library itself (it uses the same schema for passing
  *datetime* objects etc).

* Values are tuples of ``(translated_class, packer, unpacker)``.

  * *translated_class* is a class which you want to pass to peer.
  * *packer* is a :term:`callable` which receives your class instance
    and returns :class:`bytes` of *instance data*.
  * *unpacker* is a :term:`callable` which receives :class:`bytes` of
    *instance data* and returns your *class instance*.

* When the library tries to pack your class instance it searches the
  *translation table* in ascending order.

* If your object is an :func:`instance <isinstance>` of
  *translated_class* then *packer* is called and resulting
  :class:`bytes` will be sent to peer.

* On unpacking *unpacker* is called with the :class:`bytes` received by peer.
  The result should to be your class instance.

.. warning::

   Please be careful with *translation table* order. Say, if you have
   :class:`object` at position 0 then every lookup will stop at
   this. Even *datetime* objects will be redirected to *packer* and
   *unpacker* for registered *object* type.

.. warning::

   While the easiest way to write *packer* and *unpacker* is to use
   :mod:`pickle` we **don't encourage that**. The reason is simple:
   *pickle* packs an object itself and all instances which are
   referenced by that object. So you can easy pass via network a half
   of your program without any warning.

.. _aiozmq-rpc-predifined-translators:

Table of predefined translators:

+---------+-------------------------------+
| Ordinal | Class                         |
+=========+===============================+
+ 123     | :class:`datetime.tzinfo`      |
+---------+-------------------------------+
+ 124     | :class:`datetime.timedelta`   |
+---------+-------------------------------+
+ 125     | :class:`datetime.time`        |
+---------+-------------------------------+
+ 126     | :class:`datetime.date`        |
+---------+-------------------------------+
| 127     | :class:`datetime.datetime`    |
+---------+-------------------------------+

.. note::

   `pytz <http://pythonhosted.org/pytz/>`_ timezones processed by
   predefined traslator for *tzinfo* (ordinal number 123) because they
   are inherited from :class:`datetime.tzinfo`. So you don't need to
   register a custom translator for ``pytz.datetime`` .

   That's happens because :mod:`aiozmq.rpc` uses :mod:`pickle` for
   translation :mod:`datetime` classes.

   Pickling in this particular case is **safe** because all datetime
   classes are terminals and doesn't have a links to foreign class
   instances.


Exceptions
--------------

.. exception:: Error

   Base class for :mod:`aiozmq.rpc` exceptions. Derived from :exc:`Exception`.

.. exception:: GenericError

   Subclass of :exc:`Error`, raised when a remote call produces
   exception that cannot be translated.

   .. attribute:: exc_type

      A string contains *full name* of unknown
      exception(``"package.module.MyError"``).

   .. attribute:: arguments

      A tuple of arguments passed to *unknown exception* constructor

      .. seealso:: :attr:`BaseException.args` - parameters for
                   exception constructor.

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

      :attr:`Service.transport` property.


Clases
----------

.. decorator:: method

   Marks a decorated function as RPC endpoint handler.

   The func object may provide arguments and/or return annotations.
   If so annotations should be callable objects and
   they will be used to validate received arguments and/or return value.

   Example::

       @aiozmq.rpc.method
       def remote(a: int, b: int) -> int:
           return a + b

   Methods are objects that returned by
   :meth:`AbstractHander.__getitem__` lookup at RPC method search
   stage.


.. class:: AbstractHander

   The base class for all RPC handlers.

   Every handler should be *AbstractHandler* by direct inheritance
   or indirect subclassing (method *__getitem__* should be defined).

   Therefore :class:`AttrHandler` and :class:`dict` are both good
   citizens.

   Returned value eighter should implement :class:`AbstractHandler`
   interface itself for looking up forward or must be callable
   decorated by :func:`method`.

    .. method:: __getitem__(self, key)

        Returns subhandler or terminal function decorated by
        :func:`method`.

        :raise KeyError: if key is not found.

    .. seealso:: :func:`start_server` coroutine.

.. class:: AttrHandler

   Subclass of :class:`AbstractHandler`. Does lookup for *subhandlers*
   and *rpc methods* by :func:`getattr`.

   There is an example of trivial *handler*::

       class ServerHandler(aiozmq.rpc.AttrHandler):
           @aiozmq.rpc.method
           def remote_func(self, a:int, b:int) -> int:
               return a + b




.. class:: Service

   RPC service base class.

   Instances of *Service* (or descendants) are returned by
   coroutines that creates clients or servers (:func:`connect_rpc`,
   :func:`serve_rpc` and others).

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

      .. seealso::
         :ref:`aiozmq-rpc-signature-validation`


.. class:: RPCClient

   Class that returned by :func:`connect_rpc` call. Inherited from
   :class:`Service`.

   For RPC calls use :attr:`~RPCClient.rpc` property.

   .. attribute:: call

      The readonly property that returns ephemeral object used to making
      RPC call.

      Construction like::

          ret = yield from client.call.ns.method(1, 2, 3)

      makes a remote call with arguments(1, 2, 3) and returns answer
      from this call.

      You can also pass *named parameters*::

          ret = yield from client.call.ns.method(1, b=2, c=3)

      If the call raises exception that exception propagates to client side.

      Say, if remote raises :class:`ValueError` client catches
      ``ValueError`` instance with *args* sent by remote::

          try:
              yield from client.call.raise_value_error()
          except ValueError as exc:
              process_error(exc)

   .. method:: with_timeout(timeout)

      Override default timeout for client. Can be used in two forms::

          yield from client.with_timeout(1.5).call.func()

      and::

          with client.with_timeout(1.5) as new_client:
              yield from new_client.call.func1()
              yield from new_client.call.func2()

      :param float timeout: a timeout for RPC calls. If
         *timeout* is not *None* and remote call takes longer than
         *timeout* seconds then :exc:`asyncio.TimeoutError` will be raised
         at client side. If the server will return an answer after timeout
         has been raised that answer **is ignored**.

         .. seealso:: :func:`connect_rpc` coroutine.


   .. seealso::
      :ref:`aiozmq-rpc-exception-translation` and
      :ref:`aiozmq-rpc-signature-validation`

.. class:: PipelineClient

   Class that returned by :func:`connect_pipeline` call. Inherited from
   :class:`Service`.

   .. attribute:: notify

      The readonly property that returns ephemeral object used to making
      notification call.

      Construction like::

          ret = yield from client.notify.ns.method(1, 2, 3)

      makes a remote call with arguments(1, 2, 3) and returns *None*.

      You cannot get any answer from the server.


.. class:: PubSubClient

   Class that returned by :func:`connect_pubsub` call. Inherited from
   :class:`Service`.

   For *pubsub* calls use :attr:`~RPCClient.publish` method.

   .. method:: publish(topic)

      The call that returns ephemeral object used to making
      *publisher call*.

      Construction like::

          ret = yield from client.publish('topic').ns.method(1, b=2)

      makes a remote call with arguments ``(1, b=2)`` and topic name
      ``b'topic'`` and returns *None*.

      You cannot get any answer from the server.

   .. seealso::
      :ref:`aiozmq-rpc-signature-validation`

.. class:: PubSubClient

   Class that returned by :func:`connect_pubsub` call. Inherited from
   :class:`Service`.

   For *pubsub* calls use :attr:`~RPCClient.publish` method.

   .. method:: publish(topic)

      The call that returns ephemeral object used to making
      *publisher call*.

      Construction like::

          ret = yield from client.publish('topic').ns.method(1, b=2)

      makes a remote call with arguments ``(1, b=2)`` and topic name
      ``b'topic'``

   .. seealso::
      :ref:`aiozmq-rpc-signature-validation`
