import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "internal_filesystem/lib/mpos/board/d_shell_detect.py"


class DetectionTests(unittest.TestCase):
    def detect(self, devices):
        probes = []
        released = []

        class Pin:
            IN = 0

            def __init__(self, number, *args, **kwargs):
                self.number = number
                if args:
                    released.append(number)

        class Bus:
            def __init__(self, scl, sda, **kwargs):
                self.pins = (scl.number, sda.number)

            def readfrom_mem(self, address, register, count, **kwargs):
                key = (self.pins, address, register)
                probes.append(key)
                if key not in devices:
                    raise OSError("not present")
                return devices[key][:count]

        machine = types.SimpleNamespace(Pin=Pin, SoftI2C=Bus)
        with patch.dict(sys.modules, {"machine": machine}):
            spec = importlib.util.spec_from_file_location("d_shell_detect", MODULE)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            result = module.detect()
        return result, probes, released

    def test_factory_touch_address(self):
        found, _, released = self.detect({
            ((41, 42), 0x5D, 0x8140): b"911\x00",
            ((7, 6), 0x6A, 0): b"\x05",
        })
        self.assertTrue(found)
        self.assertEqual(set(released), {41, 42, 7, 6})

    def test_touch_address_after_driver_reset(self):
        found, _, _ = self.detect({
            ((41, 42), 0x14, 0x8140): b"911\x00",
            ((7, 6), 0x6A, 0): b"\x05",
        })
        self.assertTrue(found)

    def test_another_gt911_board_is_not_d_shell(self):
        found, _, _ = self.detect({((41, 42), 0x5D, 0x8140): b"911\x00"})
        self.assertFalse(found)

    def test_wrong_sensor_identity_is_rejected(self):
        found, _, _ = self.detect({
            ((41, 42), 0x5D, 0x8140): b"911\x00",
            ((7, 6), 0x6A, 0): b"\x00",
        })
        self.assertFalse(found)

    def test_missing_touch_does_not_probe_imu(self):
        found, probes, released = self.detect({})
        self.assertFalse(found)
        self.assertTrue(all(p[0] == (41, 42) for p in probes))
        self.assertEqual(set(released), {41, 42})


if __name__ == "__main__":
    unittest.main()
