.. _glossary:


********
Glossary
********

.. if you add new entries, keep the alphabetical sorting!

.. glossary::

   asyncio

      Reference implementation of :pep:`3156`

      See https://pypi.python.org/pypi/asyncio/

   callable

      Any object that can be called. Use :func:`callable` to check
      that.

   endpoint

      A string consisting of two parts as follows:
      *transport://address.*

      The transport part specifies the underlying transport protocol to use.
      The meaning of the address part is specific to the underlying
      transport protocol selected.

      The following transports are defined:

      inproc
         local in-process (inter-thread) communication transport,
         see http://api.zeromq.org/master:zmq-inproc.

      ipc
         local inter-process communication transport,
         see http://api.zeromq.org/master:zmq-ipc

      tcp
         unicast transport using TCP,
         see http://api.zeromq.org/master:zmq_tcp

      pgm, epgm
         reliable multicast transport using PGM,
         see http://api.zeromq.org/master:zmq_pgm

   enduser

      Software engeneer who wants to *just use* human-like
      communications via that library.

      We offer that simple API for RPC, Push/Pull and Pub/Sub services.

   msgpack

      Fast and compact binary serialization format.

      See http://msgpack.org/ for the description of the standard.
      https://pypi.python.org/pypi/msgpack/ is the Python implementation.

   pyzmq

      PyZMQ is the Python bindings for :term:`ZeroMQ`.

      See https://github.com/zeromq/pyzmq

   trafaret

      Trafaret is a validation library with support for data structure
      convertors.

      See https://github.com/Deepwalker/trafaret

   ZeroMQ

      ØMQ (also spelled ZeroMQ, 0MQ or ZMQ) is a high-performance
      asynchronous messaging library aimed at use in scalable
      distributed or concurrent applications. It provides a message
      queue, but unlike message-oriented middleware, a ØMQ system can
      run without a dedicated message broker. The library is designed
      to have a familiar socket-style API.

      See http://zeromq.org/
