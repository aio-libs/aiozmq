asyncio integration with ZeroMQ
===============================

asyncio (PEP 3156) support for ZeroMQ.

.. image:: https://travis-ci.com/aio-libs/aiozmq.svg?branch=master
   :target: https://travis-ci.com/aio-libs/aiozmq

The difference between ``aiozmq`` and vanilla ``pyzmq`` (``zmq.asyncio``) is:

``zmq.asyncio`` works only by replacing the *base event loop* with a custom one.
This approach works but has two disadvantages:

1. ``zmq.asyncio.ZMQEventLoop`` cannot be combined with
   other loop implementations (most notable is the ultra fast ``uvloop``).

2. It uses the internal ZMQ Poller which has fast ZMQ Sockets support
   but isn't intended to work fast with many (thousands) regular TCP sockets.

   In practice it means that ``zmq.asyncio`` is not recommended to be used with
   web servers like ``aiohttp``.

   See also https://github.com/zeromq/pyzmq/issues/894

Documentation
-------------

See http://aiozmq.readthedocs.org

Simple high-level client-server RPC example:

.. code-block:: python

    import asyncio
    import aiozmq.rpc


    class ServerHandler(aiozmq.rpc.AttrHandler):

        @aiozmq.rpc.method
        def remote_func(self, a:int, b:int) -> int:
            return a + b


    async def go():
        server = await aiozmq.rpc.serve_rpc(
            ServerHandler(), bind='tcp://127.0.0.1:5555')
        client = await aiozmq.rpc.connect_rpc(
            connect='tcp://127.0.0.1:5555')

        ret = await client.call.remote_func(1, 2)
        assert 3 == ret

        server.close()
        client.close()

    asyncio.run(go())

Low-level request-reply example:

.. code-block:: python

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


Comparison to pyzmq
-------------------

``zmq.asyncio`` provides an *asyncio compatible loop* implementation.

But it's based on ``zmq.Poller`` which doesn't work well with massive
non-zmq socket usage.

E.g. if you build a web server for handling at least thousands of
parallel web requests (1000-5000) ``pyzmq``'s internal poller will be slow.

``aiozmq`` works with epoll natively, it doesn't need a custom loop
implementation and cooperates pretty well with `uvloop` for example.

For details see https://github.com/zeromq/pyzmq/issues/894


Requirements
------------

* Python_ 3.6+
* pyzmq_ 13.1+
* optional submodule ``aiozmq.rpc`` requires msgpack_ 0.5+



License
-------

aiozmq is offered under the BSD license.

.. _python: https://www.python.org/
.. _pyzmq: https://pypi.python.org/pypi/pyzmq
.. _asyncio: https://pypi.python.org/pypi/asyncio
.. _msgpack: https://pypi.python.org/pypi/msgpack
