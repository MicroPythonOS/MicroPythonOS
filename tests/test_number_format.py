import unittest
from mpos.number_format import NumberFormat, DEFAULT_FORMAT, NUMBER_FORMAT_MAP, _insert_thousands


class TestInsertThousands(unittest.TestCase):

    def test_no_separator_short_number(self):
        self.assertEqual(_insert_thousands("12", ""), "12")

    def test_no_separator_long_number(self):
        self.assertEqual(_insert_thousands("1234567", ""), "1234567")

    def test_comma_separator_short(self):
        self.assertEqual(_insert_thousands("12", ","), "12")

    def test_comma_separator_exactly_thousands(self):
        self.assertEqual(_insert_thousands("123", ","), "123")

    def test_comma_separator_one_comma(self):
        self.assertEqual(_insert_thousands("1234", ","), "1,234")

    def test_comma_separator_two_commas(self):
        self.assertEqual(_insert_thousands("1234567", ","), "1,234,567")

    def test_comma_separator_three_commas(self):
        self.assertEqual(_insert_thousands("1234567890", ","), "1,234,567,890")

    def test_dot_separator(self):
        self.assertEqual(_insert_thousands("1234567", "."), "1.234.567")

    def test_space_separator(self):
        self.assertEqual(_insert_thousands("1234567", " "), "1 234 567")

    def test_apos_separator(self):
        self.assertEqual(_insert_thousands("1234567", "'"), "1'234'567")


class TestNumberFormatSeparators(unittest.TestCase):

    def setUp(self):
        NumberFormat.number_format_preference = None

    def test_default_separators_when_none(self):
        NumberFormat.number_format_preference = None
        dec, thou = NumberFormat.get_separators()
        self.assertEqual((dec, thou), NUMBER_FORMAT_MAP[DEFAULT_FORMAT])

    def test_comma_dot(self):
        NumberFormat.number_format_preference = "comma_dot"
        self.assertEqual(NumberFormat.get_separators(), (".", ","))

    def test_dot_comma(self):
        NumberFormat.number_format_preference = "dot_comma"
        self.assertEqual(NumberFormat.get_separators(), (",", "."))

    def test_space_comma(self):
        NumberFormat.number_format_preference = "space_comma"
        self.assertEqual(NumberFormat.get_separators(), (",", " "))

    def test_apos_dot(self):
        NumberFormat.number_format_preference = "apos_dot"
        self.assertEqual(NumberFormat.get_separators(), (".", "'"))

    def test_under_dot(self):
        NumberFormat.number_format_preference = "under_dot"
        self.assertEqual(NumberFormat.get_separators(), (".", "_"))

    def test_none_dot(self):
        NumberFormat.number_format_preference = "none_dot"
        self.assertEqual(NumberFormat.get_separators(), (".", ""))

    def test_none_comma(self):
        NumberFormat.number_format_preference = "none_comma"
        self.assertEqual(NumberFormat.get_separators(), (",", ""))

    def test_unknown_format_falls_back_to_default(self):
        NumberFormat.number_format_preference = "bogus_format"
        self.assertEqual(NumberFormat.get_separators(), NUMBER_FORMAT_MAP[DEFAULT_FORMAT])


class TestFormatNumber(unittest.TestCase):

    def setUp(self):
        NumberFormat.number_format_preference = None

    def test_int_zero(self):
        self.assertEqual(NumberFormat.format_number(0), "0")

    def test_int_positive_small(self):
        self.assertEqual(NumberFormat.format_number(5), "5")

    def test_int_positive_with_comma(self):
        NumberFormat.number_format_preference = "comma_dot"
        self.assertEqual(NumberFormat.format_number(1234), "1,234")

    def test_int_positive_large(self):
        NumberFormat.number_format_preference = "comma_dot"
        self.assertEqual(NumberFormat.format_number(1234567890), "1,234,567,890")

    def test_int_negative(self):
        NumberFormat.number_format_preference = "comma_dot"
        self.assertEqual(NumberFormat.format_number(-1234), "-1,234")

    def test_int_european_format(self):
        NumberFormat.number_format_preference = "dot_comma"
        self.assertEqual(NumberFormat.format_number(1234567), "1.234.567")

    def test_int_space_format(self):
        NumberFormat.number_format_preference = "space_comma"
        self.assertEqual(NumberFormat.format_number(1234), "1 234")

    def test_int_none_dot_format(self):
        NumberFormat.number_format_preference = "none_dot"
        self.assertEqual(NumberFormat.format_number(1234), "1234")

    def test_int_none_comma_format(self):
        NumberFormat.number_format_preference = "none_comma"
        self.assertEqual(NumberFormat.format_number(1234), "1234")

    def test_float_default_decimals(self):
        NumberFormat.number_format_preference = "comma_dot"
        self.assertEqual(NumberFormat.format_number(1234.5), "1,234.5")

    def test_float_with_nonzero_decimals(self):
        NumberFormat.number_format_preference = "comma_dot"
        self.assertEqual(NumberFormat.format_number(1234.56), "1,234.56")

    def test_float_explicit_decimals(self):
        NumberFormat.number_format_preference = "comma_dot"
        self.assertEqual(NumberFormat.format_number(1234.5678, decimals=3), "1,234.568")

    def test_float_zero_decimals_rounds(self):
        NumberFormat.number_format_preference = "comma_dot"
        self.assertEqual(NumberFormat.format_number(1234.0, decimals=0), "1,234")

    def test_float_rounds_with_zero_decimals(self):
        NumberFormat.number_format_preference = "comma_dot"
        self.assertEqual(NumberFormat.format_number(1234.5, decimals=0), "1,235")

    def test_float_trailing_zeros_stripped(self):
        NumberFormat.number_format_preference = "comma_dot"
        self.assertEqual(NumberFormat.format_number(1234.0), "1,234")

    def test_float_all_trailing_zeros_stripped(self):
        NumberFormat.number_format_preference = "comma_dot"
        self.assertEqual(NumberFormat.format_number(1000.00), "1,000")

    def test_float_zero(self):
        self.assertEqual(NumberFormat.format_number(0.0), "0")

    def test_float_zero_with_decimals(self):
        NumberFormat.number_format_preference = "comma_dot"
        self.assertEqual(NumberFormat.format_number(0.0, decimals=2), "0")

    def test_float_negative(self):
        NumberFormat.number_format_preference = "comma_dot"
        self.assertEqual(NumberFormat.format_number(-1234.56), "-1,234.56")

    def test_float_negative_small(self):
        NumberFormat.number_format_preference = "comma_dot"
        self.assertEqual(NumberFormat.format_number(-0.5), "-0.5")

    def test_float_european_decimals(self):
        NumberFormat.number_format_preference = "dot_comma"
        self.assertEqual(NumberFormat.format_number(1234.56), "1.234,56")

    def test_float_space_comma(self):
        NumberFormat.number_format_preference = "space_comma"
        self.assertEqual(NumberFormat.format_number(1234.56), "1 234,56")

    def test_float_apos_dot(self):
        NumberFormat.number_format_preference = "apos_dot"
        self.assertEqual(NumberFormat.format_number(1234.56), "1'234.56")

    def test_float_under_dot(self):
        NumberFormat.number_format_preference = "under_dot"
        self.assertEqual(NumberFormat.format_number(1234.56), "1_234.56")

    def test_int_with_explicit_decimals_nonzero(self):
        NumberFormat.number_format_preference = "comma_dot"
        self.assertEqual(NumberFormat.format_number(42, decimals=2), "42")

    def test_int_negative_with_explicit_decimals_nonzero(self):
        NumberFormat.number_format_preference = "comma_dot"
        self.assertEqual(NumberFormat.format_number(-42, decimals=2), "-42")

    def test_float_with_decimal_retains_trailing_when_nonzero(self):
        NumberFormat.number_format_preference = "comma_dot"
        self.assertEqual(NumberFormat.format_number(1.23, decimals=3), "1.23")


class TestGetFormatOptions(unittest.TestCase):

    def test_returns_correct_number_of_options(self):
        self.assertEqual(len(NumberFormat.get_format_options()), len(NUMBER_FORMAT_MAP))

    def test_all_keys_in_map(self):
        for _label, key in NumberFormat.get_format_options():
            self.assertIn(key, NUMBER_FORMAT_MAP)

    def test_returns_list_of_tuples(self):
        options = NumberFormat.get_format_options()
        self.assertIsInstance(options, list)
        for opt in options:
            self.assertIsInstance(opt, tuple)
            self.assertEqual(len(opt), 2)
