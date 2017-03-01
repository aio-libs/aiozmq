import asyncio

from asyncio.base_events import BaseEventLoop
from collections import Set


class _EndpointsSet(Set):

    __slots__ = ('_collection',)

    def __init__(self, collection):
        self._collection = collection

    def __len__(self):
        return len(self._collection)

    def __contains__(self, endpoint):
        return endpoint in self._collection

    def __iter__(self):
        return iter(self._collection)

    def __repr__(self):
        return '{' + ', '.join(sorted(self._collection)) + '}'

    __str__ = __repr__


if hasattr(asyncio, 'ensure_future'):
    ensure_future = asyncio.ensure_future
else:
    ensure_future = asyncio.async   # Deprecated since 3.4.4


# create_future is new in version 3.5.2
if hasattr(BaseEventLoop, 'create_future'):
    def create_future(loop):
        return loop.create_future()
else:
    def create_future(loop):
        return asyncio.Future(loop=loop)
