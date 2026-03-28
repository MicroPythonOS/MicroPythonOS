import unittest
from mpos.number_format import NumberFormat, NUMBER_FORMAT_MAP, DEFAULT_FORMAT


class TestNumberFormat(unittest.TestCase):

    def setUp(self):
        NumberFormat.number_format_preference = DEFAULT_FORMAT

    def test_default_is_us_format(self):
        self.assertEqual(NumberFormat.get_separators(), (".", ","))

    def test_format_int_default(self):
        self.assertEqual(NumberFormat.format_number(1234), "1,234")
        self.assertEqual(NumberFormat.format_number(0), "0")
        self.assertEqual(NumberFormat.format_number(999), "999")
        self.assertEqual(NumberFormat.format_number(1000), "1,000")
        self.assertEqual(NumberFormat.format_number(1234567), "1,234,567")

    def test_format_negative_int(self):
        self.assertEqual(NumberFormat.format_number(-1234), "-1,234")
        self.assertEqual(NumberFormat.format_number(-5), "-5")

    def test_format_float_default(self):
        self.assertEqual(NumberFormat.format_number(1234.56, 2), "1,234.56")
        self.assertEqual(NumberFormat.format_number(1234.50, 2), "1,234.5")
        self.assertEqual(NumberFormat.format_number(1234.00, 2), "1,234")
        self.assertEqual(NumberFormat.format_number(0.5, 2), "0.5")

    def test_format_europe(self):
        NumberFormat.number_format_preference = "dot_comma"
        self.assertEqual(NumberFormat.format_number(1234), "1.234")
        self.assertEqual(NumberFormat.format_number(1234.56, 2), "1.234,56")

    def test_format_french(self):
        NumberFormat.number_format_preference = "space_comma"
        self.assertEqual(NumberFormat.format_number(1234), "1 234")
        self.assertEqual(NumberFormat.format_number(1234.56, 2), "1 234,56")

    def test_format_swiss(self):
        NumberFormat.number_format_preference = "apos_dot"
        self.assertEqual(NumberFormat.format_number(1234), "1'234")
        self.assertEqual(NumberFormat.format_number(1234.56, 2), "1'234.56")

    def test_format_tech(self):
        NumberFormat.number_format_preference = "under_dot"
        self.assertEqual(NumberFormat.format_number(1234), "1_234")
        self.assertEqual(NumberFormat.format_number(1234.56, 2), "1_234.56")

    def test_format_no_thousands_dot(self):
        NumberFormat.number_format_preference = "none_dot"
        self.assertEqual(NumberFormat.format_number(1234567), "1234567")
        self.assertEqual(NumberFormat.format_number(1234.56, 2), "1234.56")

    def test_format_no_thousands_comma(self):
        NumberFormat.number_format_preference = "none_comma"
        self.assertEqual(NumberFormat.format_number(1234567), "1234567")
        self.assertEqual(NumberFormat.format_number(1234.56, 2), "1234,56")

    def test_strip_trailing_zeros(self):
        NumberFormat.number_format_preference = DEFAULT_FORMAT
        self.assertEqual(NumberFormat.format_number(1.10, 2), "1.1")
        self.assertEqual(NumberFormat.format_number(1.00, 2), "1")
        self.assertEqual(NumberFormat.format_number(1.00, 8), "1")

    def test_large_number(self):
        self.assertEqual(NumberFormat.format_number(100000000), "100,000,000")

    def test_get_format_options_returns_list(self):
        options = NumberFormat.get_format_options()
        self.assertIsInstance(options, list)
        self.assertTrue(len(options) == len(NUMBER_FORMAT_MAP))
        for label, key in options:
            self.assertIn(key, NUMBER_FORMAT_MAP)

    def test_unknown_preference_falls_back_to_default(self):
        NumberFormat.number_format_preference = "nonexistent"
        self.assertEqual(NumberFormat.get_separators(), (".", ","))


if __name__ == "__main__":
    unittest.main()
