"""Private utility functions."""

from functools import partial
from datetime import datetime, date, time, timedelta
from pickle import dumps, loads, HIGHEST_PROTOCOL

from msgpack import Packer, Unpacker, ExtType


_default = [
    (datetime, partial(dumps, protocol=HIGHEST_PROTOCOL), loads),
    (date, partial(dumps, protocol=HIGHEST_PROTOCOL), loads),
    (time, partial(dumps, protocol=HIGHEST_PROTOCOL), loads),
    (timedelta, partial(dumps, protocol=HIGHEST_PROTOCOL), loads),
    ]



class _Base:

    def __init__(self, *, translators=None):
        if translators is None:
            translators = _default
        else:
            translators = translators + _default
            assert len(translators) < 128, len(translators)
        self.translators = translators


class _Packer(Packer, _Base):

    def __init__(self, *, translators=None):
        _Base.__init__(self, translators=translators)
        Packer.__init__(self,
                        default=self.pack_hook,
                        encoding='utf-8', use_bin_type=True)

    def pack_hook(self, obj):
        for num, (cls, packer, unpacker) in enumerate(self.translators):
            if isinstance(obj, cls):
                return ExtType(num, packer)
        else:
            return obj


class _Unpacker(Unpacker, _Base):

    def __init__(self, file_like=None, read_size=0, *, translators=None):
        _Base.__init__(self, translators=translators)
        Unpacker.__init__(self,
                          file_like, read_size, use_list=True, encoding='utf-8',
                          ext_hook=self.unpack_hook)

    def unpack_hook(self, code, data):
        cls, packer, unpacker = self.translators[code]
        return unpacker(data)
