import unittest
import datetime

from aiozmq.rpc.packer import _Packer

from unittest import mock
from msgpack import ExtType, packb
from pickle import dumps, loads, HIGHEST_PROTOCOL
from functools import partial


class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def __eq__(self, other):
        if isinstance(other, Point):
            return (self.x, self.y) == (other.x, other.y)
        return NotImplemented


class PackerTests(unittest.TestCase):
    def test_packb_simple(self):
        packer = _Packer()
        self.assertEqual(packb("test"), packer.packb("test"))
        self.assertEqual(packb([123]), packer.packb([123]))
        self.assertEqual(packb((123,)), packer.packb([123]))

    def test_unpackb_simple(self):
        packer = _Packer()
        self.assertEqual("test", packer.unpackb(packb("test")))
        self.assertEqual((123,), packer.unpackb(packb([123])))
        self.assertEqual((123,), packer.unpackb(packb((123,))))

    @mock.patch("aiozmq.rpc.packer.ExtType")
    def test_ext_type__date(self, ExtTypeMock):
        packer = _Packer()

        CODE = 127
        dt = datetime.date(2014, 3, 25)
        data = dumps(dt, protocol=HIGHEST_PROTOCOL)

        self.assertEqual(dt, packer.ext_type_unpack_hook(CODE, data))

        packer.ext_type_pack_hook(dt)
        ExtTypeMock.assert_called_once_with(CODE, data)

    @mock.patch("aiozmq.rpc.packer.ExtType")
    def test_ext_type__datetime(self, ExtTypeMock):
        packer = _Packer()

        CODE = 126
        dt = datetime.datetime(2014, 3, 25, 15, 18)
        data = dumps(dt, protocol=HIGHEST_PROTOCOL)

        self.assertEqual(dt, packer.ext_type_unpack_hook(CODE, data))

        packer.ext_type_pack_hook(dt)
        ExtTypeMock.assert_called_once_with(CODE, data)

    @mock.patch("aiozmq.rpc.packer.ExtType")
    def test_ext_type__datetime_tzinfo(self, ExtTypeMock):
        packer = _Packer()

        CODE = 126
        dt = datetime.datetime(2014, 3, 25, 16, 12, tzinfo=datetime.timezone.utc)
        data = dumps(dt, protocol=HIGHEST_PROTOCOL)

        self.assertEqual(dt, packer.ext_type_unpack_hook(CODE, data))

        packer.ext_type_pack_hook(dt)
        ExtTypeMock.assert_called_once_with(CODE, data)

    @mock.patch("aiozmq.rpc.packer.ExtType")
    def test_ext_type__time(self, ExtTypeMock):
        packer = _Packer()

        CODE = 125
        tm = datetime.time(15, 51, 0)
        data = dumps(tm, protocol=HIGHEST_PROTOCOL)

        self.assertEqual(tm, packer.ext_type_unpack_hook(CODE, data))

        packer.ext_type_pack_hook(tm)
        ExtTypeMock.assert_called_once_with(CODE, data)

    @mock.patch("aiozmq.rpc.packer.ExtType")
    def test_ext_type__time_tzinfo(self, ExtTypeMock):
        packer = _Packer()

        CODE = 125
        tm = datetime.time(15, 51, 0, tzinfo=datetime.timezone.utc)
        data = dumps(tm, protocol=HIGHEST_PROTOCOL)

        self.assertEqual(tm, packer.ext_type_unpack_hook(CODE, data))

        packer.ext_type_pack_hook(tm)
        ExtTypeMock.assert_called_once_with(CODE, data)

    @mock.patch("aiozmq.rpc.packer.ExtType")
    def test_ext_type__timedelta(self, ExtTypeMock):
        packer = _Packer()

        CODE = 124
        td = datetime.timedelta(days=1, hours=2, minutes=3, seconds=4)
        data = dumps(td, protocol=HIGHEST_PROTOCOL)

        self.assertEqual(td, packer.ext_type_unpack_hook(CODE, data))

        packer.ext_type_pack_hook(td)
        ExtTypeMock.assert_called_once_with(CODE, data)

    @mock.patch("aiozmq.rpc.packer.ExtType")
    def test_ext_type__tzinfo(self, ExtTypeMock):
        packer = _Packer()

        CODE = 123
        tz = datetime.timezone.utc
        data = dumps(tz, protocol=HIGHEST_PROTOCOL)

        self.assertEqual(tz, packer.ext_type_unpack_hook(CODE, data))

        packer.ext_type_pack_hook(tz)
        ExtTypeMock.assert_called_once_with(CODE, data)

    def test_ext_type_errors(self):
        packer = _Packer()

        with self.assertRaisesRegex(TypeError, "Unknown type: "):
            packer.ext_type_pack_hook(packer)
        self.assertIn(_Packer, packer._pack_cache)
        self.assertIsNone(packer._pack_cache[_Packer])
        # lets try again just for good coverage
        with self.assertRaisesRegex(TypeError, "Unknown type: "):
            packer.ext_type_pack_hook(packer)

        self.assertEqual(ExtType(1, b""), packer.ext_type_unpack_hook(1, b""))

        # TODO: should be more specific errors
        with self.assertRaises(Exception):
            packer.ext_type_unpack_hook(127, b"bad data")

    def test_simple_translators(self):
        translation_table = {
            0: (Point, partial(dumps, protocol=HIGHEST_PROTOCOL), loads),
        }
        packer = _Packer(translation_table=translation_table)

        pt = Point(1, 2)
        data = dumps(pt, protocol=HIGHEST_PROTOCOL)

        self.assertEqual(pt, packer.unpackb(packer.packb(pt)))
        self.assertEqual(ExtType(0, data), packer.ext_type_pack_hook(pt))

        self.assertEqual(pt, packer.ext_type_unpack_hook(0, data))

    def test_override_translators(self):
        translation_table = {
            125: (Point, partial(dumps, protocol=HIGHEST_PROTOCOL), loads),
        }
        packer = _Packer(translation_table=translation_table)

        pt = Point(3, 4)
        data = dumps(pt, protocol=HIGHEST_PROTOCOL)

        dt = datetime.time(15, 2)

        self.assertEqual(ExtType(125, data), packer.ext_type_pack_hook(pt))
        with self.assertRaisesRegex(TypeError, "Unknown type: "):
            packer.ext_type_pack_hook(dt)

    def test_preserve_resolution_order(self):
        class A:
            pass

        class B(A):
            pass

        dump_a = mock.Mock(return_value=b"a")
        load_a = mock.Mock(return_value=A())

        dump_b = mock.Mock(return_value=b"b")
        load_b = mock.Mock(return_value=B())

        translation_table = {
            1: (A, dump_a, load_a),
            2: (B, dump_b, load_b),
        }
        packer = _Packer(translation_table=translation_table)
        self.assertEqual(packer.packb(ExtType(1, b"a")), packer.packb(A()))
        self.assertEqual(packer.packb(ExtType(2, b"b")), packer.packb(B()))
