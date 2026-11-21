import sys
import unittest

from mpos.platform import natmod_arch, native_keys, soc

# py/persistentcode.h: MP_NATIVE_ARCH_X64 = 2, MP_NATIVE_ARCH_XTENSAWIN = 10.
NATMOD_NAMES = {
    1: "x86",
    2: "x64",
    9: "xtensa",
    10: "xtensawin",
    11: "rv32imc",
    12: "rv64imc",
}


class TestPlatformKeys(unittest.TestCase):
    def test_desktop_has_no_soc(self):
        if sys.platform == "esp32":
            self.assertIn(soc(), ("esp32", "esp32s2", "esp32s3", "esp32c3",
                                  "esp32c6", "esp32p4"))
        else:
            self.assertIsNone(soc())

    def test_natmod_arch_comes_from_the_mpy_header(self):
        mpy = getattr(sys.implementation, "_mpy", None)
        if mpy is None:
            self.assertIsNone(natmod_arch())
            return
        expected = NATMOD_NAMES.get((mpy >> 10) & 0x2F)
        self.assertEqual(natmod_arch(), expected)

    def test_desktop_is_x64(self):
        if sys.platform == "esp32":
            return
        if natmod_arch() is None:
            # MicroPython's natmod table has no aarch64 entry, so the Linux
            # arm64 runner reports None (and no Doom module is shipped there).
            raise unittest.SkipTest("this desktop has no natmod architecture")
        self.assertEqual(natmod_arch(), "x64")

    def test_native_keys_lists_both_namespaces(self):
        keys = native_keys()
        chip = soc()
        arch = natmod_arch()
        if chip is not None:
            self.assertIn(chip, keys)
        if arch is not None:
            self.assertIn(arch, keys)
        self.assertEqual(len(keys), len(set(keys)))


if __name__ == "__main__":
    unittest.main()
