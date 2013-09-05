zmq integration with tulip
==========================

Experimental ZMQ selector for Tulip (PEP 3156).

To use tulip with zmq event loop you have to install new event loop:

   import tulip
   import zmqtulip

   loop = zmqtulip.new_event_loop()
   tulip.set_event_loop(loop)

Otherwise everything works same way as with default event loop.


Requirements
------------

- Python 3.3

- pyzmq 13.0

- tulip http://code.google.com/p/tulip/


License
-------

pyzmqtulip is offered under the BSD license.
