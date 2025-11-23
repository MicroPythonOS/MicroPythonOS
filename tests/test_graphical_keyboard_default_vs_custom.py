"""
Test comparing default LVGL keyboard with custom MposKeyboard.

This test helps identify the differences between the two keyboard types
so we can properly detect when the bug occurs (switching to default instead of custom).

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_keyboard_default_vs_custom.py
"""

import unittest
import lvgl as lv
from mpos.ui.keyboard import MposKeyboard
from mpos.ui.testing import wait_for_render


class TestDefaultVsCustomKeyboard(unittest.TestCase):
    """Compare default LVGL keyboard with custom MposKeyboard."""

    def setUp(self):
        """Set up test fixtures."""
        self.screen = lv.obj()
        self.screen.set_size(320, 240)
        lv.screen_load(self.screen)
        wait_for_render(5)

    def tearDown(self):
        """Clean up."""
        lv.screen_load(lv.obj())
        wait_for_render(5)

    def test_default_lvgl_keyboard_layout(self):
        """
        Examine the default LVGL keyboard to understand its layout.

        This helps us know what we're looking for when detecting the bug.
        """
        print("\n=== Examining DEFAULT LVGL keyboard ===")

        # Create textarea
        textarea = lv.textarea(self.screen)
        textarea.set_size(280, 40)
        textarea.align(lv.ALIGN.TOP_MID, 0, 10)
        textarea.set_one_line(True)
        wait_for_render(5)

        # Create DEFAULT LVGL keyboard
        keyboard = lv.keyboard(self.screen)
        keyboard.set_textarea(textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        wait_for_render(10)

        print("\nDefault LVGL keyboard buttons (first 40):")
        found_special_labels = {}
        for i in range(40):
            try:
                text = keyboard.get_button_text(i)
                if text and text not in ["\n", ""]:
                    print(f"  Index {i}: '{text}'")
                    # Track special labels
                    if text in ["Abc", "Abc", "1#", "?123", "#+=", lv.SYMBOL.UP, lv.SYMBOL.DOWN]:
                        found_special_labels[text] = i
            except:
                pass

        print("\n--- DEFAULT LVGL keyboard has these special labels ---")
        for label, idx in found_special_labels.items():
            print(f"  '{label}' at index {idx}")

        print("\n--- Characteristics of DEFAULT LVGL keyboard ---")
        if "Abc" in found_special_labels:
            print("  ✓ Has 'Abc' (uppercase label)")
        if "1#" in found_special_labels:
            print("  ✓ Has '1#' (numbers label)")
        if "#+" in found_special_labels or "#+=" in found_special_labels:
            print("  ✓ Has '#+=/-' type labels")

    def test_custom_mpos_keyboard_layout(self):
        """
        Examine our custom MposKeyboard to understand its layout.

        This shows what the CORRECT layout should look like.
        """
        print("\n=== Examining CUSTOM MposKeyboard ===")

        # Create textarea
        textarea = lv.textarea(self.screen)
        textarea.set_size(280, 40)
        textarea.align(lv.ALIGN.TOP_MID, 0, 10)
        textarea.set_one_line(True)
        wait_for_render(5)

        # Create CUSTOM MposKeyboard
        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        wait_for_render(10)

        print("\nCustom MposKeyboard buttons (first 40):")
        found_special_labels = {}
        for i in range(40):
            try:
                text = keyboard.get_button_text(i)
                if text and text not in ["\n", ""]:
                    print(f"  Index {i}: '{text}'")
                    # Track special labels
                    if text in ["Abc", "Abc", "1#", "?123", "=\\<", lv.SYMBOL.UP, lv.SYMBOL.DOWN]:
                        found_special_labels[text] = i
            except:
                pass

        print("\n--- CUSTOM MposKeyboard has these special labels ---")
        for label, idx in found_special_labels.items():
            print(f"  '{label}' at index {idx}")

        print("\n--- Characteristics of CUSTOM MposKeyboard ---")
        if "?123" in found_special_labels:
            print("  ✓ Has '?123' (numbers label)")
        if "=\\<" in found_special_labels:
            print("  ✓ Has '=\\<' (specials label)")
        if lv.SYMBOL.UP in found_special_labels:
            print("  ✓ Has UP symbol (shift to uppercase)")

    def test_mode_switching_bug_reproduction(self):
        """
        Try to reproduce the bug: numbers -> Abc -> wrong layout.
        """
        print("\n=== Attempting to reproduce the bug ===")

        textarea = lv.textarea(self.screen)
        textarea.set_size(280, 40)
        textarea.align(lv.ALIGN.TOP_MID, 0, 10)
        textarea.set_one_line(True)
        wait_for_render(5)

        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        wait_for_render(10)

        # Step 1: Start in lowercase
        print("\nStep 1: Initial lowercase mode")
        labels_step1 = self._get_special_labels(keyboard)
        print(f"  Labels: {list(labels_step1.keys())}")
        self.assertIn("?123", labels_step1, "Should start with custom lowercase (?123)")

        # Step 2: Switch to numbers
        print("\nStep 2: Switch to numbers mode")
        keyboard.set_mode(MposKeyboard.MODE_NUMBERS)
        wait_for_render(5)
        labels_step2 = self._get_special_labels(keyboard)
        print(f"  Labels: {list(labels_step2.keys())}")
        self.assertIn("Abc", labels_step2, "Should have 'Abc' in numbers mode")

        # Step 3: Switch back to lowercase (this is where bug might happen)
        print("\nStep 3: Switch back to lowercase via set_mode()")
        keyboard.set_mode(MposKeyboard.MODE_LOWERCASE)
        wait_for_render(5)
        labels_step3 = self._get_special_labels(keyboard)
        print(f"  Labels: {list(labels_step3.keys())}")

        # Check for bug
        if "Abc" in labels_step3 or "1#" in labels_step3:
            print("  ❌ BUG DETECTED: Got default LVGL keyboard!")
            print(f"     Found these labels: {list(labels_step3.keys())}")
            self.fail("BUG: Switched to default LVGL keyboard instead of custom")

        if "?123" not in labels_step3:
            print("  ❌ BUG DETECTED: Missing '?123' label!")
            print(f"     Found these labels: {list(labels_step3.keys())}")
            self.fail("BUG: Missing '?123' label from custom keyboard")

        print("  ✓ Correct: Has custom layout with '?123'")

    def _get_special_labels(self, keyboard):
        """Helper to get special labels from keyboard."""
        labels = {}
        for i in range(100):
            try:
                text = keyboard.get_button_text(i)
                if text in ["Abc", "Abc", "1#", "?123", "=\\<", "#+=", lv.SYMBOL.UP, lv.SYMBOL.DOWN]:
                    labels[text] = i
            except:
                pass
        return labels


