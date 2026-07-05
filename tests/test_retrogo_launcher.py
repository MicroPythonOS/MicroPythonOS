import sys
import unittest

sys.path.insert(0, "apps/com.micropythonos.doom_launcher")

from mpos.content.streaming_unzip import get_zip_crc32
from retrogo_launcher import RetroGoLauncher, compute_file_crc32

FIXTURES = "../tests/retrogo_launcher"


class TestGetZipCrc32(unittest.TestCase):
    def test_returns_correct_crc32(self):
        crc = get_zip_crc32(f"{FIXTURES}/roms/gbc/Columns_DX.zip")
        self.assertEqual(crc, 0xDB08F45E)

    def test_returns_none_for_nonexistent(self):
        crc = get_zip_crc32(f"{FIXTURES}/roms/gbc/nonexistent.zip")
        self.assertIsNone(crc)


class TestComputeFileCrc32(unittest.TestCase):
    def test_returns_correct_crc32(self):
        crc = compute_file_crc32(f"{FIXTURES}/roms/gbc/Street_Racer.gbc")
        self.assertEqual(crc & 0xFFFFFFFF, 0x9AAAC765)

    def test_returns_none_for_nonexistent(self):
        crc = compute_file_crc32(f"{FIXTURES}/roms/gbc/nonexistent.gbc")
        self.assertIsNone(crc)


class _TestLauncher(RetroGoLauncher):
    def __init__(self):
        pass


class TestFindRomart(unittest.TestCase):
    def setUp(self):
        self.launcher = _TestLauncher()
        self.launcher.romartbase = FIXTURES + "/romart"
        self.launcher.roms_subdir = "gbc"
        self.launcher.bootfile_prefix = FIXTURES
        self.launcher.romdir = "/roms"

    def test_name_match_from_zip(self):
        path = self.launcher._find_romart(
            f"{FIXTURES}/roms/gbc/Columns_DX.zip", "Columns_DX.zip"
        )
        self.assertEqual(path, f"{FIXTURES}/romart/gbc/Columns_DX.png")

    def test_crc32_fallback_from_zip_no_name_match(self):
        path = self.launcher._find_romart(
            f"{FIXTURES}/roms/gbc/NoArtMatch.zip", "NoArtMatch.zip"
        )
        self.assertEqual(path, f"{FIXTURES}/romart/gbc/9/90E9E751.png")

    def test_crc32_fallback_from_raw_file(self):
        path = self.launcher._find_romart(
            f"{FIXTURES}/roms/gbc/Street_Racer.gbc", "Street_Racer.gbc"
        )
        self.assertEqual(path, f"{FIXTURES}/romart/gbc/9/9AAAC765.png")

    def test_returns_none_when_no_match(self):
        path = self.launcher._find_romart(
            f"{FIXTURES}/roms/gbc/NoArt.gbc", "NoArt.gbc"
        )
        self.assertIsNone(path)

    def test_romart_for_console(self):
        path = self.launcher._romart_for_console("gb")
        self.assertEqual(path, f"{FIXTURES}/romart/gb.png")

    def test_romart_for_dir(self):
        path = self.launcher._romart_for_dir("homebrew")
        self.assertEqual(path, f"{FIXTURES}/romart/gbc/homebrew.png")

    def test_romart_for_console_nonexistent(self):
        path = self.launcher._romart_for_console("nonexistent")
        self.assertIsNone(path)

    def test_romart_for_dir_nonexistent(self):
        path = self.launcher._romart_for_dir("nonexistent")
        self.assertIsNone(path)
