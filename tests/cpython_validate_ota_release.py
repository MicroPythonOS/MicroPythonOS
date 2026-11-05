#!/usr/bin/env python3
"""CPython tests for scripts/validate_ota_release.py — no hardware needed.

Usage:
    python3 tests/cpython_validate_ota_release.py
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from scripts import validate_ota_release as ota  # noqa: E402


class TestPartitionHelpers(unittest.TestCase):

    def test_other_partition_toggles(self):
        self.assertEqual(ota.other_partition("ota_0"), "ota_1")
        self.assertEqual(ota.other_partition("ota_1"), "ota_0")

    def test_other_partition_rejects_factory(self):
        with self.assertRaises(ota.ValidationError):
            ota.other_partition("factory")

    def test_partition_label(self):
        info = (0, 0x10, 0x20000, 0x380000, "ota_0", False)
        self.assertEqual(ota.partition_label(info), "ota_0")

    def test_partition_label_rejects_short_tuple(self):
        with self.assertRaises(ota.ValidationError):
            ota.partition_label((0, 0x10))

    def test_partition_sequence_happy_path(self):
        self.assertEqual(ota.partition_sequence_errors("ota_0", "ota_1", "ota_0"), [])

    def test_partition_sequence_detects_stuck_slot(self):
        errors = ota.partition_sequence_errors("ota_0", "ota_0", "ota_1")
        self.assertEqual(len(errors), 2)
        self.assertIn("first OTA", errors[0])
        self.assertIn("second OTA", errors[1])

    def test_partition_sequence_requires_clean_base_only_when_asked(self):
        self.assertEqual(
            ota.partition_sequence_errors("ota_1", "ota_0", "ota_1", require_clean_base=False), []
        )
        errors = ota.partition_sequence_errors("ota_1", "ota_0", "ota_1")
        self.assertEqual(len(errors), 1)
        self.assertIn("ota_0", errors[0])


class TestBuildFlashCommand(unittest.TestCase):

    def test_erases_flash_and_writes_at_offset_zero(self):
        command = ota.build_flash_command(
            ["esptool"], "esp32s3", "/dev/ttyACM0", "16MB", "base.bin", erase_all=True
        )
        self.assertEqual(command[:3], ["esptool", "--chip", "esp32s3"])
        self.assertIn("--erase-all", command)
        self.assertEqual(command[-2:], ["0", "base.bin"])
        self.assertLess(command.index("write_flash"), command.index("--erase-all"))

    def test_can_keep_otadata(self):
        command = ota.build_flash_command(
            ["esptool"], "esp32s3", None, "16MB", "base.bin"
        )
        self.assertNotIn("--erase-all", command)
        self.assertNotIn("--port", command)


class TestUpdateMetadata(unittest.TestCase):

    def _data(self, **overrides):
        data = {
            "version": "0.21.0",
            "download_url": "https://updates.micropythonos.com/releases/esp32s3/x.ota",
            "changelog": "notes",
        }
        data.update(overrides)
        return data

    def test_accepts_expected_release(self):
        url = ota.validate_update_metadata(self._data(), "0.21.0")
        self.assertTrue(url.endswith(".ota"))

    def test_rejects_wrong_version(self):
        with self.assertRaises(ota.ValidationError):
            ota.validate_update_metadata(self._data(version="0.20.0"), "0.21.0")

    def test_rejects_missing_fields(self):
        data = self._data()
        del data["changelog"]
        with self.assertRaises(ota.ValidationError) as context:
            ota.validate_update_metadata(data, "0.21.0")
        self.assertIn("changelog", str(context.exception))

    def test_rejects_non_ota_url(self):
        with self.assertRaises(ota.ValidationError):
            ota.validate_update_metadata(self._data(download_url="https://example.com/x.bin"), "0.21.0")


class TestOutputParsing(unittest.TestCase):

    def test_parse_marker_uses_last_match(self):
        output = b"MPOSVER=0.20.0\r\nnoise\r\nMPOSVER=0.21.0\r\n"
        self.assertEqual(ota.parse_marker(output, "MPOSVER="), "0.21.0")

    def test_parse_marker_missing(self):
        self.assertIsNone(ota.parse_marker("nothing", "MPOSVER="))

    def test_find_release_text(self):
        texts = ["About", "Release version: 0.21.0", "API Level: 0"]
        self.assertEqual(ota.find_release_text(texts), "0.21.0")

    def test_find_partition_text_from_about(self):
        texts = [
            "Partition.RUNNING: <Partition type=0, subtype=16, address=131072, "
            "size=3670016, label=ota_1, encrypted=0>",
        ]
        self.assertEqual(ota.find_partition_text(texts), "ota_1")

    def test_find_partition_text_missing(self):
        self.assertIsNone(ota.find_partition_text(["Release version: 0.21.0"]))


class TestParser(unittest.TestCase):

    def test_second_pass_is_enabled_by_default(self):
        args = ota.build_parser().parse_args(["--wifi-ssid", "x", "--wifi-password", "y"])
        self.assertTrue(args.second_pass)

    def test_second_pass_can_be_disabled(self):
        args = ota.build_parser().parse_args(
            ["--wifi-ssid", "x", "--wifi-password", "y", "--no-second-pass"]
        )
        self.assertFalse(args.second_pass)


class TestCameraVerifier(unittest.TestCase):

    def test_bind_replaces_the_controller_after_a_reboot(self):
        with tempfile.TemporaryDirectory() as tmp:
            verifier = ota.CameraVerifier(object(), tmp, enabled=False)
            replacement = object()
            self.assertIs(verifier.bind(replacement).controller, replacement)


class TestReport(unittest.TestCase):

    def test_writes_incremental_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = ota.Report(tmp)
            self.assertTrue(report.check("first", True, "ok"))
            report.check("second", False, "boom")
            with open(os.path.join(tmp, "report.json")) as handle:
                data = json.load(handle)
            self.assertFalse(data["ok"])
            self.assertEqual([entry["name"] for entry in data["checks"]], ["first", "second"])

    def test_require_raises_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = ota.Report(tmp)
            with self.assertRaises(ota.ValidationError):
                report.require("bad", False, "no")
            self.assertFalse(report.data["ok"])


if __name__ == "__main__":
    unittest.main()
