import unittest

from drivers.indev.usb_hid import BootKeyboardParser, BootMouseParser, find_parser, parse_boot_mouse_report


class TestParseBootMouseReport(unittest.TestCase):
    def test_idle_report(self):
        self.assertEqual(parse_boot_mouse_report(bytes([0x00, 0x00, 0x00])), (0, 0, 0, 0))

    def test_left_button_and_positive_deltas(self):
        self.assertEqual(parse_boot_mouse_report(bytes([0x01, 0x05, 0x03])), (1, 5, 3, 0))

    def test_negative_deltas_are_sign_extended(self):
        self.assertEqual(parse_boot_mouse_report(bytes([0x02, 0xFF, 0xFB])), (2, -1, -5, 0))

    def test_button_bits_masked_to_three(self):
        self.assertEqual(parse_boot_mouse_report(bytes([0xFF, 0x00, 0x00]))[0], 0x07)

    def test_wheel_up(self):
        self.assertEqual(parse_boot_mouse_report(bytes([0x00, 0x00, 0x00, 0x01])), (0, 0, 0, 1))

    def test_wheel_down_is_signed(self):
        self.assertEqual(parse_boot_mouse_report(bytes([0x00, 0x00, 0x00, 0xFF])), (0, 0, 0, -1))

    def test_long_report_parses_first_bytes(self):
        self.assertEqual(
            parse_boot_mouse_report(bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08])),
            (1, 2, 3, 4),
        )

    def test_short_report_is_none(self):
        self.assertIsNone(parse_boot_mouse_report(bytes([0x01, 0x02])))
        self.assertIsNone(parse_boot_mouse_report(bytes([])))

    def test_none_report_is_none(self):
        self.assertIsNone(parse_boot_mouse_report(None))


class TestParserRegistry(unittest.TestCase):
    def test_boot_mouse_match(self):
        parser = find_parser(1, 2)
        self.assertIsInstance(parser, BootMouseParser)
        self.assertEqual(parser.kind, "mouse")

    def test_boot_keyboard_match(self):
        parser = find_parser(1, 1)
        self.assertIsInstance(parser, BootKeyboardParser)
        self.assertEqual(parser.kind, "keyboard")

    def test_unknown_proto_is_none(self):
        self.assertIsNone(find_parser(0, 0))
        self.assertIsNone(find_parser(1, 0))

    def test_mouse_parser_uses_report_fn(self):
        parser = BootMouseParser()
        self.assertEqual(parser.parse(bytes([0x01, 0x0A, 0xF6])), (1, 10, -10, 0))
        self.assertIsNone(parser.parse(bytes([0x01])))
