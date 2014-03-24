"""Private utility functions."""

from collections import ChainMap
from datetime import datetime, date, time, timedelta, tzinfo
from functools import partial
from pickle import dumps, loads, HIGHEST_PROTOCOL

from msgpack import ExtType
from msgpack.fallback import Packer, Unpacker


_default = {
    127: (datetime, partial(dumps, protocol=HIGHEST_PROTOCOL), loads),
    126: (date, partial(dumps, protocol=HIGHEST_PROTOCOL), loads),
    125: (time, partial(dumps, protocol=HIGHEST_PROTOCOL), loads),
    124: (timedelta, partial(dumps, protocol=HIGHEST_PROTOCOL), loads),
    123: (tzinfo, partial(dumps, protocol=HIGHEST_PROTOCOL), loads),
}


class _Base:

    def __init__(self, *, translators=None):
        if translators is None:
            translators = _default
        else:
            translators = ChainMap(translators, _default)
        self.translators = translators


class _Packer(Packer, _Base):

    def __init__(self, *, translators=None):
        _Base.__init__(self, translators=translators)
        Packer.__init__(self,
                        default=self.ext_type_pack_hook,
                        encoding='utf-8', use_bin_type=True)

    def ext_type_pack_hook(self, obj):
        for code, (cls, packer, unpacker) in self.translators.items():
            if isinstance(obj, cls):
                return ExtType(code, packer(obj))
        else:
            raise TypeError("Unknown type: {!r}".format(obj))


class _Unpacker(Unpacker, _Base):

    def __init__(self, file_like=None, read_size=0, *, translators=None):
        _Base.__init__(self, translators=translators)
        Unpacker.__init__(self,
                          file_like, read_size, use_list=True,
                          encoding='utf-8',
                          ext_hook=self.ext_type_unpack_hook)

    def ext_type_unpack_hook(self, code, data):
        try:
            cls, packer, unpacker = self.translators[code]
            return unpacker(data)
        except KeyError:
            return ExtType(code, data)
