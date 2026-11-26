"""
Graphical test for InputActivity's optional `scan_check`.

A text setting may carry `scan_check(text)`. After data is scanned from a QR
code into the field, InputActivity runs the check and shows a warning below
the field when the data doesn't have the expected format, so a user who
scanned the wrong QR code notices before saving. The scanned text is still
filled in: the warning never blocks Save.
"""

import unittest

import lvgl as lv

import mpos.ui
from mpos import InputActivity, Intent, wait_for_render
from mpos.activity_navigator import ActivityNavigator
from mpos.ui.input_activity import SCAN_WARNING_DEFAULT, scan_check_warning
from mpos.ui.testing import verify_text_present


def _looks_like_hex32(text):
    return len(text) == 32 and all(c in "0123456789abcdef" for c in text)


GOOD_KEY = "fd92e3f8168ba314dc22e54182784045"


class TestScanCheckWarning(unittest.TestCase):
    """The verdict-to-warning mapping, without any widgets."""

    def test_no_check_means_no_warning(self):
        self.assertIsNone(scan_check_warning({"title": "Key"}, "anything"))
        self.assertIsNone(scan_check_warning(None, "anything"))

    def test_true_or_none_means_no_warning(self):
        self.assertIsNone(scan_check_warning({"scan_check": lambda t: True}, "x"))
        self.assertIsNone(scan_check_warning({"scan_check": lambda t: None}, "x"))

    def test_false_gives_default_warning_with_title(self):
        setting = {"title": "Read Key", "scan_check": lambda t: False}
        self.assertEqual(scan_check_warning(setting, "x"), SCAN_WARNING_DEFAULT % "Read Key")

    def test_string_is_shown_as_the_warning(self):
        setting = {"title": "Read Key", "scan_check": lambda t: "That is a URL."}
        self.assertEqual(scan_check_warning(setting, "x"), "That is a URL.")

    def test_empty_string_means_no_warning(self):
        self.assertIsNone(scan_check_warning({"scan_check": lambda t: ""}, "x"))

    def test_check_receives_the_scanned_text(self):
        seen = []
        scan_check_warning({"scan_check": lambda t: seen.append(t)}, "scanned")
        self.assertEqual(seen, ["scanned"])

    def test_raising_check_gives_no_warning(self):
        def broken(text):
            raise ValueError("boom")
        self.assertIsNone(scan_check_warning({"title": "Key", "scan_check": broken}, "x"))


class TestInputActivityScanWarning(unittest.TestCase):
    """The warning label on a real InputActivity screen."""

    def setUp(self):
        self._to_launcher()

    def tearDown(self):
        self._to_launcher()

    def _to_launcher(self):
        for _ in range(10):
            if len(mpos.ui.screen_stack) <= 1:
                break
            mpos.ui.back_screen()
            wait_for_render(5)

    def _open(self, setting):
        intent = Intent(activity_class=InputActivity)
        intent.putExtra("setting", setting)
        ActivityNavigator.startActivity(intent)
        wait_for_render(10)
        activity = mpos.ui.screen_stack[-1][0]
        self.assertIsInstance(activity, InputActivity)
        return activity

    def _scan(self, activity, data):
        activity.gotqr_result_callback({"result_code": True, "data": data})
        wait_for_render(5)

    def _warning_visible(self, activity):
        label = activity._scan_warning_label
        return label is not None and not label.has_flag(lv.obj.FLAG.HIDDEN)

    def _key_setting(self):
        return {"title": "Read Key", "key": "readkey", "scan_check": _looks_like_hex32}

    def test_wrong_format_shows_warning_and_keeps_text(self):
        activity = self._open(self._key_setting())
        self.assertFalse(self._warning_visible(activity), "No warning before a scan")
        self._scan(activity, "https://example.com/not-a-key")
        self.assertTrue(self._warning_visible(activity))
        self.assertTrue(verify_text_present(lv.screen_active(), "Check that you scanned the right QR code"))
        self.assertEqual(activity.textarea.get_text(), "https://example.com/not-a-key")

    def test_expected_format_shows_no_warning(self):
        activity = self._open(self._key_setting())
        self._scan(activity, GOOD_KEY)
        self.assertFalse(self._warning_visible(activity))
        self.assertEqual(activity.textarea.get_text(), GOOD_KEY)

    def test_good_rescan_clears_warning(self):
        activity = self._open(self._key_setting())
        self._scan(activity, "wrong")
        self.assertTrue(self._warning_visible(activity))
        self._scan(activity, GOOD_KEY)
        self.assertFalse(self._warning_visible(activity))

    def test_editing_scanned_text_clears_warning(self):
        activity = self._open(self._key_setting())
        self._scan(activity, "wrong")
        self.assertTrue(self._warning_visible(activity))
        activity.textarea.add_text("x")
        wait_for_render(5)
        self.assertFalse(self._warning_visible(activity))

    def test_keyboard_stays_in_place_when_warning_clears(self):
        activity = self._open(self._key_setting())
        self._scan(activity, "wrong")
        self.assertTrue(self._warning_visible(activity))
        activity.keyboard.remove_flag(lv.obj.FLAG.HIDDEN)
        wait_for_render(5)
        keyboard_y = activity.keyboard.get_y()
        activity.textarea.add_text("x")
        wait_for_render(5)
        self.assertFalse(self._warning_visible(activity))
        self.assertEqual(activity.keyboard.get_y(), keyboard_y,
                         "The keyboard must not move under the finger when the warning clears")

    def test_save_with_warning_visible_returns_the_scanned_text(self):
        results = []
        intent = Intent(activity_class=InputActivity)
        intent.putExtra("setting", self._key_setting())
        ActivityNavigator.startActivityForResult(intent, results.append)
        wait_for_render(10)
        activity = mpos.ui.screen_stack[-1][0]
        self.assertIsInstance(activity, InputActivity)
        self._scan(activity, "https://example.com/not-a-key")
        self.assertTrue(self._warning_visible(activity))
        activity.save_input()
        wait_for_render(10)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["result_code"])
        self.assertEqual(results[0]["data"]["value"], "https://example.com/not-a-key")

    def test_cancelled_scan_changes_nothing(self):
        activity = self._open(self._key_setting())
        activity.gotqr_result_callback({"result_code": False, "data": None})
        wait_for_render(5)
        self.assertFalse(self._warning_visible(activity))
        self.assertEqual(activity.textarea.get_text(), "")

    def test_custom_message_is_shown(self):
        setting = {"title": "Read Key", "key": "readkey",
                   "scan_check": lambda t: "This looks like a web address."}
        activity = self._open(setting)
        self._scan(activity, "https://example.com")
        self.assertTrue(verify_text_present(lv.screen_active(), "This looks like a web address."))

    def test_setting_without_check_has_no_warning_label(self):
        activity = self._open({"title": "Name", "key": "name"})
        self.assertIsNone(activity._scan_warning_label)
        self._scan(activity, "anything")
        self.assertEqual(activity.textarea.get_text(), "anything")


if __name__ == "__main__":
    unittest.main()
