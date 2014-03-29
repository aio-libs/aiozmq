import asyncio
import builtins
import inspect
from types import MethodType

from .base import AbstractHandler, NotFoundError, ParametersError


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
        return _Waiter(fut, timeout=self._timeout, loop=self._proto.loop)


class _Waiter:

    __slots__ = ('_fut', '_timeout', '_loop')

    def __init__(self, fut, *, timeout=None, loop=None):
        self._fut = fut
        self._timeout = timeout
        self._loop = loop

    def __iter__(self):
        return (yield from asyncio.wait_for(self._fut, self._timeout,
                                            loop=self._loop))


class _MethodDispatcher:

    def dispatch(self, name):
        if not name:
            raise NotFoundError(name)
        namespaces, sep, method = name.rpartition('.')
        handler = self.handler
        if namespaces:
            for part in namespaces.split('.'):
                try:
                    handler = handler[part]
                except KeyError:
                    raise NotFoundError(name)
                else:
                    if not isinstance(handler, AbstractHandler):
                        raise NotFoundError(name)

        try:
            func = handler[method]
        except KeyError:
            raise NotFoundError(name)
        else:
            if isinstance(func, MethodType):
                holder = func.__func__
            else:
                holder = func
            if not hasattr(holder, '__rpc__'):
                raise NotFoundError(name)
            return func


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


def _check_func_arguments(func, args, kwargs):
    """Utility function for validating function arguments

    Returns validated (args, kwargs, return annotation) tuple
    """
    try:
        sig = inspect.signature(func)
        bargs = sig.bind(*args, **kwargs)
    except TypeError as exc:
        raise ParametersError(repr(exc)) from exc
    else:
        arguments = bargs.arguments
        for name, param in sig.parameters.items():
            if param.annotation is param.empty:
                continue
            val = arguments.get(name, param.default)
            # NOTE: default value always being passed through annotation
            #       is it realy neccessary?
            try:
                arguments[name] = param.annotation(val)
            except (TypeError, ValueError) as exc:
                raise ParametersError('Invalid value for argument {!r}: {!r}'
                                      .format(name, exc)) from exc
        if sig.return_annotation is not sig.empty:
            return bargs.args, bargs.kwargs, sig.return_annotation
        return bargs.args, bargs.kwargs, None
