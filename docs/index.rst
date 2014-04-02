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
  :class:`~aiozmq.ZmqEventLoop`.
- Implements installable policy for ZeroMQ event loop (see
  :ref:`install-aiozmq-policy`), **required** for ZeroMQ sockets layer.
- Provides :class:`~aiozmq.ZmqTransport` and :class:`~aiozmq.ZmqProtocol`
- Provides RPC :ref:`aiozmq-rpc-rpc` :ref:`aiozmq-rpc-pushpull` and
  :ref:`aiozmq-rpc-pubsub` patterns for *remote calls*.

Library Installation
--------------------

The :ref:`core <aiozmq-core>` requires only :term:`pyzmq` and can
be installed (with pyzmq as dependency) by executing::

   pip3 install aiozmq

Also probably you want to use :mod:`aiozmq.rpc`.


.. _aiozmq-install-msgpack:

RPC module is **optional** and requires :term:`msgpack`. You can
install *msgpack-python* by executing::

  pip3 install msgpack-python

.. note::

   *aiozmq* can be executed by *Python 3* only. The most Linux
   distributions uses *pip3* for installing *Python 3 libraries*.
   But your system may be using *Python 3* by default than try
   just *pip* instead of *pip3*. The same may be true for *virtualenv*,
   *travis continuous integration system* etc.

Source code
-----------

The project is hosted on `GitHub`_

Please feel free to file an issue on `bug tracker
<https://github.com/aio-libs/aiozmq/issues>`_ if you have found a bug
or have some suggestion for library improvement.

The library uses `Travis <https://travis-ci.org/aio-libs/aiozmq>`_ for
Continious Integration.


Dependencies
------------

- Python 3.3 and :term:`asyncio` or Python 3.4+
- :term:`ZeroMQ` 3.2+
- :term:`pyzmq` 13.1+ (did not test with earlier versions)
- aiozmq.rpc requires :term:`msgpack`

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

    import aiozmq.rpc

    class ServerHandler(aiozmq.rpc.AttrHandler):
        @aiozmq.rpc.method
        def remote_func(self, a:int, b:int) -> int:
            return a + b

    @asyncio.coroutine
    def go():
        server = yield from aiozmq.rpc.serve_rpc(
            ServerHandler(), bind='tcp://127.0.0.1:5555')
        client = yield from aiozmq.rpc.connect_rpc(
            connect='tcp://127.0.0.1:5555')

        ret = yield from client.rpc.remote_func(1, 2)
        assert 3 == ret

        server.close()
        client.close()

    asyncio.get_event_loop().run_until_complete(go())

.. note:: To execute the example you need to :ref:`install
   msgpack<aiozmq-install-msgpack>` first.

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

.. toctree::

   core
   rpc
   examples
   glossary
