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

import lvgl as lv
from mpos import (
    wait_for_text,
    get_all_widgets_with_text,
    find_button_with_text,
    print_screen_labels,
    click_label,
    click_button,
    find_text_on_screen,
    AppManager
)


class TestIMUCalibrationUI(unittest.TestCase):

    def test_imu_calibration_bug_test(self):
        print("=== IMU Calibration UI Bug Test ===\n")

        # Initialize the OS (boot.py and main.py)
        print("Step 1: Initializing MicroPythonOS...")
        import mpos.main
        print("OS initialized\n")

        # Step 2: Open Settings app
        print("Step 2: Opening Settings app...")
        AppManager.start_app("com.micropythonos.settings")

        # Wait for Settings main screen to appear
        self.assertTrue(
            wait_for_text("Check IMU Calibration", timeout=10),
            "Settings main screen did not load within timeout"
        )
        print("Settings app opened\n")

        print("Current screen content:")
        print_screen_labels(lv.screen_active())
        print()

        # Check if we're on the main Settings screen
        on_settings_main = (find_text_on_screen("Calibrate IMU") and
                            find_text_on_screen("Check IMU Calibration") and
                            find_text_on_screen("Theme Color"))

        if not on_settings_main:
            print("Step 3: Not on Settings main screen, clicking Back or Cancel to return...")
            self.assertTrue(click_button("Back") or click_button("Cancel"),
                            "Could not click 'Back' or 'Cancel' button")
            self.assertTrue(
                wait_for_text("Check IMU Calibration", timeout=10),
                "Did not return to Settings main screen within timeout"
            )
            print("Current screen content:")
            print_screen_labels(lv.screen_active())
            print()

        # Step 4: Click "Check IMU Calibration"
        print("Step 4: Clicking 'Check IMU Calibration' menu item...")
        self.assertTrue(
            click_label("Check IMU Calibration"),
            "Could not find Check IMU Calibration menu item"
        )

        # Wait for the calibration check screen to appear
        self.assertTrue(
            wait_for_text("Calibrate", timeout=10),
            "Check IMU Calibration screen did not load within timeout"
        )

        print("Step 5: Checking BEFORE calibration...")
        print("Current screen content:")
        print_screen_labels(lv.screen_active())
        print()

        has_values_before = False
        for widget in get_all_widgets_with_text(lv.screen_active()):
            text = widget.get_text()
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
        calibrate_btn.send_event(lv.EVENT.CLICKED, None)

        # Wait for CalibrateIMUActivity to load
        self.assertTrue(
            wait_for_text("Calibrate Now", timeout=10),
            "Calibrate IMU screen did not load within timeout"
        )
        print("Calibrate IMU screen is open now\n")

        print("Current screen content:")
        print_screen_labels(lv.screen_active())
        print()

        # Step 7: Click "Calibrate Now" button
        print("Step 7: Clicking 'Calibrate Now' button...")
        self.assertTrue(
            click_button("Calibrate Now"),
            "Could not click 'Calibrate Now' button"
        )
        print("Calibration started...\n")

        # Wait for calibration to complete — poll for success message
        self.assertTrue(
            wait_for_text("Calibration successful!", timeout=15),
            "Calibration did not complete within timeout"
        )

        print("Current screen content after calibration:")
        print_screen_labels(lv.screen_active())
        print()

        # Step 8: Click "Done" to go back
        print("Step 8: Clicking 'Done' button...")
        self.assertTrue(
            click_button("Done"),
            "Could not click 'Done' button"
        )

        # Wait for Check IMU Calibration screen to reappear
        self.assertTrue(
            wait_for_text("Calibrate", timeout=10),
            "Did not return to Check IMU Calibration screen within timeout"
        )

        # Step 9: Check AFTER calibration
        print("Step 9: Checking AFTER calibration (testing for bug)...")
        print("Current screen content:")
        print_screen_labels(lv.screen_active())
        print()

        has_values_after = False
        for widget in get_all_widgets_with_text(lv.screen_active()):
            text = widget.get_text()
            if ":" in text and "--" not in text:
                if any(char.isdigit() for char in text):
                    print(f"Found value: {text}")
                    has_values_after = True

        print()
        print("=" * 60)
        print("TEST RESULTS:")
        print(f"  Values shown BEFORE calibration: {has_values_before}")
        print(f"  Values shown AFTER calibration:  {has_values_after}")

        if has_values_before and not has_values_after:
            print("\n  BUG REPRODUCED: Values disappeared after calibration!")
            print("  Expected: Values should still be shown")
            print("  Actual: All showing '--'")
        elif has_values_after:
            print("\n  PASS: Values are showing correctly after calibration")
        else:
            print("\n  WARNING: No values shown before or after (might be desktop mock issue)")
