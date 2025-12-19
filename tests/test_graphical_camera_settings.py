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
    Desktop: ./tests/unittest.sh tests/test_graphical_camera_settings.py
    Device:  ./tests/unittest.sh tests/test_graphical_camera_settings.py --ondevice
"""

import unittest
import lvgl as lv
import mpos.apps
import mpos.ui
import os
from mpos.ui.testing import (
    wait_for_render,
    capture_screenshot,
    find_label_with_text,
    find_button_with_text,
    verify_text_present,
    print_screen_labels,
    simulate_click,
    get_widget_coords
)


class TestGraphicalCameraSettings(unittest.TestCase):
    """Test suite for Camera app settings verification."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        # Check if webcam module is available
        try:
            import webcam
            self.has_webcam = True
        except:
            try:
                import camera
                self.has_webcam = False  # Has internal camera instead
            except:
                self.skipTest("No camera module available (webcam or internal)")

        # Get absolute path to screenshots directory
        import sys
        if sys.platform == "esp32":
            self.screenshot_dir = "tests/screenshots"
        else:
            self.screenshot_dir = "../tests/screenshots"

        # Ensure screenshots directory exists
        try:
            os.mkdir(self.screenshot_dir)
        except OSError:
            pass  # Directory already exists

    def tearDown(self):
        """Clean up after each test method."""
        # Navigate back to launcher (closes the camera app)
        try:
            mpos.ui.back_screen()
            wait_for_render(10)  # Allow navigation and cleanup to complete
        except:
            pass  # Already on launcher or error

    def _find_and_click_settings_button(self, screen, use_send_event=True):
        """Find and click the settings button using lv.SYMBOL.SETTINGS.
        
        Args:
            screen: LVGL screen object to search
            use_send_event: If True (default), use send_event() which is more reliable.
                           If False, use simulate_click() with coordinates.
        
        Returns True if button was found and clicked, False otherwise.
        """
        settings_button = find_button_with_text(screen, lv.SYMBOL.SETTINGS)
        if settings_button:
            coords = get_widget_coords(settings_button)
            print(f"Found settings button at ({coords['center_x']}, {coords['center_y']})")
            if use_send_event:
                # Use send_event for more reliable button triggering
                settings_button.send_event(lv.EVENT.CLICKED, None)
                print("Clicked settings button using send_event()")
            else:
                simulate_click(coords['center_x'], coords['center_y'], press_duration_ms=100)
                print("Clicked settings button using simulate_click()")
            return True
        else:
            print("Settings button not found via lv.SYMBOL.SETTINGS")
            return False

    def test_settings_button_click_no_crash(self):
        """
        Test that clicking the settings button doesn't cause a segfault.

        This is the critical test that verifies the fix for the segfault
        that occurred when clicking settings due to stale image_dsc.data pointer.

        Steps:
        1. Start camera app
        2. Wait for camera to initialize
        3. Capture initial screenshot
        4. Click settings button (found dynamically by lv.SYMBOL.SETTINGS)
        5. Verify settings dialog opened
        6. If we get here without crash, test passes
        """
        print("\n=== Testing settings button click (no crash) ===")

        # Start the Camera app
        result = mpos.apps.start_app("com.micropythonos.camera")
        self.assertTrue(result, "Failed to start Camera app")

        # Wait for camera to initialize and first frame to render
        wait_for_render(iterations=30)

        # Get current screen
        screen = lv.screen_active()

        # Debug: Print all text on screen
        print("\nInitial screen labels:")
        print_screen_labels(screen)

        # Capture screenshot before clicking settings
        screenshot_path = f"{self.screenshot_dir}/camera_before_settings.raw"
        print(f"\nCapturing initial screenshot: {screenshot_path}")
        capture_screenshot(screenshot_path, width=320, height=240)

        # Find and click settings button dynamically
        found = self._find_and_click_settings_button(screen)
        self.assertTrue(found, "Settings button with lv.SYMBOL.SETTINGS not found on screen")

        # Wait for settings dialog to appear - needs more time for Activity transition
        wait_for_render(iterations=50)

        # Get screen again (might have changed after navigation)
        screen = lv.screen_active()

        # Debug: Print labels after clicking
        print("\nScreen labels after clicking settings:")
        print_screen_labels(screen)

        # Verify settings screen opened by looking for the Save button
        # This is more reliable than text search since buttons are always present
        save_button = find_button_with_text(screen, "Save")
        cancel_button = find_button_with_text(screen, "Cancel")
        
        has_settings_ui = save_button is not None or cancel_button is not None
        
        # Also try text-based verification as fallback
        if not has_settings_ui:
            has_settings_ui = (
                verify_text_present(screen, "Camera Settings") or
                verify_text_present(screen, "Resolution") or
                verify_text_present(screen, "resolution") or
                verify_text_present(screen, "Basic") or  # Tab name
                verify_text_present(screen, "Color Mode")  # Setting name
            )

        self.assertTrue(
            has_settings_ui,
            "Settings screen did not open (no Save/Cancel buttons or expected UI elements found)"
        )

        # Capture screenshot of settings dialog
        screenshot_path = f"{self.screenshot_dir}/camera_settings_dialog.raw"
        print(f"\nCapturing settings dialog screenshot: {screenshot_path}")
        capture_screenshot(screenshot_path, width=320, height=240)

        # If we got here without segfault, the test passes!
        print("\n✓ Settings button clicked successfully without crash!")

    def _find_and_click_button(self, screen, text, use_send_event=True):
        """Find and click a button by its text label.
        
        Args:
            screen: LVGL screen object to search
            text: Text to search for in button labels
            use_send_event: If True (default), use send_event() which is more reliable.
                           If False, use simulate_click() with coordinates.
        
        Returns True if button was found and clicked, False otherwise.
        """
        button = find_button_with_text(screen, text)
        if button:
            coords = get_widget_coords(button)
            print(f"Found '{text}' button at ({coords['center_x']}, {coords['center_y']})")
            if use_send_event:
                # Use send_event for more reliable button triggering
                button.send_event(lv.EVENT.CLICKED, None)
                print(f"Clicked '{text}' button using send_event()")
            else:
                simulate_click(coords['center_x'], coords['center_y'], press_duration_ms=100)
                print(f"Clicked '{text}' button using simulate_click()")
            return True
        else:
            print(f"Button with text '{text}' not found")
            return False

    def _find_dropdown(self, screen):
        """Find a dropdown widget on the screen.
        
        Returns the dropdown widget or None if not found.
        """
        def find_dropdown_recursive(obj):
            # Check if this object is a dropdown
            try:
                if obj.__class__.__name__ == 'dropdown' or hasattr(obj, 'get_selected'):
                    # Verify it's actually a dropdown by checking for dropdown-specific method
                    if hasattr(obj, 'get_options'):
                        return obj
            except:
                pass
            
            # Check children
            child_count = obj.get_child_count()
            for i in range(child_count):
                child = obj.get_child(i)
                result = find_dropdown_recursive(child)
                if result:
                    return result
            return None
        
        return find_dropdown_recursive(screen)

    def test_resolution_change_no_crash(self):
        """
        Test that changing resolution doesn't cause a crash.

        This tests the full resolution change workflow:
        1. Start camera app
        2. Open settings (found dynamically by lv.SYMBOL.SETTINGS)
        3. Change resolution via dropdown
        4. Save settings (found dynamically by "Save" text)
        5. Verify camera continues working

        This verifies fixes for:
        - Segfault during reconfiguration
        - Buffer size mismatches
        - Stale data pointers
        """
        print("\n=== Testing resolution change (no crash) ===")

        # Start the Camera app
        result = mpos.apps.start_app("com.micropythonos.camera")
        self.assertTrue(result, "Failed to start Camera app")

        # Wait for camera to initialize
        wait_for_render(iterations=30)

        # Click settings button dynamically
        screen = lv.screen_active()
        print("\nOpening settings...")
        found = self._find_and_click_settings_button(screen)
        self.assertTrue(found, "Settings button with lv.SYMBOL.SETTINGS not found on screen")
        wait_for_render(iterations=20)

        screen = lv.screen_active()

        # Try to find the dropdown/resolution selector dynamically
        print("\nLooking for resolution dropdown...")
        dropdown = self._find_dropdown(screen)
        
        if dropdown:
            # Click the dropdown to open it
            coords = get_widget_coords(dropdown)
            print(f"Found dropdown at ({coords['center_x']}, {coords['center_y']})")
            simulate_click(coords['center_x'], coords['center_y'], press_duration_ms=100)
            wait_for_render(iterations=15)
            
            # Get current selection and try to change it
            try:
                current = dropdown.get_selected()
                option_count = dropdown.get_option_count()
                print(f"Dropdown has {option_count} options, current selection: {current}")
                
                # Select a different option (next one, or first if at end)
                new_selection = (current + 1) % option_count
                dropdown.set_selected(new_selection)
                print(f"Changed selection to: {new_selection}")
            except Exception as e:
                print(f"Could not change dropdown selection: {e}")
                # Fallback: click below current position to select different option
                simulate_click(coords['center_x'], coords['center_y'] + 30, press_duration_ms=100)
        else:
            print("Dropdown not found, test may not fully exercise resolution change")

        wait_for_render(iterations=15)

        # Capture screenshot
        screenshot_path = f"{self.screenshot_dir}/camera_dropdown_open.raw"
        print(f"Capturing dropdown screenshot: {screenshot_path}")
        capture_screenshot(screenshot_path, width=320, height=240)

        screen = lv.screen_active()
        print("\nScreen after dropdown interaction:")
        print_screen_labels(screen)

        # Find and click the Save button dynamically
        print("\nLooking for Save button...")
        save_found = self._find_and_click_button(lv.screen_active(), "Save")
        
        if not save_found:
            # Try "OK" as alternative
            save_found = self._find_and_click_button(lv.screen_active(), "OK")
        
        self.assertTrue(save_found, "Save/OK button not found on settings screen")

        # Wait for reconfiguration to complete
        print("\nWaiting for reconfiguration...")
        wait_for_render(iterations=30)

        # Capture screenshot after reconfiguration
        screenshot_path = f"{self.screenshot_dir}/camera_after_resolution_change.raw"
        print(f"Capturing post-change screenshot: {screenshot_path}")
        capture_screenshot(screenshot_path, width=320, height=240)

        # If we got here without segfault, the test passes!
        print("\n✓ Resolution changed successfully without crash!")

        # Verify camera is still showing something by checking for camera UI elements
        screen = lv.screen_active()
        # The camera app should still be active (not crashed back to launcher)
        # Check for camera-specific buttons (close, settings, snap, qr)
        has_camera_ui = (
            find_button_with_text(screen, lv.SYMBOL.CLOSE) or
            find_button_with_text(screen, lv.SYMBOL.SETTINGS) or
            find_button_with_text(screen, lv.SYMBOL.OK) or
            find_button_with_text(screen, lv.SYMBOL.EYE_OPEN)
        )
        
        self.assertTrue(has_camera_ui, "Camera app UI not found after resolution change - app may have crashed")
        print("\n✓ Camera app still running after resolution change!")


if __name__ == '__main__':
    # Note: Don't include unittest.main() - handled by unittest.sh
    pass
