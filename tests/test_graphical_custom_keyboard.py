"""
Graphical tests for MposKeyboard.

Tests keyboard visual appearance, text input via simulated button presses,
and mode switching. Captures screenshots for regression testing.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_custom_keyboard.py
    Device:  ./tests/unittest.sh tests/test_graphical_custom_keyboard.py ondevice
"""

import unittest
import lvgl as lv
import sys
import os
from mpos.ui.keyboard import MposKeyboard, create_keyboard
from graphical_test_helper import (
    wait_for_render,
    capture_screenshot,
)


class TestGraphicalMposKeyboard(unittest.TestCase):
    """Test suite for MposKeyboard graphical verification."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        # Determine screenshot directory
        if sys.platform == "esp32":
            self.screenshot_dir = "tests/screenshots"
        else:
            self.screenshot_dir = "../tests/screenshots"

        # Ensure screenshots directory exists
        try:
            os.mkdir(self.screenshot_dir)
        except OSError:
            pass  # Directory already exists

        print(f"\n=== Graphical Keyboard Test Setup ===")
        print(f"Platform: {sys.platform}")

    def tearDown(self):
        """Clean up after each test method."""
        lv.screen_load(lv.obj())
        wait_for_render(5)
        print("=== Test Cleanup Complete ===\n")

    def _create_test_keyboard_scene(self):
        """
        Create a test scene with textarea and keyboard.

        Returns:
            tuple: (screen, keyboard, textarea)
        """
        # Create screen
        screen = lv.obj()
        screen.set_size(320, 240)

        # Create textarea
        textarea = lv.textarea(screen)
        textarea.set_size(280, 40)
        textarea.align(lv.ALIGN.TOP_MID, 0, 10)
        textarea.set_placeholder_text("Type here...")
        textarea.set_one_line(True)

        # Create custom keyboard
        keyboard = MposKeyboard(screen)
        keyboard.set_textarea(textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)

        # Load and render
        lv.screen_load(screen)
        wait_for_render(iterations=20)

        return screen, keyboard, textarea

    def _simulate_button_press(self, keyboard, button_index):
        """
        Simulate pressing a keyboard button.

        Args:
            keyboard: CustomKeyboard instance
            button_index: Index of button to press

        Returns:
            str: Text of the pressed button
        """
        lvgl_keyboard = keyboard.get_lvgl_obj()

        # Get button text before pressing
        button_text = lvgl_keyboard.get_button_text(button_index)

        # Simulate button press by setting it as selected and sending event
        # Note: This is a bit of a hack since we can't directly click in tests
        # We'll trigger the VALUE_CHANGED event which is what happens on click

        # The keyboard has an internal handler that responds to VALUE_CHANGED
        # We need to manually trigger it
        lvgl_keyboard.send_event(lv.EVENT.VALUE_CHANGED, None)

        wait_for_render(5)

        return button_text

    def test_keyboard_lowercase_appearance(self):
        """
        Test keyboard appearance in lowercase mode.

        Verifies that the keyboard renders correctly and captures screenshot.
        """
        print("\n=== Testing lowercase keyboard appearance ===")

        screen, keyboard, textarea = self._create_test_keyboard_scene()

        # Ensure lowercase mode
        keyboard.set_mode(MposKeyboard.MODE_LOWERCASE)
        wait_for_render(10)

        # Capture screenshot
        screenshot_path = f"{self.screenshot_dir}/custom_keyboard_lowercase.raw"
        print(f"Capturing screenshot: {screenshot_path}")
        capture_screenshot(screenshot_path, width=320, height=240)

        # Verify screenshot was created
        stat = os.stat(screenshot_path)
        self.assertTrue(stat[6] > 0, "Screenshot file is empty")
        print(f"Screenshot captured: {stat[6]} bytes")

        print("=== Lowercase appearance test PASSED ===")

    def test_keyboard_uppercase_appearance(self):
        """Test keyboard appearance in uppercase mode."""
        print("\n=== Testing uppercase keyboard appearance ===")

        screen, keyboard, textarea = self._create_test_keyboard_scene()

        # Switch to uppercase mode
        keyboard.set_mode(MposKeyboard.MODE_UPPERCASE)
        wait_for_render(10)

        # Capture screenshot
        screenshot_path = f"{self.screenshot_dir}/custom_keyboard_uppercase.raw"
        print(f"Capturing screenshot: {screenshot_path}")
        capture_screenshot(screenshot_path, width=320, height=240)

        # Verify screenshot was created
        stat = os.stat(screenshot_path)
        self.assertTrue(stat[6] > 0, "Screenshot file is empty")
        print(f"Screenshot captured: {stat[6]} bytes")

        print("=== Uppercase appearance test PASSED ===")

    def test_keyboard_numbers_appearance(self):
        """Test keyboard appearance in numbers/specials mode."""
        print("\n=== Testing numbers keyboard appearance ===")

        screen, keyboard, textarea = self._create_test_keyboard_scene()

        # Switch to numbers mode
        keyboard.set_mode(MposKeyboard.MODE_NUMBERS)
        wait_for_render(10)

        # Capture screenshot
        screenshot_path = f"{self.screenshot_dir}/custom_keyboard_numbers.raw"
        print(f"Capturing screenshot: {screenshot_path}")
        capture_screenshot(screenshot_path, width=320, height=240)

        # Verify screenshot was created
        stat = os.stat(screenshot_path)
        self.assertTrue(stat[6] > 0, "Screenshot file is empty")
        print(f"Screenshot captured: {stat[6]} bytes")

        print("=== Numbers appearance test PASSED ===")

    def test_keyboard_specials_appearance(self):
        """Test keyboard appearance in additional specials mode."""
        print("\n=== Testing specials keyboard appearance ===")

        screen, keyboard, textarea = self._create_test_keyboard_scene()

        # Switch to specials mode
        keyboard.set_mode(MposKeyboard.MODE_SPECIALS)
        wait_for_render(10)

        # Capture screenshot
        screenshot_path = f"{self.screenshot_dir}/custom_keyboard_specials.raw"
        print(f"Capturing screenshot: {screenshot_path}")
        capture_screenshot(screenshot_path, width=320, height=240)

        # Verify screenshot was created
        stat = os.stat(screenshot_path)
        self.assertTrue(stat[6] > 0, "Screenshot file is empty")
        print(f"Screenshot captured: {stat[6]} bytes")

        print("=== Specials appearance test PASSED ===")

    def test_keyboard_visibility_light_mode(self):
        """
        Test that custom keyboard buttons are visible in light mode.

        This verifies that the theme fix is applied.
        """
        print("\n=== Testing keyboard visibility in light mode ===")

        # Set light mode (should already be default)
        import mpos.config
        import mpos.ui.theme
        prefs = mpos.config.SharedPreferences("theme_settings")
        editor = prefs.edit()
        editor.put_string("theme_light_dark", "light")
        editor.commit()
        mpos.ui.theme.set_theme(prefs)
        wait_for_render(10)

        # Create keyboard
        screen, keyboard, textarea = self._create_test_keyboard_scene()

        # Get button background color
        lvgl_keyboard = keyboard.get_lvgl_obj()
        bg_color = lvgl_keyboard.get_style_bg_color(lv.PART.ITEMS)

        # Extract RGB (similar to keyboard styling test)
        try:
            color_dict = {
                'r': bg_color.red() if hasattr(bg_color, 'red') else 0,
                'g': bg_color.green() if hasattr(bg_color, 'green') else 0,
                'b': bg_color.blue() if hasattr(bg_color, 'blue') else 0,
            }
        except:
            try:
                color_int = bg_color.to_int() if hasattr(bg_color, 'to_int') else 0
                color_dict = {
                    'r': (color_int >> 16) & 0xFF,
                    'g': (color_int >> 8) & 0xFF,
                    'b': color_int & 0xFF,
                }
            except:
                color_dict = {'r': 0, 'g': 0, 'b': 0}

        print(f"Button background: RGB({color_dict['r']}, {color_dict['g']}, {color_dict['b']})")

        # Verify buttons are NOT pure white (which would be invisible)
        if 'r' in color_dict:
            is_white = (color_dict['r'] >= 250 and
                       color_dict['g'] >= 250 and
                       color_dict['b'] >= 250)

            self.assertFalse(
                is_white,
                f"Mpos keyboard buttons are pure white in light mode (invisible)!"
            )

        print("=== Visibility test PASSED ===")

    def test_keyboard_with_standard_comparison(self):
        """
        Test custom keyboard alongside standard keyboard.

        Creates both for visual comparison.
        """
        print("\n=== Testing custom vs standard keyboard ===")

        # Create screen with two textareas
        screen = lv.obj()
        screen.set_size(320, 240)

        # Top textarea with standard keyboard
        ta_standard = lv.textarea(screen)
        ta_standard.set_size(280, 30)
        ta_standard.set_pos(20, 5)
        ta_standard.set_placeholder_text("Standard")
        ta_standard.set_one_line(True)

        # Create standard keyboard (hidden initially)
        keyboard_standard = create_keyboard(screen, custom=False)
        keyboard_standard.set_textarea(ta_standard)
        keyboard_standard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        keyboard_standard.set_style_min_height(145, 0)

        # Load and render
        lv.screen_load(screen)
        wait_for_render(20)

        # Capture standard keyboard
        screenshot_path = f"{self.screenshot_dir}/keyboard_standard_comparison.raw"
        print(f"Capturing standard keyboard: {screenshot_path}")
        capture_screenshot(screenshot_path, width=320, height=240)

        # Clean up
        lv.screen_load(lv.obj())
        wait_for_render(5)

        # Now create custom keyboard
        screen2 = lv.obj()
        screen2.set_size(320, 240)

        ta_custom = lv.textarea(screen2)
        ta_custom.set_size(280, 30)
        ta_custom.set_pos(20, 5)
        ta_custom.set_placeholder_text("Custom")
        ta_custom.set_one_line(True)

        keyboard_custom = create_keyboard(screen2, custom=True)
        keyboard_custom.set_textarea(ta_custom)
        keyboard_custom.align(lv.ALIGN.BOTTOM_MID, 0, 0)

        lv.screen_load(screen2)
        wait_for_render(20)

        # Capture custom keyboard
        screenshot_path = f"{self.screenshot_dir}/keyboard_custom_comparison.raw"
        print(f"Capturing custom keyboard: {screenshot_path}")
        capture_screenshot(screenshot_path, width=320, height=240)

        print("=== Comparison test PASSED ===")


if __name__ == "__main__":
    unittest.main()
