import asyncio
import builtins

from .base import NotFoundError, ParametersError


class _MethodCall:

    __slots__ = ('_proto', '_timeout', '_names')

    def __init__(self, proto, timeout=None, names=()):
        self._proto = proto
        self._timeout = timeout
        self._names = names

    def __getattr__(self, name):
        return self.__class__(self._proto, self._timeout,
                              self._names + (name,))

    def __call__(self, *args, **kwargs):
        if not self._names:
            raise ValueError('RPC method name is empty')
        fut = self._proto.call('.'.join(self._names), args, kwargs)
        loop = self._proto.loop
        return asyncio.Task(asyncio.wait_for(fut,
                                             timeout=self._timeout,
                                             loop=loop),
                            loop=loop)


def _fill_error_table():
    # Fill error table with standard exceptions
    error_table = {}
    for name in dir(builtins):
        val = getattr(builtins, name)
        if isinstance(val, type) and issubclass(val, Exception):
            error_table['builtins.'+name] = val
    error_table['aiozmq.rpc.base.NotFoundError'] = NotFoundError
    error_table['aiozmq.rpc.base.ParametersError'] = ParametersError
    return error_table
