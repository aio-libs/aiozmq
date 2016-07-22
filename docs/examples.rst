Examples of aiozmq usage
========================

There is a list of examples from `aiozmq/examples <https://github.com/aio-libs/aiozmq/tree/master/examples>`_

Every example is a correct tiny python program.

.. _aiozmq-examples-core-dealer-router:

Simple DEALER-ROUTER pair implemented on Core level
---------------------------------------------------

.. literalinclude:: ../examples/core_dealer_router.py

.. _aiozmq-examples-stream-dealer-router:

DEALER-ROUTER pair implemented with streams
-------------------------------------------

.. literalinclude:: ../examples/stream_dealer_router.py

.. _aiozmq-examples-rpc-rpc:

Remote Procedure Call
---------------------

.. literalinclude:: ../examples/rpc_simple.py


.. _aiozmq-examples-rpc-pipeline:

Pipeline aka Notifier
---------------------

.. literalinclude:: ../examples/rpc_pipeline.py


.. _aiozmq-examples-rpc-pubsub:

Publish-Subscribe
-----------------

.. literalinclude:: ../examples/rpc_pubsub.py


.. _aiozmq-examples-rpc-exception-trasnslator:

Translation RPC exceptions back to client
-----------------------------------------

.. literalinclude:: ../examples/rpc_exception_translator.py


.. _aiozmq-examples-rpc-custom-value-trasnslator:

Translation instances of custom classes via RPC
------------------------------------------------

.. literalinclude:: ../examples/rpc_custom_translator.py


.. _aiozmq-examples-rpc-incorrect-calls:

Validation of RPC methods
--------------------------

.. literalinclude:: ../examples/rpc_incorrect_calls.py


.. _aiozmq-examples-rpc-subhandlers:

RPC lookup in nested namespaces
-------------------------------

.. literalinclude:: ../examples/rpc_with_subhandlers.py


.. _aiozmq-examples-rpc-dict-handler:

Use dict as RPC lookup table
----------------------------

.. literalinclude:: ../examples/rpc_dict_handler.py


.. _aiozmq-examples-rpc-dynamic-handler:

Use dynamic RPC lookup
----------------------

.. literalinclude:: ../examples/rpc_dynamic.py


.. _aiozmq-examples-socket-event-monitor:

Socket event monitor
--------------------

.. literalinclude:: ../examples/socket_event_monitor.py

.. _aiozmq-examples-stream-socket-event-monitor:

Stream socket event monitor
---------------------------

.. literalinclude:: ../examples/stream_monitor.py


.. _aiozmq-examples-sync-async:

Synchronous and asynchronous code works together
-------------------------------------------------

.. literalinclude:: ../examples/sync_async.py
