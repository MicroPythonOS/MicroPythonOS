import time
import unittest

import localPTZtime
from mpos.time_zones import TIME_ZONE_MAP


def ts(year, month, day, hour=12):
    return time.mktime((year, month, day, hour, 0, 0, 0, 0, 0))


class TestHours2Secs(unittest.TestCase):

    def test_sign_applies_to_minutes(self):
        self.assertEqual(localPTZtime._hours2secs("-5:30"), -19800)
        self.assertEqual(localPTZtime._hours2secs("-5:45"), -20700)

    def test_unsigned_and_plus(self):
        self.assertEqual(localPTZtime._hours2secs("5:30"), 19800)
        self.assertEqual(localPTZtime._hours2secs("+3:30"), 12600)
        self.assertEqual(localPTZtime._hours2secs("7"), 25200)

    def test_negative_whole_hours(self):
        self.assertEqual(localPTZtime._hours2secs("-1"), -3600)


class TestTzOffset(unittest.TestCase):

    def assertOffset(self, ptz, timestamp, expected):
        self.assertEqual(localPTZtime.tzoffset(timestamp, ptz)[0], expected, ptz)

    def test_half_hour_east_of_utc(self):
        self.assertOffset("IST-5:30", ts(2027, 1, 15), 19800)
        self.assertOffset("<+0545>-5:45", ts(2027, 1, 15), 20700)
        self.assertOffset("<+0330>-3:30", ts(2027, 1, 15), 12600)

    def test_half_hour_east_of_utc_with_dst(self):
        adelaide = "ACST-9:30ACDT,M10.1.0,M4.1.0/3"
        self.assertOffset(adelaide, ts(2027, 1, 15), 37800)
        self.assertOffset(adelaide, ts(2027, 7, 15), 34200)

    def test_half_hour_west_of_utc_unchanged(self):
        st_johns = "NST3:30NDT,M3.2.0,M11.1.0"
        self.assertOffset(st_johns, ts(2027, 1, 15), -12600)
        self.assertOffset(st_johns, ts(2027, 7, 15), -9000)

    def test_explicit_dst_offset(self):
        lord_howe = "<+1030>-10:30<+11>-11,M10.1.0,M4.1.0"
        self.assertOffset(lord_howe, ts(2027, 1, 15), 39600)
        self.assertOffset(lord_howe, ts(2027, 7, 15), 37800)

    def test_negative_dst(self):
        dublin = "IST-1GMT0,M10.5.0,M3.5.0/1"
        self.assertOffset(dublin, ts(2027, 1, 15), 0)
        self.assertOffset(dublin, ts(2027, 7, 15), 3600)

    def test_whole_hours_unchanged(self):
        new_york = "EST5EDT,M3.2.0,M11.1.0"
        self.assertOffset(new_york, ts(2027, 1, 15), -18000)
        self.assertOffset(new_york, ts(2027, 7, 15), -14400)
        self.assertOffset("JST-9", ts(2027, 1, 15), 32400)


class TestTimeZoneMap(unittest.TestCase):

    def test_canada_no_fall_back_from_november_2026(self):
        december = ts(2026, 12, 15)
        self.assertEqual(localPTZtime.tzoffset(december, TIME_ZONE_MAP["America/Vancouver"])[0], -25200)
        self.assertEqual(localPTZtime.tzoffset(december, TIME_ZONE_MAP["America/Edmonton"])[0], -21600)
        self.assertEqual(localPTZtime.tzoffset(december, TIME_ZONE_MAP["America/Winnipeg"])[0], -18000)

    def test_morocco_utc(self):
        self.assertEqual(localPTZtime.tzoffset(ts(2027, 1, 15), TIME_ZONE_MAP["Africa/Casablanca"])[0], 0)

    def test_kolkata(self):
        self.assertEqual(localPTZtime.tzoffset(ts(2027, 1, 15), TIME_ZONE_MAP["Asia/Kolkata"])[0], 19800)


if __name__ == "__main__":
    unittest.main()
