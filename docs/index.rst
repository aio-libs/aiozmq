.. aiozmq documentation master file, created by
   sphinx-quickstart on Mon Mar 17 15:12:47 2014.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

aiozmq
====================================

ZeroMQ integration with asyncio (:pep:`3156`).

.. _GitHub: https://github.com/aio-libs/aiozmq


Features
--------

- Implements :mod:`asyncio` event loop for :term:`ZeroMQ` sockets via
  :class:`~aiozmq.ZmqEventLoop`
- Has installable policy for ZerMQ event loop (see :ref:`install-aiozmq-policy`)
- Provides :class:`~aiozmq.ZmqTransport` and :class:`~aiozmq.ZmqProtocol`
- Provides RPC :ref:`client <aiozmq-rpc-client>` and :ref:`server
  <aiozmq-rpc-server>` based on :term:`ZeroMQ` *DEALER/ROUTER* sockets


Library Installation
--------------------

::

   pip install aiozmq

Source code
-----------

The project is hosted on `GitHub`_

aiozmq uses `Travis <https://travis-ci.org/aio-libs/aiozmq>`_ for
Continious Integration.  Current status of `master branch <GitHub>`_
is |travis-st|.

.. |travis-st| image:: https://travis-ci.org/aio-libs/aiozmq.svg?branch=master
   :target: https://travis-ci.org/aio-libs/aiozmq


Dependencies
------------

- Python 3.3 and :term:`asyncio` or Python 3.4+
- :term:`pyzmq`
- aiozmq.rpc requires :term:`msgpack` and :term:`trafaret`

Authors and License
-------------------

The ``aiozmq`` package is initially written by Nikolay Kim, now
maintained by Andrew Svetlov.  It's BSD licensed and freely available.
Feel free to improve this package and send a pull request to `GitHub`_.

Getting Started
---------------

At first you need to install aiozmq *policy* to use ZeroMQ socket layer::

    import asyncio
    import aiozmq

    asyncio.set_event_loop_policy(aiozmq.ZmqEventLoopPolicy())

For details please take a look on :ref:`install-aiozmq-policy`.

After that you probably would like to use RPC::

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

    asyncio.get_event_loop().run_until_complete(go())



Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

.. toctree::

   examples
   low-level
   rpc
   glossary
