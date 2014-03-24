"""Private utility functions."""

from collections import ChainMap
from datetime import datetime, date, time, timedelta, tzinfo
from functools import partial
from pickle import dumps, loads, HIGHEST_PROTOCOL

from msgpack import ExtType, packb, unpackb


_default = {
    127: (datetime, partial(dumps, protocol=HIGHEST_PROTOCOL), loads),
    126: (date, partial(dumps, protocol=HIGHEST_PROTOCOL), loads),
    125: (time, partial(dumps, protocol=HIGHEST_PROTOCOL), loads),
    124: (timedelta, partial(dumps, protocol=HIGHEST_PROTOCOL), loads),
    123: (tzinfo, partial(dumps, protocol=HIGHEST_PROTOCOL), loads),
}


class _Packer:

    def __init__(self, *, translators=None):
        if translators is None:
            translators = _default
        else:
            translators = ChainMap(translators, _default)
        self.translators = translators

    def packb(self, data):
        return packb(data, encoding='utf-8', use_bin_type=True,
                     default=self.ext_type_pack_hook)

    def unpackb(self, packed):
        return unpackb(packed, use_list=True, encoding='utf-8',
                       ext_hook=self.ext_type_unpack_hook)

    def ext_type_pack_hook(self, obj):
        for code, (cls, packer, unpacker) in self.translators.items():
            if isinstance(obj, cls):
                return ExtType(code, packer(obj))
        else:
            raise TypeError("Unknown type: {!r}".format(obj))

    def ext_type_unpack_hook(self, code, data):
        try:
            cls, packer, unpacker = self.translators[code]
            return unpacker(data)
        except KeyError:
            return ExtType(code, data)
