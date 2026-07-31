import unittest
from mpos.time_zone import TimeZone
from mpos.time_zones import TIME_ZONE_MAP


class TestTimeZoneToPosix(unittest.TestCase):

    def test_none_returns_gmt0(self):
        self.assertEqual(TimeZone.timezone_to_posix_time_zone(None), "GMT0")

    def test_unknown_timezone_returns_gmt0(self):
        self.assertEqual(TimeZone.timezone_to_posix_time_zone("Mars/Olympus"), "GMT0")

    def test_empty_string_returns_gmt0(self):
        self.assertEqual(TimeZone.timezone_to_posix_time_zone(""), "GMT0")

    def test_abidjan(self):
        self.assertEqual(TimeZone.timezone_to_posix_time_zone("Africa/Abidjan"), "GMT0")

    def test_new_york(self):
        result = TimeZone.timezone_to_posix_time_zone("America/New_York")
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_los_angeles(self):
        result = TimeZone.timezone_to_posix_time_zone("America/Los_Angeles")
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_london(self):
        result = TimeZone.timezone_to_posix_time_zone("Europe/London")
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_tokyo(self):
        result = TimeZone.timezone_to_posix_time_zone("Asia/Tokyo")
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_all_known_timezones_return_non_empty_string(self):
        for tz_name in TIME_ZONE_MAP:
            result = TimeZone.timezone_to_posix_time_zone(tz_name)
            self.assertIsInstance(result, str)
            self.assertTrue(len(result) > 0, f"Empty result for {tz_name}")


class TestGetTimezones(unittest.TestCase):

    def test_returns_list(self):
        tzs = TimeZone.get_timezones()
        self.assertIsInstance(tzs, list)

    def test_returns_sorted_list(self):
        tzs = TimeZone.get_timezones()
        self.assertEqual(tzs, sorted(tzs))

    def test_contains_common_timezones(self):
        tzs = TimeZone.get_timezones()
        self.assertIn("Africa/Abidjan", tzs)
        self.assertIn("Pacific/Auckland", tzs)

    def test_length_matches_map(self):
        tzs = TimeZone.get_timezones()
        self.assertEqual(len(tzs), len(TIME_ZONE_MAP))
