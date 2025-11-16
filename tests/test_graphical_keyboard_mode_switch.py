"""
Test for MposKeyboard mode switching crash.

This test reproduces the crash that occurs when clicking the UP arrow
to switch to uppercase mode in MposKeyboard.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_keyboard_mode_switch.py
    Device:  ./tests/unittest.sh tests/test_graphical_keyboard_mode_switch.py --ondevice
"""

import unittest
import lvgl as lv
from mpos.ui.keyboard import MposKeyboard
from graphical_test_helper import wait_for_render


class TestKeyboardModeSwitch(unittest.TestCase):
    """Test keyboard mode switching doesn't crash."""

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

    def test_switch_to_uppercase_with_symbol_up(self):
        """
        Test switching to uppercase mode.

        This reproduces the crash that occurred when clicking the UP arrow button.
        The bug was that set_mode() was called without set_map() first.
        """
        print("\n=== Testing uppercase mode switch ===")

        # Create keyboard
        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(self.textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        wait_for_render(10)

        # Keyboard starts in lowercase mode
        print("Initial mode: MODE_LOWERCASE")

        # Find the UP symbol button by searching all buttons
        up_button_index = None
        for i in range(100):  # Try up to 100 buttons
            try:
                text = keyboard.get_button_text(i)
                if text == lv.SYMBOL.UP:
                    up_button_index = i
                    print(f"Found UP symbol at button index {i}")
                    break
            except:
                pass

        self.assertIsNotNone(up_button_index, "Should find UP symbol button")

        # Test mode switching (this is what happens when the user clicks UP)
        print("Switching to uppercase mode...")
        try:
            keyboard.set_mode(MposKeyboard.MODE_UPPERCASE)
            wait_for_render(5)
            print("SUCCESS: No crash when switching to uppercase!")

            # Verify we're now in uppercase mode by checking the button changed
            down_button_text = keyboard.get_button_text(up_button_index)
            print(f"After switch, button {up_button_index} text: {down_button_text}")
            self.assertEqual(down_button_text, lv.SYMBOL.DOWN,
                           "Should show DOWN symbol in uppercase mode")

            # Switch back to lowercase
            keyboard.set_mode(MposKeyboard.MODE_LOWERCASE)
            wait_for_render(5)
            up_button_text = keyboard.get_button_text(up_button_index)
            self.assertEqual(up_button_text, lv.SYMBOL.UP,
                           "Should show UP symbol in lowercase mode")

        except Exception as e:
            self.fail(f"CRASH: Switching to uppercase caused exception: {e}")

    def test_switch_modes_multiple_times(self):
        """
        Test switching between all keyboard modes multiple times.

        Tests the full mode switching cycle to ensure all modes work.
        """
        print("\n=== Testing multiple mode switches ===")

        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(self.textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        wait_for_render(10)

        modes_to_test = [
            (MposKeyboard.MODE_UPPERCASE, "MODE_UPPERCASE"),
            (MposKeyboard.MODE_LOWERCASE, "MODE_LOWERCASE"),
            (MposKeyboard.MODE_NUMBERS, "MODE_NUMBERS"),
            (MposKeyboard.MODE_SPECIALS, "MODE_SPECIALS"),
            (MposKeyboard.MODE_LOWERCASE, "MODE_LOWERCASE (again)"),
        ]

        for mode, mode_name in modes_to_test:
            print(f"Switching to {mode_name}...")
            try:
                keyboard.set_mode(mode)
                wait_for_render(5)
                print(f"  SUCCESS: Switched to {mode_name}")
            except Exception as e:
                self.fail(f"  CRASH: Switching to {mode_name} caused exception: {e}")


if __name__ == "__main__":
    unittest.main()
