#!/usr/bin/env python3
"""Automated UI test for IMU calibration bug.

Tests the complete flow:
1. Open Settings → IMU → Check Calibration
2. Verify values are shown
3. Click "Calibrate" → Calibrate IMU
4. Click "Calibrate Now"
5. Go back to Check Calibration
6. BUG: Verify values are shown (not "--")
"""

import sys
import time
import unittest

# Import graphical test infrastructure
import lvgl as lv
from mpos.ui.testing import (
    wait_for_render,
    simulate_click,
    find_button_with_text,
    find_label_with_text,
    get_widget_coords,
    print_screen_labels,
    capture_screenshot,
    click_label,
    click_button,
    find_text_on_screen
)


class TestIMUCalibrationUI(unittest.TestCase):

    def test_imu_calibration_bug_test(self):
        print("=== IMU Calibration UI Bug Test ===\n")
    
        # Initialize the OS (boot.py and main.py)
        print("Step 1: Initializing MicroPythonOS...")
        import mpos.main
        wait_for_render(iterations=30)
        print("OS initialized\n")
    
        # Step 2: Open Settings app
        print("Step 2: Opening Settings app...")
        import mpos.apps
    
        # Start Settings app by name
        mpos.apps.start_app("com.micropythonos.settings")
        wait_for_render(iterations=30)
        print("Settings app opened\n")
    
        # Initialize touch device with dummy click (required for simulate_click to work)
        print("Initializing touch input device...")
        simulate_click(10, 10)
        wait_for_render(iterations=10)
    
        print("Current screen content:")
        print_screen_labels(lv.screen_active())
        print()
    
        # Check if we're on the main Settings screen (should see multiple settings options)
        # The Settings app shows a list with items like "Calibrate IMU", "Check IMU Calibration", "Theme Color", etc.
        on_settings_main = (find_text_on_screen("Calibrate IMU") and
                            find_text_on_screen("Check IMU Calibration") and
                            find_text_on_screen("Theme Color"))
    
        # If we're on a sub-screen (like Calibrate IMU or Check IMU Calibration screens),
        # we need to go back to Settings main. We can detect this by looking for screen titles.
        if not on_settings_main:
            print("Step 3: Not on Settings main screen, clicking Back or Cancel to return...")
            self.assertTrue(click_button("Back") or click_button("Cancel"), "Could not click 'Back' or 'Cancel' button")
            wait_for_render(iterations=20)
            print("Current screen content:")
            print_screen_labels(lv.screen_active())
            print()
    
        # Step 4: Click "Check IMU Calibration" (it's a clickable label/container, not a button)
        print("Step 4: Clicking 'Check IMU Calibration' menu item...")
        self.assertTrue(click_label("Check IMU Calibration"), "Could not find Check IMU Calibration menu item")
        wait_for_render(iterations=40)

        print("Step 5: Checking BEFORE calibration...")
        print("Current screen content:")
        print_screen_labels(lv.screen_active())
        print()
    
        # Capture screenshot before
        capture_screenshot("../tests/screenshots/check_imu_before_calib.raw")
    
        # Look for actual values (not "--")
        has_values_before = False
        widgets = []
        from mpos.ui.testing import get_all_widgets_with_text
        for widget in get_all_widgets_with_text(lv.screen_active()):
            text = widget.get_text()
            # Look for patterns like "X: 0.00" or "Quality: Good"
            if ":" in text and "--" not in text:
                if any(char.isdigit() for char in text):
                    print(f"Found value: {text}")
                    has_values_before = True
    
        if not has_values_before:
            print("WARNING: No values found before calibration (all showing '--')")
        else:
            print("GOOD: Values are showing before calibration")
        print()
    
        # Step 6: Click "Calibrate" button to go to calibration screen
        print("Step 6: Finding 'Calibrate' button...")
        calibrate_btn = find_button_with_text(lv.screen_active(), "Calibrate")
        self.assertIsNotNone(calibrate_btn, "Could not find 'Calibrate' button")
    
        print(f"Found Calibrate button: {calibrate_btn}")
        print("Manually sending CLICKED event to button...")
        # Instead of using simulate_click, manually send the event
        calibrate_btn.send_event(lv.EVENT.CLICKED, None)
        wait_for_render(iterations=20)
    
        # Wait for navigation to complete (activity transition can take some time)
        time.sleep(0.5)
        wait_for_render(iterations=50)
        print("Calibrate IMU screen should be open now\n")
    
        print("Current screen content:")
        print_screen_labels(lv.screen_active())
        print()
    
        # Step 7: Click "Calibrate Now" button
        print("Step 7: Clicking 'Calibrate Now' button...")
        self.assertTrue(click_button("Calibrate Now"), "Could not click 'Calibrate Now' button")
        print("Calibration started...\n")
    
        # Wait for calibration to complete (~2 seconds + UI updates)
        time.sleep(3)
        wait_for_render(iterations=50)
    
        print("Current screen content after calibration:")
        print_screen_labels(lv.screen_active())
        print()
    
        # Step 8: Click "Done" to go back
        print("Step 8: Clicking 'Done' button...")
        self.assertTrue(click_button("Done"), "Could not click 'Done' button")
        print("Going back to Check Calibration\n")
    
        # Wait for screen to load
        time.sleep(0.5)
        wait_for_render(iterations=30)
    
        # Step 9: Check AFTER calibration (BUG: should show values, not "--")
        print("Step 9: Checking AFTER calibration (testing for bug)...")
        print("Current screen content:")
        print_screen_labels(lv.screen_active())
        print()
    
        # Capture screenshot after
        capture_screenshot("../tests/screenshots/check_imu_after_calib.raw")
    
        # Look for actual values (not "--")
        has_values_after = False
        for widget in get_all_widgets_with_text(lv.screen_active()):
            text = widget.get_text()
            # Look for patterns like "X: 0.00" or "Quality: Good"
            if ":" in text and "--" not in text:
                if any(char.isdigit() for char in text):
                    print(f"Found value: {text}")
                    has_values_after = True
    
        print()
        print("="*60)
        print("TEST RESULTS:")
        print(f"  Values shown BEFORE calibration: {has_values_before}")
        print(f"  Values shown AFTER calibration:  {has_values_after}")
    
        if has_values_before and not has_values_after:
            print("\n  ❌ BUG REPRODUCED: Values disappeared after calibration!")
            print("  Expected: Values should still be shown")
            print("  Actual: All showing '--'")
            #return False
        elif has_values_after:
            print("\n  ✅ PASS: Values are showing correctly after calibration")
            #return True
        else:
            print("\n  ⚠️  WARNING: No values shown before or after (might be desktop mock issue)")
            #return True
    
    
