"""
Test MposKeyboard animation support (show/hide with mpos.ui.anim).

This test reproduces the bug where MposKeyboard is missing methods
required by mpos.ui.anim.smooth_show() and smooth_hide().

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_keyboard_animation.py
    Device:  ./tests/unittest.sh tests/test_graphical_keyboard_animation.py --ondevice
"""

import unittest
import lvgl as lv
import time
import mpos.ui.anim
from mpos.ui.keyboard import MposKeyboard
from mpos.ui.testing import wait_for_render

class TestKeyboardAnimation(unittest.TestCase):
    """Test MposKeyboard compatibility with animation system."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a test screen
        self.screen = lv.obj()
        self.screen.set_size(320, 240)
        lv.screen_load(self.screen)

        # Create textarea
        self.textarea = lv.textarea(self.screen)
        self.textarea.set_size(280, 40)
        self.textarea.align(lv.ALIGN.TOP_MID, 0, 10)
        self.textarea.set_one_line(True)

        print("\n=== Animation Test Setup Complete ===")

    def tearDown(self):
        """Clean up after test."""
        lv.screen_load(lv.obj())
        print("=== Test Cleanup Complete ===\n")

    def test_keyboard_has_set_style_opa(self):
        """
        Test that MposKeyboard has set_style_opa method.

        This method is required by mpos.ui.anim for fade animations.
        """
        print("Testing that MposKeyboard has set_style_opa...")

        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(self.textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        keyboard.add_flag(lv.obj.FLAG.HIDDEN)

        # Verify method exists
        self.assertTrue(
            hasattr(keyboard, 'set_style_opa'),
            "MposKeyboard missing set_style_opa method"
        )
        self.assertTrue(
            callable(getattr(keyboard, 'set_style_opa')),
            "MposKeyboard.set_style_opa is not callable"
        )

        # Try calling it (should not raise AttributeError)
        try:
            keyboard.set_style_opa(128, 0)
            print("set_style_opa called successfully")
        except AttributeError as e:
            self.fail(f"set_style_opa raised AttributeError: {e}")

        print("=== set_style_opa test PASSED ===")

    def test_keyboard_smooth_show(self):
        """
        Test that MposKeyboard can be shown with smooth_show animation.

        This reproduces the actual user interaction in QuasiNametag.
        """
        print("Testing smooth_show animation...")

        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(self.textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        keyboard.add_flag(lv.obj.FLAG.HIDDEN)

        # This should work without raising AttributeError
        try:
            mpos.ui.anim.smooth_show(keyboard)
            wait_for_render(100)
            print("smooth_show called successfully")
        except AttributeError as e:
            self.fail(f"smooth_show raised AttributeError: {e}\n"
                     "This is the bug - MposKeyboard missing animation methods")

        # Verify keyboard is no longer hidden
        self.assertFalse(
            keyboard.has_flag(lv.obj.FLAG.HIDDEN),
            "Keyboard should not be hidden after smooth_show"
        )

        print("=== smooth_show test PASSED ===")

    def test_keyboard_smooth_hide(self):
        """
        Test that MposKeyboard can be hidden with smooth_hide animation.

        This reproduces the hide behavior in QuasiNametag.
        """
        print("Testing smooth_hide animation...")

        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(self.textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        # Start visible
        keyboard.remove_flag(lv.obj.FLAG.HIDDEN)

        # This should work without raising AttributeError
        try:
            mpos.ui.anim.smooth_hide(keyboard)
            print("smooth_hide called successfully")
        except AttributeError as e:
            self.fail(f"smooth_hide raised AttributeError: {e}\n"
                     "This is the bug - MposKeyboard missing animation methods")

        print("=== smooth_hide test PASSED ===")

    def test_keyboard_show_hide_cycle(self):
        """
        Test full show/hide animation cycle.

        This mimics the actual user flow:
        1. Click textarea -> show keyboard
        2. Press Enter/Cancel -> hide keyboard
        """
        print("Testing full show/hide cycle...")

        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(self.textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        keyboard.add_flag(lv.obj.FLAG.HIDDEN)

        # Initial state: hidden
        self.assertTrue(keyboard.has_flag(lv.obj.FLAG.HIDDEN))

        # Show keyboard (simulates textarea click)
        try:
            mpos.ui.anim.smooth_show(keyboard)
            wait_for_render(100)
        except AttributeError as e:
            self.fail(f"Failed during smooth_show: {e}")

        # Should be visible now
        self.assertFalse(keyboard.has_flag(lv.obj.FLAG.HIDDEN))

        # Hide keyboard (simulates pressing Enter)
        try:
            mpos.ui.anim.smooth_hide(keyboard)
            wait_for_render(100)
        except AttributeError as e:
            self.fail(f"Failed during smooth_hide: {e}")

        print("=== Full cycle test PASSED ===")

    def test_keyboard_has_get_y_and_set_y(self):
        """
        Test that MposKeyboard has get_y and set_y methods.

        These are required for slide animations (though not currently used).
        """
        print("Testing get_y and set_y methods...")

        keyboard = MposKeyboard(self.screen)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)

        # Verify methods exist
        self.assertTrue(hasattr(keyboard, 'get_y'), "Missing get_y method")
        self.assertTrue(hasattr(keyboard, 'set_y'), "Missing set_y method")

        # Try using them
        try:
            y = keyboard.get_y()
            keyboard.set_y(y + 10)
            new_y = keyboard.get_y()
            print(f"Position test: {y} -> {new_y}")
        except AttributeError as e:
            self.fail(f"Position methods raised AttributeError: {e}")

        print("=== Position methods test PASSED ===")


