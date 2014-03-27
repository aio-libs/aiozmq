import asyncio
import zmq


@asyncio.coroutine
def connect_pubsub(*, connect=None, bind=None, loop=None, translators=None):
    if loop is None:
        loop = asyncio.get_event_loop()

    transp, proto = yield from loop.create_zmq_connection(
        lambda: object(),
        zmq.PUB, connect=connect, bind=bind)
    return


@asyncio.coroutine
def serve_pubsub(handler, *, connect=None, bind=None, loop=None,
                 translators=None):
    if loop is None:
        loop = asyncio.get_event_loop()
    transp, proto = yield from loop.create_zmq_connection(
        lambda: object(),
        zmq.SUB, connect=connect, bind=bind)
    return
