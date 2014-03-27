import asyncio
import zmq


@asyncio.coroutine
def connect_pipeline(*, connect=None, bind=None, loop=None, translators=None):
    if loop is None:
        loop = asyncio.get_event_loop()
    transp, proto = yield from loop.create_zmq_connection(
        lambda: object(),
        zmq.PUSH, connect=connect, bind=bind)
    return


@asyncio.coroutine
def serve_pipeline(handler, *, connect=None, bind=None, loop=None,
                   translators=None):
    if loop is None:
        loop = asyncio.get_event_loop()
    trans, proto = yield from loop.create_zmq_connection(
        lambda: object(),
        zmq.PULL, connect=connect, bind=bind)
    return
