"""
Graphical test for on-screen keyboard button styling.

This test verifies that keyboard buttons have proper visible contrast
in both light and dark modes. It checks for the bug where keyboard buttons
appear white-on-white in light mode on ESP32.

The test uses two approaches:
1. Programmatic: Query LVGL style properties to verify button background colors
2. Visual: Capture screenshots for manual verification and regression testing

This test should INITIALLY FAIL, demonstrating the bug before the fix is applied.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_keyboard_styling.py
    Device:  ./tests/unittest.sh tests/test_graphical_keyboard_styling.py ondevice
"""

import unittest
import lvgl as lv
import mpos.ui
import mpos.config
import sys
import os
from graphical_test_helper import (
    wait_for_render,
    capture_screenshot,
)


class TestKeyboardStyling(unittest.TestCase):
    """Test suite for keyboard button visibility and styling."""

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

        # Save current theme setting
        prefs = mpos.config.SharedPreferences("theme_settings")
        self.original_theme = prefs.get_string("theme_light_dark", "light")

        print(f"\n=== Keyboard Styling Test Setup ===")
        print(f"Platform: {sys.platform}")
        print(f"Original theme: {self.original_theme}")

    def tearDown(self):
        """Clean up after each test method."""
        # Restore original theme
        prefs = mpos.config.SharedPreferences("theme_settings")
        editor = prefs.edit()
        editor.put_string("theme_light_dark", self.original_theme)
        editor.commit()

        # Reapply original theme
        mpos.ui.theme.set_theme(prefs)

        print("=== Test cleanup complete ===\n")

    def _create_test_keyboard(self):
        """
        Create a test keyboard widget for inspection.

        Returns:
            tuple: (screen, keyboard, textarea) widgets
        """
        # Create a clean screen
        screen = lv.obj()
        screen.set_size(320, 240)

        # Create a text area for the keyboard to target
        textarea = lv.textarea(screen)
        textarea.set_size(280, 40)
        textarea.align(lv.ALIGN.TOP_MID, 0, 10)
        textarea.set_placeholder_text("Type here...")

        # Create the keyboard
        keyboard = lv.keyboard(screen)
        keyboard.set_textarea(textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        keyboard.set_style_min_height(160, 0)

        # Apply the keyboard button fix
        mpos.ui.theme.fix_keyboard_button_style(keyboard)

        # Load the screen and wait for rendering
        lv.screen_load(screen)
        wait_for_render(iterations=20)

        return screen, keyboard, textarea

    def _get_button_background_color(self, keyboard):
        """
        Extract the background color of keyboard buttons.

        This queries LVGL's style system to get the actual rendered
        background color of the keyboard's button parts (LV_PART_ITEMS).

        Args:
            keyboard: LVGL keyboard widget

        Returns:
            dict: Color information with 'r', 'g', 'b' values (0-255)
        """
        # Get the style property for button background color
        # LV_PART_ITEMS is the part that represents individual buttons
        bg_color = keyboard.get_style_bg_color(lv.PART.ITEMS)

        # Extract RGB values from LVGL color
        # Note: LVGL colors are in RGB565 or RGB888 depending on config
        # We convert to RGB888 for comparison
        r = lv.color_brightness(bg_color) if hasattr(lv, 'color_brightness') else 0

        # Try to get RGB components directly
        try:
            # For LVGL 9.x, colors have direct accessors
            color_dict = {
                'r': bg_color.red() if hasattr(bg_color, 'red') else 0,
                'g': bg_color.green() if hasattr(bg_color, 'green') else 0,
                'b': bg_color.blue() if hasattr(bg_color, 'blue') else 0,
            }
        except:
            # Fallback: use color as hex value
            try:
                color_int = bg_color.to_int() if hasattr(bg_color, 'to_int') else 0
                color_dict = {
                    'r': (color_int >> 16) & 0xFF,
                    'g': (color_int >> 8) & 0xFF,
                    'b': color_int & 0xFF,
                    'hex': f"#{color_int:06x}"
                }
            except:
                # Last resort: just store the color object
                color_dict = {'color_obj': bg_color}

        return color_dict

    def _get_screen_background_color(self, screen):
        """
        Extract the background color of the screen.

        Args:
            screen: LVGL screen object

        Returns:
            dict: Color information with 'r', 'g', 'b' values (0-255)
        """
        bg_color = screen.get_style_bg_color(lv.PART.MAIN)

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
                    'hex': f"#{color_int:06x}"
                }
            except:
                color_dict = {'color_obj': bg_color}

        return color_dict

    def _color_contrast_sufficient(self, color1, color2, min_difference=20):
        """
        Check if two colors have sufficient contrast.

        Uses simple RGB distance. For production, you might want to use
        proper contrast ratio calculation (WCAG).

        Args:
            color1: Dict with 'r', 'g', 'b' keys
            color2: Dict with 'r', 'g', 'b' keys
            min_difference: Minimum RGB distance for sufficient contrast

        Returns:
            bool: True if contrast is sufficient
        """
        if 'r' not in color1 or 'r' not in color2:
            # Can't determine, assume failure
            return False

        # Calculate Euclidean distance in RGB space
        r_diff = abs(color1['r'] - color2['r'])
        g_diff = abs(color1['g'] - color2['g'])
        b_diff = abs(color1['b'] - color2['b'])

        # Simple average difference
        avg_diff = (r_diff + g_diff + b_diff) / 3

        print(f"  Color 1: RGB({color1['r']}, {color1['g']}, {color1['b']})")
        print(f"  Color 2: RGB({color2['r']}, {color2['g']}, {color2['b']})")
        print(f"  Average difference: {avg_diff:.1f} (min required: {min_difference})")

        return avg_diff >= min_difference

    def test_keyboard_buttons_visible_in_light_mode(self):
        """
        Test that keyboard buttons are visible in light mode.

        In light mode, the screen background is white. Keyboard buttons
        should NOT be white - they should be a light gray color to provide
        contrast.

        This test will FAIL initially, demonstrating the bug.
        """
        print("\n=== Testing keyboard buttons in LIGHT mode ===")

        # Set theme to light mode
        prefs = mpos.config.SharedPreferences("theme_settings")
        editor = prefs.edit()
        editor.put_string("theme_light_dark", "light")
        editor.commit()

        # Apply theme
        mpos.ui.theme.set_theme(prefs)
        wait_for_render(iterations=10)

        # Create test keyboard
        screen, keyboard, textarea = self._create_test_keyboard()

        # Get colors
        button_bg = self._get_button_background_color(keyboard)
        screen_bg = self._get_screen_background_color(screen)

        print("\nLight mode colors:")
        print(f"  Screen background: {screen_bg}")
        print(f"  Button background: {button_bg}")

        # Capture screenshot
        screenshot_path = f"{self.screenshot_dir}/keyboard_light_mode.raw"
        print(f"\nCapturing screenshot: {screenshot_path}")
        capture_screenshot(screenshot_path, width=320, height=240)

        # Verify contrast
        print("\nChecking button/screen contrast...")
        has_contrast = self._color_contrast_sufficient(button_bg, screen_bg, min_difference=20)

        # Clean up
        lv.screen_load(lv.obj())
        wait_for_render(5)

        # Assert: buttons should have sufficient contrast with background
        self.assertTrue(
            has_contrast,
            f"Keyboard buttons lack sufficient contrast in light mode!\n"
            f"Button color: {button_bg}\n"
            f"Screen color: {screen_bg}\n"
            f"This is the BUG we're trying to fix - buttons are white on white."
        )

        print("=== Light mode test PASSED ===")

    def test_keyboard_buttons_visible_in_dark_mode(self):
        """
        Test that keyboard buttons are visible in dark mode.

        In dark mode, buttons should have proper contrast with the
        dark background. This typically works correctly.
        """
        print("\n=== Testing keyboard buttons in DARK mode ===")

        # Set theme to dark mode
        prefs = mpos.config.SharedPreferences("theme_settings")
        editor = prefs.edit()
        editor.put_string("theme_light_dark", "dark")
        editor.commit()

        # Apply theme
        mpos.ui.theme.set_theme(prefs)
        wait_for_render(iterations=10)

        # Create test keyboard
        screen, keyboard, textarea = self._create_test_keyboard()

        # Get colors
        button_bg = self._get_button_background_color(keyboard)
        screen_bg = self._get_screen_background_color(screen)

        print("\nDark mode colors:")
        print(f"  Screen background: {screen_bg}")
        print(f"  Button background: {button_bg}")

        # Capture screenshot
        screenshot_path = f"{self.screenshot_dir}/keyboard_dark_mode.raw"
        print(f"\nCapturing screenshot: {screenshot_path}")
        capture_screenshot(screenshot_path, width=320, height=240)

        # Verify contrast
        print("\nChecking button/screen contrast...")
        has_contrast = self._color_contrast_sufficient(button_bg, screen_bg, min_difference=20)

        # Clean up
        lv.screen_load(lv.obj())
        wait_for_render(5)

        # Assert: buttons should have sufficient contrast
        self.assertTrue(
            has_contrast,
            f"Keyboard buttons lack sufficient contrast in dark mode!\n"
            f"Button color: {button_bg}\n"
            f"Screen color: {screen_bg}"
        )

        print("=== Dark mode test PASSED ===")

    def test_keyboard_buttons_not_pure_white_in_light_mode(self):
        """
        Specific test: In light mode, buttons should NOT be pure white.

        They should be a light gray (approximately RGB(238, 238, 238) or similar).
        Pure white (255, 255, 255) means they're invisible on white background.
        """
        print("\n=== Testing that buttons are NOT pure white in light mode ===")

        # Set theme to light mode
        prefs = mpos.config.SharedPreferences("theme_settings")
        editor = prefs.edit()
        editor.put_string("theme_light_dark", "light")
        editor.commit()

        # Apply theme
        mpos.ui.theme.set_theme(prefs)
        wait_for_render(iterations=10)

        # Create test keyboard
        screen, keyboard, textarea = self._create_test_keyboard()

        # Get button color
        button_bg = self._get_button_background_color(keyboard)

        print(f"\nButton background color: {button_bg}")

        # Clean up
        lv.screen_load(lv.obj())
        wait_for_render(5)

        # Check if button is pure white (or very close to it)
        if 'r' in button_bg:
            is_white = (button_bg['r'] >= 250 and
                       button_bg['g'] >= 250 and
                       button_bg['b'] >= 250)

            print(f"Is button pure white? {is_white}")

            # Assert: buttons should NOT be pure white
            self.assertFalse(
                is_white,
                f"Keyboard buttons are pure white in light mode!\n"
                f"Button color: RGB({button_bg['r']}, {button_bg['g']}, {button_bg['b']})\n"
                f"Expected: Light gray around RGB(238, 238, 238) or similar\n"
                f"This is the BUG - white buttons on white background are invisible."
            )
        else:
            # Couldn't extract RGB, fail the test
            self.fail(f"Could not extract RGB values from button color: {button_bg}")

        print("=== Pure white test PASSED ===")


if __name__ == "__main__":
    # Note: This file is executed by unittest.sh which handles unittest.main()
    # But we include it here for completeness
    unittest.main()
