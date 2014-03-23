.. aiozmq documentation master file, created by
   sphinx-quickstart on Mon Mar 17 15:12:47 2014.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

aiozmq
====================================

ZeroMQ integration with asyncio (:pep:`3156`).

.. _GitHub: https://github.com/fafhrd91/aiozmq


Features
--------

- Implements asyncio (PEP3156) event loop
- Provides ZmqTransport and ZmqProtocol
- Provides RPC client and server based on ZeroMQ DEALER/ROUTER sockets

Library Installation
--------------------

::

   pip install aiozmq

Source code
-----------

The project is hosted on `GitHub`_

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


.. _install-aiozmq-policy:

Installing ZeroMQ event loop
----------------------------

To use ZeroMQ layer you need to install event loop first.

The recommended way is to setup global event loop *policy*::

    import asyncio
    import aiozmq

    asyncio.set_event_loop_policy(aiozmq.ZmqEventLoopPolicy())

That installs :class:`ZmqEventLoopPolicy` globally. After installing
you can get event loop instance from main thread by
:func:`asyncio.get_event_loop` call::

    loop = asyncio.get_event_loop()

If you need to execute event loop in own (non-main) thread you have to
setup it first::

     import threading

     def thread_func():
         loop = asyncio.new_event_loop()
         asyncio.set_event_loop()

         loop.run_forever()

     thread = threading.Thread(target=thread_func)
     thread.start()



Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

.. toctree::

   examples
   reference-low-level
   reference-rpc
   glossary
