.. _aiozmq-stream:

Streams API
===========================

.. currentmodule:: aiozmq

.. versionadded:: 0.6

*aiozmq* provides a high level stream oriented API on top of the low-level
API (:class:`ZmqTransport` and :class:`ZmqProtocol`) which can provide a
more convinient API.

Here's an example::

    import asyncio
    import aiozmq
    import zmq

    async def go():
        router = await aiozmq.create_zmq_stream(
            zmq.ROUTER,
            bind='tcp://127.0.0.1:*')

        addr = list(router.transport.bindings())[0]
        dealer = await aiozmq.create_zmq_stream(
            zmq.DEALER,
            connect=addr)

        for i in range(10):
            msg = (b'data', b'ask', str(i).encode('utf-8'))
            dealer.write(msg)
            data = await router.read()
            router.write(data)
            answer = await dealer.read()
            print(answer)
        dealer.close()
        router.close()

    asyncio.run(go())

The code creates two streams for request and response part of
:term:`ZeroMQ` connection and sends message through the wire with
waiting for response.

Socket events can also be monitored when using streams.

.. literalinclude:: ../examples/stream_monitor.py


create_zmq_stream
-----------------

.. function:: create_zmq_stream(zmq_type, *, bind=None, connect=None, \
                                loop=None, zmq_sock=None, \
                                high_read=None, low_read=None, \
                                high_write=None, low_write=None, \
                                events_backlog=100)

   A wrapper for :func:`create_zmq_connection` returning a ZeroMQ
   stream (:class:`ZmqStream` instance).

   The arguments are all the usual arguments to
   :func:`create_zmq_connection` plus high and low watermarks for
   reading and writing messages.

   This function is a :ref:`coroutine <coroutine>`.

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

   :param asyncio.AbstractEventLoop loop: optional event loop
                                          instance, ``None`` for
                                          default event loop.

   :param int high_read: high-watermark for reading from
                         :term:`ZeroMQ` socket. ``None`` by default
                         (no limits).

   :param int low_read: low-watermark for reading from
                        :term:`ZeroMQ` socket. ``None`` by default
                        (no limits).

   :param int high_write: high-watermark for writing into
                          :term:`ZeroMQ` socket. ``None`` by default
                          (no limits).

   :param int low_write: low-watermark for writing into
                         :term:`ZeroMQ` socket. ``None`` by default
                         (no limits).

   :param int events_backlog: backlog size for monitoring events,
      ``100`` by default.  It specifies size of event queue. If count
      of unread events exceeds *events_backlog* the oldest events are
      discarded.

      Use ``None`` for unlimited backlog size.

   :return: ZeroMQ stream object, :class:`ZmqStream` instance.


   .. versionadded:: 0.7

      events_backlog parameter


ZmqStream
---------

.. class:: ZmqStream

   A class for sending and receiving :term:`ZeroMQ` messages.

   .. attribute:: transport

      :class:`ZmqTransport` instance, used for the stream.

   .. method:: at_closing()

      Return ``True`` if the buffer is empty and :meth:`feed_closing`
      was called.

   .. method:: close()

      Close the stream and underlying :term:`ZeroMQ` socket.

   .. method:: drain()

      Wait until the write buffer of the underlying transport is flushed.

      The intended use is to write::

          w.write(data)
          await w.drain()

      When the transport buffer is full (the protocol is paused), block until
      the buffer is (partially) drained and the protocol is resumed. When there
      is nothing to wait for, the await continues immediately.

      This method is a :ref:`coroutine <coroutine>`.

   .. method:: exception()

      Get the stream exception.

   .. method:: get_extra_info(name, default=None)

      Return optional transport information: see
      :meth:`asyncio.BaseTransport.get_extra_info`.

   .. method:: read()

      Read one :term:`ZeroMQ` message from the wire and return it.

      Raise :exc:`ZmqStreamClosed` if the stream was closed.

   .. method:: read_event()

      Read one :term:`ZeroMQ` monitoring event and return it.

      Raise :exc:`ZmqStreamClosed` if the stream was closed.

      Monitoring mode should be enabled by
      :meth:`ZmqTransport.enable_monitor` call first::

          await stream.transport.enable_monitor()

      .. versionadded:: 0.7

   .. method:: write(msg)

      Writes message *msg* into :term:`ZeroMQ` socket.

      :param msg: a sequence (:class:`tuple` or :class:`list`),
                  containing multipart message daata.

   *Internal API*

   .. method:: set_exception(exc)

      Set the exception to *exc*. The exception may be retrieved by
      :meth:`exception` call or raised by next :meth:`read`, *the
      private method*.

   .. method:: set_transport(transport)

      Set the transport to *transport*, *the private method*.

   .. method:: set_read_buffer_limits(high=None, low=None)

      Set read buffer limits, *the private method*.

   .. method:: feed_closing()

      Feed the socket closing signal, *the private method*.

   .. method:: feed_msg(msg)

      Feed *msg* message to the stream's internal buffer. Any
      operations waiting for the data will be resumed.

      *The private method*.

   .. method:: feed_event(event)

      Feed a socket *event* message to the stream's internal buffer.

      *The private method*.

Exceptions
----------

.. exception:: ZmqStreamClosed

   Raised by read operations on closed stream.
