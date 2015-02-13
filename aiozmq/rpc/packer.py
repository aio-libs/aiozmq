"""Private utility functions."""
from collections import ChainMap
from datetime import datetime, date, time, timedelta, tzinfo
from functools import partial
from pickle import dumps, loads, HIGHEST_PROTOCOL

from msgpack import ExtType, packb, unpackb


_default = {
    127: (date, partial(dumps, protocol=HIGHEST_PROTOCOL), loads),
    126: (datetime, partial(dumps, protocol=HIGHEST_PROTOCOL), loads),
    125: (time, partial(dumps, protocol=HIGHEST_PROTOCOL), loads),
    124: (timedelta, partial(dumps, protocol=HIGHEST_PROTOCOL), loads),
    123: (tzinfo, partial(dumps, protocol=HIGHEST_PROTOCOL), loads),
}


class _Packer:

    def __init__(self, *, translation_table=None):
        if translation_table is None:
            translation_table = _default
        else:
            translation_table = ChainMap(translation_table, _default)
        self.translation_table = translation_table
        self._pack_cache = {}

    def packb(self, data):
        return packb(data, encoding='utf-8', use_bin_type=True,
                     default=self.ext_type_pack_hook)

    def unpackb(self, packed):
        return unpackb(packed, use_list=False, encoding='utf-8',
                       ext_hook=self.ext_type_unpack_hook)

    def ext_type_pack_hook(self, obj, _sentinel=object()):
        obj_class = obj.__class__
        hit = self._pack_cache.get(obj_class, _sentinel)
        if hit is None:
            # packer has been not found by previous long-lookup
            raise TypeError("Unknown type: {!r}".format(obj))
        elif hit is _sentinel:
            # do long-lookup
            for code in sorted(self.translation_table):
                cls, packer, unpacker = self.translation_table[code]
                if isinstance(obj, cls):
                    self._pack_cache[obj_class] = (code, packer)
                    return ExtType(code, packer(obj))
            else:
                self._pack_cache[obj_class] = None
                raise TypeError("Unknown type: {!r}".format(obj))
        else:
            # do shortcut
            code, packer = hit
            return ExtType(code, packer(obj))

    def ext_type_unpack_hook(self, code, data):
        try:
            cls, packer, unpacker = self.translation_table[code]
            return unpacker(data)
        except KeyError:
            return ExtType(code, data)
