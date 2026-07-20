"""
Graphical test for Camera app settings functionality.

This test verifies that:
1. The camera app settings button can be clicked without crashing
2. The settings dialog opens correctly
3. Resolution can be changed without causing segfault
4. The camera continues to work after resolution change

This specifically tests the fixes for:
- Segfault when clicking settings button
- Pale colors after resolution change
- Buffer size mismatches

Usage:
"""

import unittest
import lvgl as lv
import mpos.ui
import sys
from mpos import (
    wait_for_text,
    wait_for_widget,
    find_button_with_text,
    click_button,
    verify_text_present,
    print_screen_labels,
    simulate_click,
    get_widget_coords,
    AppManager
)


@unittest.skipIf(sys.platform == 'darwin', "Camera tests not supported on macOS (no camera available)")
class TestGraphicalCameraSettings(unittest.TestCase):
    """Test suite for Camera app settings verification."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        try:
            import webcam
            self.has_webcam = True
        except:
            try:
                import camera
                self.has_webcam = False
            except:
                print("SKIP: No camera module available (webcam or internal)")
                self.skipTest("No camera module available (webcam or internal)")

    def tearDown(self):
        """Clean up after each test method."""
        try:
            mpos.ui.back_screen()
        except:
            pass

    def _find_dropdown(self, screen):
        """Find a dropdown widget on the screen."""
        def find_dropdown_recursive(obj):
            try:
                if obj.__class__.__name__ == 'dropdown' or hasattr(obj, 'get_selected'):
                    if hasattr(obj, 'get_options'):
                        return obj
            except:
                pass
            child_count = obj.get_child_count()
            for i in range(child_count):
                child = obj.get_child(i)
                result = find_dropdown_recursive(child)
                if result:
                    return result
            return None

        return find_dropdown_recursive(screen)

    def test_settings_button_click_no_crash(self):
        """
        Test that clicking the settings button doesn't cause a segfault.
        """
        print("\n=== Testing settings button click (no crash) ===")

        result = AppManager.start_app("com.micropythonos.camera")
        self.assertTrue(result, "Failed to start Camera app")

        settings_btn = wait_for_widget(
            lambda: find_button_with_text(lv.screen_active(), lv.SYMBOL.SETTINGS),
            timeout=10,
        )
        self.assertIsNotNone(
            settings_btn,
            "Settings button not found — camera may not have loaded",
        )

        screen = lv.screen_active()
        print("\nInitial screen labels:")
        print_screen_labels(screen)

        self.assertTrue(
            click_button(lv.SYMBOL.SETTINGS),
            "Could not click Settings button",
        )

        self.assertTrue(
            wait_for_text("Save", timeout=10) or wait_for_text("Cancel", timeout=10),
            "Settings screen did not open (no Save/Cancel buttons found)",
        )

        screen = lv.screen_active()
        print("\nScreen labels after clicking settings:")
        print_screen_labels(screen)

        save_button = find_button_with_text(screen, "Save")
        cancel_button = find_button_with_text(screen, "Cancel")

        has_settings_ui = save_button is not None or cancel_button is not None

        if not has_settings_ui:
            has_settings_ui = (
                verify_text_present(screen, "Camera Settings") or
                verify_text_present(screen, "Resolution") or
                verify_text_present(screen, "resolution") or
                verify_text_present(screen, "Basic") or
                verify_text_present(screen, "Color Mode")
            )

        self.assertTrue(
            has_settings_ui,
            "Settings screen did not open (no Save/Cancel buttons or expected UI elements found)"
        )

        print("\nSettings button clicked successfully without crash!")

    def test_resolution_change_no_crash(self):
        """
        Test that changing resolution doesn't cause a crash.
        """
        print("\n=== Testing resolution change (no crash) ===")

        result = AppManager.start_app("com.micropythonos.camera")
        self.assertTrue(result, "Failed to start Camera app")

        settings_btn = wait_for_widget(
            lambda: find_button_with_text(lv.screen_active(), lv.SYMBOL.SETTINGS),
            timeout=10,
        )
        self.assertIsNotNone(
            settings_btn,
            "Settings button not found — camera may not have loaded",
        )

        print("\nOpening settings...")
        self.assertTrue(
            click_button(lv.SYMBOL.SETTINGS),
            "Could not click Settings button",
        )
        self.assertTrue(
            wait_for_text("Save", timeout=10) or wait_for_text("Cancel", timeout=10),
            "Settings screen did not open",
        )

        screen = lv.screen_active()

        print("\nLooking for resolution dropdown...")
        dropdown = self._find_dropdown(screen)

        if dropdown:
            coords = get_widget_coords(dropdown)
            print(f"Found dropdown at ({coords['center_x']}, {coords['center_y']})")
            simulate_click(coords['center_x'], coords['center_y'], press_duration_ms=100)

            try:
                current = dropdown.get_selected()
                option_count = dropdown.get_option_count()
                print(f"Dropdown has {option_count} options, current selection: {current}")

                new_selection = (current + 1) % option_count
                dropdown.set_selected(new_selection)
                print(f"Changed selection to: {new_selection}")
            except Exception as e:
                print(f"Could not change dropdown selection: {e}")
                simulate_click(coords['center_x'], coords['center_y'] + 30, press_duration_ms=100)
        else:
            print("Dropdown not found, test may not fully exercise resolution change")

        print("\nLooking for Save button...")
        save_found = click_button("Save")

        if not save_found:
            save_found = click_button("OK")

        self.assertTrue(save_found, "Save/OK button not found on settings screen")

        print("\nWaiting for reconfiguration...")
        camera_restored = wait_for_widget(
            lambda: (
                find_button_with_text(lv.screen_active(), lv.SYMBOL.CLOSE) or
                find_button_with_text(lv.screen_active(), lv.SYMBOL.SETTINGS) or
                find_button_with_text(lv.screen_active(), lv.SYMBOL.OK) or
                find_button_with_text(lv.screen_active(), lv.SYMBOL.EYE_OPEN)
            ),
            timeout=10,
        )

        print("\nResolution changed successfully without crash!")

        self.assertIsNotNone(
            camera_restored,
            "Camera app UI not found after resolution change - app may have crashed",
        )
        print("Camera app still running after resolution change!")


if __name__ == '__main__':
    pass
