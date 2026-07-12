"""
Unit tests for the `_value_label_for` helper in `mpos.ui.settings_activity`.

The helper maps a stored pref value to its human-readable display label
using the setting's `ui_options` list. This is what lets the row in a
SettingsActivity list show "Lightning Piggy" / "Bright" / "Dark" instead
of the raw pref value "lightningpiggy" / "light" / "dark".

Motivating case: Lightning Piggy's Customise screen with a Hero Image
row using `ui: "radiobuttons"` — the value_label was rendering
"lightningpiggy" before this helper was added.

Usage:
    Desktop: ./tests/unittest.sh tests/test_settings_activity_label_mapping.py
    Device:  ./tests/unittest.sh tests/test_settings_activity_label_mapping.py --ondevice
"""

import unittest

from mpos.ui.settings_activity import _value_label_for


class TestValueLabelFor(unittest.TestCase):

    def test_matched_value_returns_label(self):
        setting = {
            "ui_options": [
                ("Lightning Piggy", "lightningpiggy"),
                ("Lightning Penguin", "lightningpenguin"),
                ("None", "none"),
            ],
        }
        self.assertEqual(_value_label_for(setting, "lightningpiggy"), "Lightning Piggy")
        self.assertEqual(_value_label_for(setting, "lightningpenguin"), "Lightning Penguin")
        self.assertEqual(_value_label_for(setting, "none"), "None")

    def test_unmatched_value_passes_through(self):
        # A stored value that's not in ui_options (e.g. a stale value from
        # before the option set changed) returns unchanged rather than
        # disappearing into "(not set)". Lets users still see what's
        # actually stored, even if it's not a current valid option.
        setting = {
            "ui_options": [("A", "a"), ("B", "b")],
        }
        self.assertEqual(_value_label_for(setting, "legacy_value"), "legacy_value")

    def test_setting_without_ui_options_passes_through(self):
        # Plain textarea / freeform settings have no ui_options — the raw
        # value is the right thing to display.
        setting = {}
        self.assertEqual(_value_label_for(setting, "some_value"), "some_value")
        # None ui_options should also pass through, not raise.
        self.assertEqual(_value_label_for({"ui_options": None}, "v"), "v")

    def test_empty_ui_options_passes_through(self):
        # Edge case: ui_options = [] (degenerate). Same fall-through as None.
        self.assertEqual(_value_label_for({"ui_options": []}, "v"), "v")

    def test_none_stored_value_passes_through(self):
        # The caller (SettingsActivity row-render code) handles the "None"
        # case separately with "(not set)" — this helper should never be
        # asked about None, but be defensive: don't crash.
        setting = {"ui_options": [("Yes", True), ("No", False)]}
        # None doesn't match any option → return None unchanged.
        self.assertIsNone(_value_label_for(setting, None))

    def test_first_match_wins_with_duplicate_values(self):
        # Duplicate values in ui_options (config bug) — first match wins.
        # Documents the precedence so callers know what to expect.
        setting = {
            "ui_options": [("First", "x"), ("Second", "x")],
        }
        self.assertEqual(_value_label_for(setting, "x"), "First")


class TestShouldShow(unittest.TestCase):

    def _should_show(self, setting):
        should_show = setting.get("should_show")
        if should_show is not None:
            if callable(should_show):
                should_show = should_show(setting)
            if not should_show:
                return False
        return True

    def test_callable_returns_true(self):
        self.assertTrue(self._should_show({"should_show": lambda s: True}))

    def test_callable_returns_false(self):
        self.assertFalse(self._should_show({"should_show": lambda s: False}))

    def test_callable_returns_truthy_object(self):
        self.assertTrue(self._should_show({"should_show": lambda s: "buzzer"}))

    def test_callable_returns_none(self):
        self.assertFalse(self._should_show({"should_show": lambda s: None}))

    def test_no_should_show_key_shows(self):
        self.assertTrue(self._should_show({}))

    def test_should_show_true_shows(self):
        self.assertTrue(self._should_show({"should_show": True}))

    def test_should_show_false_hides(self):
        self.assertFalse(self._should_show({"should_show": False}))

    def test_should_show_truthy_object_shows(self):
        self.assertTrue(self._should_show({"should_show": "some_output"}))

    def test_callable_receives_setting_dict(self):
        captured = []
        self._should_show({"should_show": lambda s: captured.append(s) or True, "key": "mykey"})
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["key"], "mykey")


if __name__ == "__main__":
    unittest.main()
