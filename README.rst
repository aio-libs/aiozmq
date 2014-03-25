asyncio integration with ZeroMQ
=============================

Experimental asyncio (PEP 3156) compatibility with ZeroMQ.

.. image:: https://travis-ci.org/aio-libs/aiozmq.svg?branch=master
   :target: https://travis-ci.org/aio-libs/aiozmq

Documentation
-------------

See http://aiozmq.readthedocs.org

RPC Example
-----------

Simple client-server RPC example::

    import aiozmq, aiozmq.rpc
    import asyncio

    class ServerHandler(aiozmq.AttrHandler):
        @aiozmq.method
        def remote_func(self, a:int, b:int) -> int:
            retuirn a + b

    @asyncio.coroutine
    def go(client):
        server = yield from aiozmq.rpc.start_server(
            ServerHandler(), bind='tpc://127.0.0.1:5555'))
        client = yield from aiozmq.rpc.open_client(
            connect='tpc://127.0.0.1:5555'))

        ret = yield from client.rpc.remote_func(1, 3)
        assert 3 == ret

        server.close()
        client.close()

    asyncio.set_event_loop_policy(aiozmq.ZmqEventLoopPolicy())
    asyncio.get_event_loop().run_until_complete(go())

Requirements
------------

- Python 3.3+

- pyzmq 13.1+

- asyncio http://code.google.com/p/tulip/ or Python 3.4+

- optional submodule aiozmq.rpc requires msgpack-python



License
-------

aiozmq is offered under the BSD license.
