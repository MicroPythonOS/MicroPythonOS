"""
Test to reproduce the lv_strcmp crash during keyboard mode switching.

The crash happens in buttonmatrix drawing code when map_p[txt_i] is NULL.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_keyboard_crash_reproduction.py
"""

import unittest
import lvgl as lv
from mpos import MposKeyboard, wait_for_render


class TestKeyboardCrash(unittest.TestCase):
    """Test to reproduce keyboard crashes."""

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

    def test_rapid_mode_switching(self):
        """
        Rapidly switch between modes to trigger the crash.

        The crash occurs when btnm->map_p[txt_i] is NULL during drawing.
        """
        print("\n=== Testing rapid mode switching ===")

        textarea = lv.textarea(self.screen)
        textarea.set_size(280, 40)
        textarea.align(lv.ALIGN.TOP_MID, 0, 10)
        textarea.set_one_line(True)
        wait_for_render(5)

        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        wait_for_render(10)

        print("Rapidly switching modes...")
        modes = [
            MposKeyboard.MODE_LOWERCASE,
            MposKeyboard.MODE_NUMBERS,
            MposKeyboard.MODE_LOWERCASE,
            MposKeyboard.MODE_UPPERCASE,
            MposKeyboard.MODE_LOWERCASE,
            MposKeyboard.MODE_NUMBERS,
            MposKeyboard.MODE_SPECIALS,
            MposKeyboard.MODE_NUMBERS,
            MposKeyboard.MODE_LOWERCASE,
        ]

        for i, mode in enumerate(modes):
            print(f"  Switch {i+1}: mode {mode}")
            keyboard.set_mode(mode)
            # Force rendering - this is where the crash happens
            wait_for_render(2)

        print("SUCCESS: No crash during rapid switching")

    def test_mode_switching_with_standard_modes(self):
        """
        Test switching using standard LVGL modes (TEXT_LOWER, etc).

        This tests if LVGL internally switching modes causes the crash.
        """
        print("\n=== Testing with standard LVGL modes ===")

        textarea = lv.textarea(self.screen)
        textarea.set_size(280, 40)
        textarea.align(lv.ALIGN.TOP_MID, 0, 10)
        textarea.set_one_line(True)
        wait_for_render(5)

        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        wait_for_render(10)

        print("Switching using standard LVGL modes...")

        # Try standard modes
        print("  Switching to TEXT_LOWER")
        keyboard._keyboard.set_mode(lv.keyboard.MODE.TEXT_LOWER)
        wait_for_render(5)

        print("  Switching to NUMBER")
        keyboard._keyboard.set_mode(lv.keyboard.MODE.NUMBER)
        wait_for_render(5)

        print("  Switching back to TEXT_LOWER")
        keyboard._keyboard.set_mode(lv.keyboard.MODE.TEXT_LOWER)
        wait_for_render(5)

        print("SUCCESS: No crash with standard modes")

    def test_multiple_keyboards(self):
        """
        Test creating multiple keyboards to see if that causes issues.
        """
        print("\n=== Testing multiple keyboard creation ===")

        textarea = lv.textarea(self.screen)
        textarea.set_size(280, 40)
        textarea.align(lv.ALIGN.TOP_MID, 0, 10)
        textarea.set_one_line(True)
        wait_for_render(5)

        # Create first keyboard
        print("Creating keyboard 1...")
        keyboard1 = MposKeyboard(self.screen)
        keyboard1.set_textarea(textarea)
        keyboard1.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        wait_for_render(10)

        print("Switching modes on keyboard 1...")
        keyboard1.set_mode(MposKeyboard.MODE_NUMBERS)
        wait_for_render(5)

        print("Deleting keyboard 1...")
        keyboard1._keyboard.delete()
        wait_for_render(5)

        # Create second keyboard
        print("Creating keyboard 2...")
        keyboard2 = MposKeyboard(self.screen)
        keyboard2.set_textarea(textarea)
        keyboard2.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        wait_for_render(10)

        print("Switching modes on keyboard 2...")
        keyboard2.set_mode(MposKeyboard.MODE_UPPERCASE)
        wait_for_render(5)

        print("SUCCESS: Multiple keyboards work")


