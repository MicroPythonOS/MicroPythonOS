"""
Test for rapid mode switching bug (clicking ?123/abc rapidly).

This test reproduces:
1. Comma being added when clicking "abc" button
2. Intermittent crashes when rapidly clicking mode switch buttons

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_keyboard_rapid_mode_switch.py
"""

import unittest
import lvgl as lv
from mpos import MposKeyboard, wait_for_render


class TestRapidModeSwitching(unittest.TestCase):
    """Test rapid mode switching between lowercase and numbers."""

    def setUp(self):
        """Set up test fixtures."""
        self.screen = lv.obj()
        self.screen.set_size(320, 240)

        # Create textarea
        self.textarea = lv.textarea(self.screen)
        self.textarea.set_size(280, 40)
        self.textarea.align(lv.ALIGN.TOP_MID, 0, 10)
        self.textarea.set_one_line(True)

        # Load screen
        lv.screen_load(self.screen)
        wait_for_render(5)

    def tearDown(self):
        """Clean up."""
        lv.screen_load(lv.obj())
        wait_for_render(5)

    def test_rapid_clicking_abc_button(self):
        """
        Rapidly click the "Abc" button to reproduce the comma bug and crash.

        Expected: Clicking "Abc" should NOT add comma to textarea
        Bug: Comma is being added, suggesting button index confusion
        """
        print("\n=== Testing rapid clicking of Abc button ===")

        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(self.textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        wait_for_render(10)

        # Start in lowercase, switch to numbers
        print("Step 1: Switch to numbers mode")
        keyboard.set_mode(MposKeyboard.MODE_NUMBERS)
        wait_for_render(10)  # Give time to settle

        # Clear textarea
        self.textarea.set_text("")

        # Now find the "abc" button
        abc_button_index = None
        for i in range(100):
            try:
                text = keyboard.get_button_text(i)
                if text == "Abc":
                    abc_button_index = i
                    print(f"  Found 'Abc' button at index {i}")
                    break
            except:
                pass

        self.assertIsNotNone(abc_button_index, "Should find 'Abc' button in numbers mode")

        # Simulate rapid clicking by alternating modes
        print("\nStep 2: Rapidly switch modes by simulating Abc/?123 clicks")
        for i in range(10):
            # Get current mode
            current_mode = keyboard._keyboard.get_mode()

            # Clear text before click
            textarea_before = self.textarea.get_text()
            print(f"  Click {i+1}: mode={current_mode}, textarea='{textarea_before}'")

            if current_mode == MposKeyboard.MODE_NUMBERS or current_mode == lv.keyboard.MODE.NUMBER:
                # Click "Abc" to go to lowercase
                keyboard.set_mode(MposKeyboard.MODE_LOWERCASE)
            else:
                # Click "?123" to go to numbers
                keyboard.set_mode(MposKeyboard.MODE_NUMBERS)

            wait_for_render(2)

            # Check if text changed (BUG: should not change!)
            textarea_after = self.textarea.get_text()
            if textarea_after != textarea_before:
                print(f"    ERROR: Text changed from '{textarea_before}' to '{textarea_after}'")
                self.fail(f"BUG: Clicking mode switch button added '{textarea_after}' to textarea")

        # Verify textarea is still empty
        final_text = self.textarea.get_text()
        print(f"\nFinal textarea text: '{final_text}'")
        self.assertEqual(final_text, "",
                        f"Textarea should be empty after mode switches, but contains: '{final_text}'")

        print("SUCCESS: No spurious characters added during rapid mode switching")

    def test_button_indices_after_mode_switch(self):
        """
        Test that button indices remain consistent after mode switches.

        This helps identify if the comma bug is due to button index confusion.
        """
        print("\n=== Testing button indices after mode switch ===")

        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(self.textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        wait_for_render(10)

        # Map button indices in lowercase mode
        print("\nButton indices in LOWERCASE mode:")
        keyboard.set_mode(MposKeyboard.MODE_LOWERCASE)
        wait_for_render(10)

        lowercase_buttons = {}
        for i in range(40):
            try:
                text = keyboard.get_button_text(i)
                if text in ["?123", ",", "Abc", lv.SYMBOL.UP]:
                    lowercase_buttons[text] = i
                    print(f"  '{text}' at index {i}")
            except:
                pass

        # Map button indices in numbers mode
        print("\nButton indices in NUMBERS mode:")
        keyboard.set_mode(MposKeyboard.MODE_NUMBERS)
        wait_for_render(10)

        numbers_buttons = {}
        for i in range(40):
            try:
                text = keyboard.get_button_text(i)
                if text in ["?123", ",", "Abc", "=\\<"]:
                    numbers_buttons[text] = i
                    print(f"  '{text}' at index {i}")
            except:
                pass

