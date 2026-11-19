import unittest

import drivers.indev.gt911 as gt911
from drivers.indev.focaltech_touch import parse_touch_points as parse_focaltech_points
from drivers.indev.gt911 import parse_touch_points as parse_gt911_points


class TestGT911Parsing(unittest.TestCase):
    def test_two_points(self):
        buf = bytearray(2 * 8)
        buf[0] = 0x2C
        buf[1] = 0x01
        buf[2] = 0xC8
        buf[3] = 0x00
        buf[4] = 20
        buf[8] = 0x14
        buf[9] = 0x00
        buf[10] = 0x0A
        buf[11] = 0x00
        buf[12] = 18
        self.assertEqual(
            parse_gt911_points(buf, 2),
            [(None, 300, 200), (None, 20, 10)],
        )

    def test_zero_padding_is_skipped(self):
        buf = bytearray(5 * 8)
        buf[0] = 0x14
        buf[2] = 0x0A
        buf[4] = 18
        self.assertEqual(parse_gt911_points(buf, 5), [(None, 20, 10)])


class FakeIndevDrv:
    def __init__(self):
        self.wait_release_calls = 0

    def wait_release(self):
        self.wait_release_calls += 1


class FakeGT911:
    PRESSED = 1
    RELEASED = 0

    def __init__(self):
        self.reports = []
        self._rx_buf = bytearray(1 + 5 * 8)
        self._rx_mv = memoryview(self._rx_buf)
        self._interrupt_pin = None
        self._interrupt_flag = False
        self._touch_points = []
        self._multi_touch_active = False
        self._indev_drv = FakeIndevDrv()
        self._GT911__x = 0
        self._GT911__y = 0
        self._GT911__last_state = 0

    def _read_reg(self, reg, num_bytes=None, buf=None):
        status, points = self.reports[0]
        if reg == 0x814E:
            self._rx_buf[0] = status
        elif reg == 0x8150:
            for index, point in enumerate(points):
                offset = index * 8
                _, x, y = point
                self._rx_buf[offset] = x & 0xFF
                self._rx_buf[offset + 1] = x >> 8
                self._rx_buf[offset + 2] = y & 0xFF
                self._rx_buf[offset + 3] = y >> 8
                self._rx_buf[offset + 4] = 20
            self.reports.pop(0)

    def _write_reg(self, reg, value=None, buf=None):
        pass

    def _calc_coords(self, x, y):
        return x, y


class TestGT911MultiTouch(unittest.TestCase):
    def test_two_points_suppress_pointer_events(self):
        fake = FakeGT911()
        fake.reports = [(0x82, [(None, 100, 100), (None, 140, 120)])]
        self.assertTrue(gt911.GT911._get_coords(fake) is None)
        self.assertEqual(fake._indev_drv.wait_release_calls, 1)
        self.assertEqual(gt911.GT911.get_touch_count(fake), 2)
        self.assertEqual(
            gt911.GT911.get_touches(fake),
            [(None, 100, 100), (None, 140, 120)],
        )

    def test_sustained_two_fingers_wait_release_once(self):
        fake = FakeGT911()
        fake.reports = [
            (0x82, [(None, 100, 100), (None, 140, 120)]),
            (0x82, [(None, 110, 100), (None, 150, 120)]),
        ]
        gt911.GT911._get_coords(fake)
        gt911.GT911._get_coords(fake)
        self.assertEqual(fake._indev_drv.wait_release_calls, 1)

    def test_release_clears_suppression(self):
        fake = FakeGT911()
        fake.reports = [
            (0x82, [(None, 100, 100), (None, 140, 120)]),
            (0x80, []),
            (0x80, []),
        ]
        gt911.GT911._get_coords(fake)
        gt911.GT911._get_coords(fake)
        self.assertFalse(fake._multi_touch_active)
        self.assertEqual(gt911.GT911.get_touch_count(fake), 0)

    def test_single_point_is_pressed(self):
        fake = FakeGT911()
        fake.reports = [(0x81, [(None, 50, 60)])]
        self.assertEqual(gt911.GT911._get_coords(fake), (1, 50, 60))
        self.assertEqual(gt911.GT911.get_touches(fake), [(None, 50, 60)])


class TestFocalTechParsing(unittest.TestCase):
    def test_two_points(self):
        buf = bytearray(1 + 2 * 6)
        buf[0] = 0x02
        buf[1] = 0x01
        buf[2] = 0x2C
        buf[3] = 0x00
        buf[4] = 0xC8
        buf[7] = 0x00
        buf[8] = 0x14
        buf[9] = 0x00
        buf[10] = 0x0A
        self.assertEqual(
            parse_focaltech_points(buf, 2, None),
            [(None, 300, 200), (None, 20, 10)],
        )

    def test_factors(self):
        buf = bytearray(1 + 6)
        buf[1] = 0x00
        buf[2] = 0x64
        buf[3] = 0x00
        buf[4] = 0x32
        self.assertEqual(
            parse_focaltech_points(buf, 1, (2.0, 2.0)),
            [(None, 50, 25)],
        )
