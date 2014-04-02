.. _aiozmq-core:

:mod:`aiozmq` --- Core API
==========================


.. module:: aiozmq
   :synopsis: Low level API for ZeroMQ support
.. currentmodule:: aiozmq


.. _install-aiozmq-policy:

Installing ZeroMQ event loop
----------------------------

To use :term:`ZeroMQ` layer you **should** install proper event loop
first.

The recommended way is to setup *global event loop policy*::

    import asyncio
    import aiozmq

    asyncio.set_event_loop_policy(aiozmq.ZmqEventLoopPolicy())

That installs :class:`ZmqEventLoopPolicy` globally. After installing
you can get event loop instance from main thread by
:func:`asyncio.get_event_loop` call::

    loop = asyncio.get_event_loop()

If you need to execute event loop in your own (not main) thread you have to
set it up first::

     import threading

     def thread_func():
         loop = asyncio.new_event_loop()
         asyncio.set_event_loop()

         loop.run_forever()

     thread = threading.Thread(target=thread_func)
     thread.start()


ZmqEventLoop
---------------------


Event loop with :term:`ZeroMQ` support.

Follows :class:`asyncio.AbstractEventLoop` specification and has
:meth:`~ZmqEventLoop.create_zmq_connection` method for :term:`ZeroMQ`
sockets layer.

Internally the loop contains a :class:`zmq.Context` instance, so all
transports created by event loop shares the same context.


.. class:: ZmqEventLoop(*, io_threads=1)

   :param int io_threads: number of I/O threads.
     See http://api.zeromq.org/3-3:zmq-ctx-set **ZMQ_IO_THREADS** for details.

   .. method:: create_zmq_connection(protocol_factory, zmq_type, *, \
                               bind=None, connect=None, zmq_sock=None)

        Create a ZeroMQ connection.

        If you don't use *bind* or *connect* params you can do it
        later by :meth:`ZmqTransport.bind` and :meth:`ZmqTransport.connect`
        calls.

        :param callable protocol_factory: a factory that instantiates
          :class:`~ZmqProtocol` object.

        :param int zmq_type: a type of :term:`ZeroMQ` socket
          (*zmq.REQ*, *zmq.REP*, *zmq.PUB*, *zmq.SUB*, zmq.PAIR*,
          *zmq.DEALER*, *zmq.ROUTER*, *zmq.PULL*, *zmq.PUSH*, etc.)

        :param bind: endpoints specification.

          Every :term:`endpoint` generates call to
          :meth:`ZmqTransport.bind` for accepting connections from
          specified endpoint.

          Other side should use *connect* parameter to connect to this
          transport.
        :type bind: str or iterable of strings

        :param connect: endpoints specification.

          Every :term:`endpoint` generates call to
          :meth:`ZmqTransport.connect` for connecting transport to
          specified endpoint.

          Other side should use bind parameter to wait for incoming
          connections.
        :type connect: str or iterable of strings

        :param zmq.Socket zmq_sock: a preexisting zmq socket that
                                    will be passed to returned
                                    transport.

        :return: a pair of ``(transport, protocol)``
          where transport supports :class:`~ZmqTransport` interface.
        :rtype: :class:`tuple`


ZmqTransport
---------------------

.. class:: ZmqTransport

   Transport for :term:`ZeroMQ` connections. Implements
   :class:`asyncio.BaseTransport` interface.

   End user should never create :class:`~ZmqTransport` objects directly,
   he gets it by ``yield from loop.create_zmq_connection()`` call.

   .. method:: get_extra_info(key, default=None)

      Return optional transport information if name is present
      otherwise return *default*.

      :class:`ZmqTransport` supports the only valid *key*:
      ``"zmq_socket"``.  The value is :class:`zmq.Socket` instance.

      :param str name: name of info record.
      :param default: default value

   .. method:: close()

      Close the transport.

      Buffered data will be flushed asynchronously.  No more data will
      be received.  After all buffered data is flushed, the protocol's
      :meth:`~ZmqProtocol.connection_lost` method will (eventually)
      called with *None* as its argument.

   .. method:: write(data)

      Write message to the transport.

      :param data: iterable to send as multipart message.

      This does not block; it buffers the data and arranges for it
      to be sent out asynchronously.

   .. method:: abort()

      Close the transport immediately.

      Buffered data will be lost.  No more data will be received.  The
      protocol's :meth:`~ZmqProtocol.connection_lost` method will
      (eventually) be called with *None* as it's argument.

   .. method:: getsockopt(option)

      Get :term:`ZeroMQ` socket option.

      :param int option: a constant like *zmq.SUBSCRIBE*,
        *zmq.UNSUBSCRIBE*, *zmq.TYPE* etc.

        For list of available options please see:
        http://api.zeromq.org/master:zmq-getsockopt

      :return: option value

      :raise OSError:
         if call to ZeroMQ was unsuccessful.

   .. method:: setsockopt(option, value)

      Set :term:`ZeroMQ` socket option.

      :param int option: a constant like *zmq.SUBSCRIBE*,
        *zmq.UNSUBSCRIBE*, *zmq.TYPE* etc.

      :param value: a new option value, it's type depend of option name.

        For list of available options please see:
        http://api.zeromq.org/master:zmq-setsockopt

   .. method:: set_write_buffer_limits(high=None, low=None)

      Set the high- and low-water limits for write flow control.

      :param high: high-water limit
      :type high: int or None

      :param low: low-water limit
      :type low: int or None

      These two values control when to call the protocol's
      :meth:`~ZmqProtocol.pause_writing` and
      :meth:`~ZmqProtocol.resume_writing()` methods.  If specified, the
      low-water limit must be less than or equal to the high-water
      limit.  Neither value can be negative.

      The defaults are implementation-specific.  If only the
      high-water limit is given, the low-water limit defaults to a
      implementation-specific value less than or equal to the
      high-water limit.  Setting high to zero forces low to zero as
      well, and causes :meth:`~ZmqProtocol.pause_writing` to be called
      whenever the buffer becomes non-empty.  Setting low to zero
      causes :meth:`~ZmqProtocol.resume_writing` to be called only once
      the buffer is empty.  Use of zero for either limit is generally
      sub-optimal as it reduces opportunities for doing I/O and
      computation concurrently.


   .. method:: get_write_buffer_size()

      Return the current size of the write buffer.

   .. method:: bind(endpoint)

      Bind transpot to :term:`endpoint`.
      See http://api.zeromq.org/master:zmq-bind for details.

      This method is a :ref:`coroutine <coroutine>`.

      :param endpoint: a string in format ``transport://address`` as
         :term:`ZeroMQ` requires.

      :return: bound endpoint, unwinding wildcards if needed.
      :rtype: :class:`str`
      :raise OSError: on error from ZeroMQ layer
      :raise TypeError: if *endpoint* is not a :class:`str`

   .. method:: unbind(endpoint)

      Unbind transpot from :term:`endpoint`.

      This method is a :ref:`coroutine <coroutine>`.

      :param endpoint: a string in format ``transport://address`` as
         :term:`ZeroMQ` requires.

      :return: *None*
      :raise OSError: on error from ZeroMQ layer
      :raise TypeError: if *endpoint* is not a :class:`str`

   .. method:: bindings()

      Return immutable set of :term:`endpoints <endpoint>` bound to transport.

      .. note::

         Returned endpoints include only ones that has been bound via
         :meth:`ZmqTransport.bind` or
         :meth:`ZmqEventLoop.create_zmq_connection` calls and do not
         include bindings that have been done on *zmq_sock* before
         :meth:`ZmqEventLoop.create_zmq_connection` call.

   .. method:: connect(endpoint)

      Connect transpot to :term:`endpoint`.
      See http://api.zeromq.org/master:zmq-connect for details.

      This method is a :ref:`coroutine <coroutine>`.

      :param str endpoint: a string in format ``transport://address`` as
        :term:`ZeroMQ` requires.

        For tcp connections the *endpoint* should specify *IPv4* or
        *IPv6* address, not *DNS* name.  Use ``yield from
        get_event_loop().getaddrinfo(host, port)`` for translating
        *DNS* into *IP address*.

      :return: endpoint
      :rtype: :class:`str`

      :raise ValueError: if the endpoint is a tcp DNS address.
      :raise OSError: on error from ZeroMQ layer
      :raise TypeError: if *endpoint* is not a :class:`str`


   .. method:: disconnect(endpoint)

      Disconnect transpot from :term:`endpoint`.

      This method is a :ref:`coroutine <coroutine>`.

      :param endpoint: a string in format ``transport://address`` as
         :term:`ZeroMQ` requires.

      :return: *None*
      :raise OSError: on error from ZeroMQ layer
      :raise TypeError: if *endpoint* is not a :class:`str`

   .. method:: connections()

      Return immutable set of :term:`endpoints <endpoint>` connected
      to transport.

      .. note::

         Returned endpoints include only ones that has been connected
         via :meth:`ZmqTransport.connect` or
         :meth:`ZmqEventLoop.create_zmq_connection` calls and do not
         include connections that have been done to *zmq_sock* before
         :meth:`ZmqEventLoop.create_zmq_connection` call.

   .. method:: subscribe(value)

      Establish a new message filter on *SUB* transport.

      Newly created *SUB* transports filters out all incoming
      messages, therefore you should call this method to
      establish an initial message filter.

      An empty (``b''``) *value* subscribes to all incoming messages. A
      non-empty value subscribes to all messages beginning with the
      specified prefix. Multiple filters may be attached to a single
      *SUB* transport, in which case a message shall be accepted if it
      matches at least one filter.

      :param bytes value: a filter value to add to *SUB* filters.
      :raise NotImplementedError: the transport is not *SUB*.
      :raise TypeError: when *value* is not bytes.


      .. _aiozmq-transport-subscribe-warning:

      .. warning::

         Unlike to :term:`ZeroMQ` socket level the call first check
         for *value* in :meth:`ZmqTransport.subscriptions` and does
         nothing if the transport already has been subscribed to the
         *value*.

   .. method:: unsubscribe(value)

      Remove an existing message filter on a *SUB* transport.

      The filter specified must match an existing filter previously
      established with the :meth:`ZmqTransport.subscribe`.

      If the transport has several instances of the same filter
      attached the ``.unsubscribe()`` removes only one instance,
      leaving the rest in place and functional (if you use
      :meth:`ZmqTransport.subscribe` to adding new filters that never
      happens, see :ref:`difference between aiozmq and ZeroMQ raw
      sockets <aiozmq-transport-subscribe-warning>` for details).

      :param bytes value: a filter value to add to *SUB* filters.

      :raise NotImplementedError: the transport is not *SUB*.
      :raise TypeError: when *value* is not bytes.

   .. method:: subscriptions()

      Return immutable set of subscriptions (set of bytes) subscribed
      on transport.

      .. note::

         Returned subscriptions include only ones that has
         been subscribed via :meth:`ZmqTransport.subscribe` call and do not
         include subscribtions that have been done to zmq_sock before
         :meth:`ZmqEventLoop.create_zmq_connection` call.

      :raise NotImplementedError: the transport is not *SUB*.



ZmqProtocol
--------------------

.. class:: ZmqProtocol

   Protocol for :term:`ZeroMQ` connections. Derives from
   :class:`asyncio.BaseProtocol`.

   .. method:: connection_made(transport)

      Called when a connection is made.

      :param ZmqTransport transport: representing the pipe
        connection.  To receive data, wait for
        :meth:`~ZmqProtocol.msg_received` calls.  When the
        connection is closed,
        :meth:`~ZmqProtocol.connection_lost` is called.

   .. method:: connection_lost(exc)

      Called when the connection is lost or closed.

      :param exc: an exception object or *None* (the latter
         meaning the connection was aborted or closed).
      :type exc: instance of :class:`Exception` or derived class

   .. method:: pause_writing()

      Called when the transport's buffer goes over the high-water mark.

      Pause and resume calls are paired --
      :meth:`~ZmqProtocol.pause_writing` is called once when
      the buffer goes strictly over the high-water mark (even if
      subsequent writes increases the buffer size even more), and
      eventually :meth:`~ZmqProtocol.resume_writing` is called
      once when the buffer size reaches the low-water mark.

      Note that if the buffer size equals the high-water mark,
      :meth:`~ZmqProtocol.pause_writing` is not called -- it
      must go strictly over.  Conversely,
      :meth:`~ZmqProtocol.resume_writing` is called when the
      buffer size is equal or lower than the low-water mark.  These
      end conditions are important to ensure that things go as
      expected when either mark is zero.

      .. note::

         This is the only Protocol callback that is not called through
         :meth:`asyncio.AbstractEventLoop.call_soon` -- if it were, it
         would have no effect when it's most needed (when the app
         keeps writing without yielding until
         :meth:`~ZmqProtocol.pause_writing` is called).

   .. method:: resume_writing()

      Called when the transport's buffer drains below the low-water mark.

      See :meth:`~ZmqProtocol.pause_writing` for details.

   .. method:: msg_received(data)

      Called when some ZeroMQ message is received.

      :param tuple data: the multipart tuple of bytes with at least one item.


ZmqEventLoopPolicy
---------------------------

ZeroMQ policy implementation for accessing the event loop.

In this policy, each thread has its own event loop.  However, we only
automatically create an event loop by default for the main thread;
other threads by default have no event loop.

:class:`ZmqEventLoopPolicy` implements an :class:`asyncio.AbstractEventLoopPolicy` interface.

.. class:: ZmqEventLoopPolicy(*, io_threads=1)

   Create policy for ZeroMQ event loops.

   :param int io_threads: number of I/O threads for event loops
                          created by this policy.

      .. seealso:: :class:`ZmqEventLoop` constructor.

   .. note::

      policy should be **installed**, see :ref:`install-aiozmq-policy`.

   .. method:: get_event_loop()

      Get the event loop.

      If current thread is the main thread and there are no
      registered event loop for current thread then the call creates
      new event loop and registers it.

      :return: Return an instance of :class:`ZmqEventLoop`.
      :raise RuntimeError: if there is no registered event loop
         for current thread.

   .. method:: new_event_loop()

      Create a new event loop.

      You must call :meth:`ZmqEventLoopPolicy.set_event_loop` to
      make this the current event loop.

   .. method:: set_event_loop(loop)

      Set the event loop.

      As a side effect, if a child watcher was set before, then
      calling ``.set_event_loop()`` from the main thread will call
      :meth:`asyncio.AbstractChildWatcher.attach_loop` on the child watcher.

      :param loop: an :class:`asyncio.AbstractEventLoop` instance or *None*
      :raise TypeError: if loop is not instance of
         :class:`asyncio.AbstractEventLoop`

   .. method:: get_child_watcher()

      Get the child watcher

      If not yet set, a :class:`asyncio.SafeChildWatcher` object is
      automatically created.

      :return: Return an instance of :class:`asyncio.AbstractChildWatcher`.

   .. method:: set_child_watcher(watcher)

      Set the child watcher.

      :param watcher: an :class:`asyncio.AbstractChildWatcher`
         instance or *None*
      :raise TypeError: if watcher is not instance of
         :class:`asyncio.AbstractChildWatcher`

Exception policy
----------------

Every call to :class:`zmq.Socket` method can raise
:class:`zmq.ZMQError` exception. But all methods of
:class:`ZmqEventLoop` and :class:`ZmqTransport` translate ZMQError
into :class:`OSError` (or descendat) with errno and strerror borrowed
from underlying ZMQError values.

The reason for translation is that Python 3.3 implements :pep:`3151`
**--- Reworking the OS and IO Exception Hierarchy** which gets rid of
exceptions zoo and uses :class:`OSError` and descendants for all
exceptions generated by system function calls.

:mod:`aiozmq` implements the same pattern. Internally it looks like::

       try:
           return self._zmq_sock.getsockopt(option)
       except zmq.ZMQError as exc:
           raise OSError(exc.errno, exc.strerror)

Also public methods of :mod:`aiozmq` will never raise
:exc:`InterruptedError` (aka *EINTR*), they process interruption
internally.

Getting aiozmq version
----------------------

.. data:: version

   a text version of the library::

       '0.1.0 , Python 3.3.2+ (default, Feb 28 2014, 00:52:16) \n[GCC 4.8.1]'

.. data:: version_info

   a named tuple with version information, useful for comparison::

       VersionInfo(major=0, minor=1, micro=0, releaselevel='alpha', serial=0)

   The Python itself uses the same schema (:const:`sys.version_info`).
