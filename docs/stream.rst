.. _aiozmq-stream:

Streams API
===========================

.. currentmodule:: aiozmq

.. versionadded:: 0.6

While *aiozmq* library is built on top of low-level
:class:`ZmqTransport` and :class:`ZmqProtocol` API it provides a more
convinient way also.

Please take a look on example::

    import asyncio
    import aiozmq
    import zmq

    @asyncio.coroutine
    def go():
        router = yield from aiozmq.create_zmq_stream(
            zmq.ROUTER,
            bind='tcp://127.0.0.1:*')

        addr = list(router.transport.bindings())[0]
        dealer = yield from aiozmq.create_zmq_stream(
            zmq.DEALER,
            connect=addr)

        for i in range(10):
            msg = (b'data', b'ask', str(i).encode('utf-8'))
            dealer.write(msg)
            data = yield from router.read()
            router.write(data)
            answer = yield from dealer.read()
            print(answer)
        dealer.close()
        router.close()

    asyncio.get_event_loop().run_until_complete(go())

The code creates two streams for request and response part of
:term:`ZeroMQ` connection and sends message through the wire with
waiting for response.

create_zmq_stream
-----------------

.. function:: create_zmq_stream(zmq_type, *, bind=None, connect=None, \
                                loop=None, zmq_sock=None, \
                                high_read=None, low_read=None, \
                                high_write=None, low_write=None)

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

   :return: ZeroMQ stream object, :class:`ZmqStream` instance.


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
          yield from w.drain()

      When the transport buffer is full (the protocol is paused), block until
      the buffer is (partially) drained and the protocol is resumed. When there
      is nothing to wait for, the yield-from continues immediately.

      This method is a :ref:`coroutine <coroutine>`.

   .. method:: exception()

      Get the stream exception.

   .. method:: get_extra_info(name, default=None)

      Return optional transport information: see
      :meth:`asyncio.BaseTransport.get_extra_info`.

   .. method:: read()

      Read one :term:`ZeroMQ` message from the wire and return it.

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
