import ast
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "internal_filesystem/lib/drivers/display/st7789v"


class ST7789VPRTests(unittest.TestCase):
    def load(self, filename):
        framework = types.SimpleNamespace(DisplayDriver=object, STATE_HIGH=1, STATE_LOW=0,
                                          STATE_PWM=2, BYTE_ORDER_RGB=0, BYTE_ORDER_BGR=8)
        modules = {"micropython": types.SimpleNamespace(const=lambda value: value),
                   "time": types.SimpleNamespace(sleep_ms=lambda value: None),
                   "lcd_bus": types.SimpleNamespace(I80Bus=type("I80Bus", (), {})),
                   "display_driver_framework": framework,
                   "lvgl": types.SimpleNamespace(COLOR_FORMAT=types.SimpleNamespace(RGB565=18, RGB888=15),
                                                 color_format_get_size=lambda value: 2)}
        with patch.dict(sys.modules, modules):
            spec = importlib.util.spec_from_file_location("screen_pr_test", DRIVER / filename)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        return module

    def test_board_selects_pr_driver(self):
        source = (ROOT / "internal_filesystem/lib/mpos/board/d_shell.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = [n.name for node in tree.body if isinstance(node, ast.Import) for n in node.names]
        self.assertIn("drivers.display.st7789v", imports)
        self.assertIn("st7789.ST7789V(", source)
        self.assertIn("rgb565_byte_swap=True", source)

    def test_init_uses_b4_without_negative_color_command(self):
        commands = []
        display = types.SimpleNamespace(
            set_params=lambda command, data=None: commands.append((command, bytes(data) if data is not None else None)),
            _madctl=lambda *args: 8, _color_byte_order=8, _ORIENTATION_TABLE=(0, 96, 192, 160),
            _rgb565_byte_swap=True, _data_bus=object(), _color_space=18,
            display_width=240, display_height=320)
        self.load("_st7789v_init.py").init(display)
        self.assertIn((0xB4, b"\x01"), commands)
        self.assertNotIn(0x21, [command for command, _ in commands])
        self.assertIn((0x3A, b"\x55"), commands)

    def test_inversion_control_reuses_parameter_buffer(self):
        commands = []
        buffer = bytearray(4)
        display = types.SimpleNamespace(_param_buf=buffer, _param_mv=memoryview(buffer),
                                        _INVON=1, _INVOFF=0,
                                        set_params=lambda command, data: commands.append((command, bytes(data))))
        driver = self.load("st7789v.py").ST7789V
        driver.set_color_inversion(display, True)
        driver.set_color_inversion(display, False)
        self.assertEqual(commands, [(0xB4, b"\x01"), (0xB4, b"\x00")])


if __name__ == "__main__":
    unittest.main()
