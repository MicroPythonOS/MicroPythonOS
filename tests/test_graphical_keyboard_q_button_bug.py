"""
Test for keyboard button functionality (originally created to fix "q" button bug).

This test verifies that all keyboard buttons work correctly, including the
'q' button which was previously broken due to button index 0 being treated
as False in Python's truthiness check.

The bug was: `if not button:` would return True when button index was 0,
causing the 'q' key to be ignored. Fixed by changing to `if button is None:`.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_keyboard_q_button_bug.py
    Device:  ./tests/unittest.sh tests/test_graphical_keyboard_q_button_bug.py --ondevice
"""

import unittest
from base import KeyboardTestBase


class TestKeyboardQButton(KeyboardTestBase):
    """Test keyboard button functionality (especially 'q' which was at index 0)."""

    def test_q_button_works(self):
        """
        Test that clicking the 'q' button adds 'q' to textarea.

        This test verifies the fix for the bug where:
        - Bug: Button index 0 ('q') was treated as False in `if not button:`
        - Fix: Changed to `if button is None:` to properly handle index 0

        Steps:
        1. Create textarea and keyboard
        2. Click 'q' button using click_keyboard_button helper
        3. Verify 'q' appears in textarea (should PASS after fix)
        4. Repeat with 'a' button
        5. Verify 'a' appears correctly (should PASS)
        """
        print("\n=== Testing keyboard 'q' and 'a' button behavior ===")

        # Create keyboard scene (textarea + keyboard)
        self.create_keyboard_scene()

        print(f"Initial textarea: '{self.get_textarea_text()}'")
        self.assertTextareaEmpty("Textarea should start empty")

        # --- Test 'q' button ---
        print("\n--- Testing 'q' button ---")

        # Click the 'q' button using the reliable click_keyboard_button helper
        success = self.click_keyboard_button("q")
        self.assertTrue(success, "Should find and click 'q' button on keyboard")

        # Check textarea content
        text_after_q = self.get_textarea_text()
        print(f"Textarea after clicking 'q': '{text_after_q}'")

        # Verify 'q' was added (should work after fix)
        self.assertTextareaText("q", "Clicking 'q' button should add 'q' to textarea")

        # --- Test 'a' button for comparison ---
        print("\n--- Testing 'a' button (for comparison) ---")

        # Clear textarea
        self.clear_textarea()
        print("Cleared textarea")

        # Click the 'a' button using the reliable click_keyboard_button helper
        success = self.click_keyboard_button("a")
        self.assertTrue(success, "Should find and click 'a' button on keyboard")

        # Check textarea content
        text_after_a = self.get_textarea_text()
        print(f"Textarea after clicking 'a': '{text_after_a}'")

        # The 'a' button should work correctly
        self.assertTextareaText("a", "Clicking 'a' button should add 'a' to textarea")

        print("\nSummary:")
        print(f"  'q' button result: '{text_after_q}' (expected 'q') ✓")
        print(f"  'a' button result: '{text_after_a}' (expected 'a') ✓")
        print("  Both buttons work correctly!")

    def test_keyboard_button_discovery(self):
        """
        Debug test: Discover all buttons on the keyboard.

        This test helps understand the keyboard layout and button structure.
        It prints all found buttons and their text.
        """
        print("\n=== Discovering keyboard buttons ===")

        # Create keyboard scene
        self.create_keyboard_scene()

        # Get all buttons using the base class helper
        found_buttons = self.get_all_keyboard_buttons()

        # Print first 20 buttons
        print("\nEnumerating keyboard buttons by index:")
        for idx, text in found_buttons[:20]:
            print(f"  Button {idx}: '{text}'")

        if len(found_buttons) > 20:
            print(f"  ... (showing first 20 of {len(found_buttons)} buttons)")

        print(f"\nTotal buttons found: {len(found_buttons)}")

        # Try to find specific letters
        letters_to_test = ['q', 'w', 'e', 'r', 'a', 's', 'd', 'f']
        print("\nLooking for specific letters:")

        for letter in letters_to_test:
            idx = self.find_keyboard_button_index(letter)
            if idx is not None:
                print(f"  '{letter}' at index {idx}")
            else:
                print(f"  '{letter}' NOT FOUND")

        # Verify we can find at least some buttons
        self.assertTrue(len(found_buttons) > 0,
                       "Should find at least some buttons on keyboard")
