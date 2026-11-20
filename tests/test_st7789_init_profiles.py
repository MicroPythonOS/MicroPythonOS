import os
import unittest

import lvgl as lv

from drivers.display.st7789 import _st7789_init
from drivers.display.st7789 import _st7789_init_type1
from drivers.display.st7789 import _st7789_init_type2
from drivers.display.st7789 import PROFILE_GENERIC, PROFILE_LEGACY, PROFILE_ST7789V


_VCOMS = 0xBB
_VRHS = 0xC3
_FRCTR2 = 0xC6
_INVON = 0x21
_INVCTR = 0xB4


class _RecordingDisplay:
    def __init__(self):
        self.commands = []
        self._color_byte_order = 0
        self._ORIENTATION_TABLE = (0, 0, 0, 0)
        self._rgb565_byte_swap = False
        self._data_bus = object()
        self._color_space = lv.COLOR_FORMAT.RGB565
        self.display_width = 240
        self.display_height = 320

    def _madctl(self, color_byte_order, orientation_table):
        return 0

    def set_params(self, command, data=None):
        self.commands.append((command, bytes(data) if data is not None else None))


class ST7789InitProfileTests(unittest.TestCase):
    def run_init(self, module):
        display = _RecordingDisplay()
        module.init(display)
        return display.commands

    def data_for(self, commands, command):
        return [data for sent, data in commands if sent == command]

    def commands_without_inversion(self, commands):
        return [(sent, data) for sent, data in commands if sent not in (_INVON, _INVCTR)]

    def test_package_exports_every_init_module(self):
        # The package keeps a reference even after display_driver_framework
        # deletes the init module it used from sys.modules (it does that to
        # reclaim RAM), so check the package attributes, not sys.modules.
        import drivers.display.st7789 as driver
        self.assertIs(driver._st7789_init, _st7789_init)
        self.assertIs(driver._st7789_init_type1, _st7789_init_type1)
        self.assertIs(driver._st7789_init_type2, _st7789_init_type2)

    def test_profile_names_match_the_init_module_numbers(self):
        self.assertIsNone(PROFILE_GENERIC)
        self.assertEqual(PROFILE_LEGACY, 1)
        self.assertEqual(PROFILE_ST7789V, 2)

    def test_default_profile_is_the_upstream_sequence(self):
        commands = self.run_init(_st7789_init)
        self.assertEqual(self.data_for(commands, _VCOMS), [b"\x28"])
        self.assertEqual(self.data_for(commands, _VRHS), [b"\x13"])
        self.assertEqual(self.data_for(commands, _FRCTR2), [b"\x0f"])
        self.assertEqual(self.data_for(commands, 0x3A), [b"\x55"])
        self.assertEqual(self.data_for(commands, _INVON), [None])
        self.assertEqual(self.data_for(commands, _INVCTR), [])

    def test_legacy_profile_keeps_the_previous_default_sequence(self):
        commands = self.run_init(_st7789_init_type1)
        self.assertEqual(self.data_for(commands, _VCOMS), [b"\x3c"])
        self.assertEqual(self.data_for(commands, _VRHS), [b"\x15"])
        self.assertEqual(self.data_for(commands, _FRCTR2), [b"\x05"])
        self.assertEqual(self.data_for(commands, _INVON), [None])
        self.assertEqual(self.data_for(commands, _INVCTR), [])
        self.assertEqual(
            self.data_for(commands, 0xE0),
            [b"\xd0\x08\x0e\x09\x09\x05\x31\x33\x48\x17\x14\x15\x31\x34"],
        )

    def test_st7789v_profile_inverts_with_b4_and_matches_upstream_otherwise(self):
        commands = self.run_init(_st7789_init_type2)
        default = self.run_init(_st7789_init)
        self.assertEqual(self.data_for(commands, _INVCTR), [b"\x01"])
        self.assertEqual(self.data_for(commands, _INVON), [])
        self.assertEqual(
            self.commands_without_inversion(commands),
            self.commands_without_inversion(default),
        )

    def test_st7789_boards_select_a_named_profile(self):
        board_dir = os.path.join("lib", "mpos", "board")
        try:
            names = os.listdir(board_dir)
        except OSError:
            return  # frozen board modules: no sources to scan

        checked = 0
        for name in names:
            if not name.endswith(".py"):
                continue
            with open(os.path.join(board_dir, name)) as source_file:
                source = source_file.read()
            if "drivers.display.st7789" not in source:
                continue
            checked += 1
            self.assertTrue(
                ".init(st7789.PROFILE_" in source or ".init(PROFILE_" in source,
                "%s must select a named ST7789 init profile" % name,
            )
        self.assertTrue(checked > 0, "no ST7789 boards found to check")


if __name__ == "__main__":
    unittest.main()
