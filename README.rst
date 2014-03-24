asyncio integration with ZeroMQ
=============================

Experimental asyncio (PEP 3156) compatibility with ZeroMQ.


Documentation
-------------

See http://aiozmq.readthedocs.org

RPC Example
-----------

Simple client-server RPC example::

    import aiozmq, aiozmq.rpc
    import asyncio

    asyncio.set_event_loop_policy(aiozmq.ZmqEventLoopPolicy())

    loop = asyncio.get_event_loop()

    class ServerHandler(aiozmq.AttrHandler):
        @aiozmq.method
        def remote_func(self, a, b):
            retuirn a + b

    server = loop.run_until_complete(
        aiozmq.rpc.start_server(ServerHandler(), bind='tpc://127.0.0.1:5555'))

    client = loop.run_until_complete(
        aiozmq.rpc.open_client(connect='tpc://127.0.0.1:5555'))

    @asyncio.coroutine
    def communicate(client):
        ret = yield from client.rpc.remote_func(1, 3)
        assert 3 == ret

        try:
            yield from client.rpc.unknown_func()
        except aiozmq.rpc.NotFoundError:
            pass

    loop.run_until_complete(communicate(client))

    server.close()
    client.close()
    loop.close()

Requirements
------------

- Python 3.3+

- pyzmq 13.1

- asyncio http://code.google.com/p/tulip/ or Python 3.4+



License
-------

aiozmq is offered under the BSD license.
