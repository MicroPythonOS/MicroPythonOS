"""
Test for keyboard "q" button bug.

This test reproduces the issue where typing "q" on the keyboard results in
the button lighting up but no character being added to the textarea, while
the "a" button beneath it works correctly.

The test uses helper functions to locate buttons by their text, get their
coordinates, and simulate clicks using simulate_click().

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_keyboard_q_button_bug.py
    Device:  ./tests/unittest.sh tests/test_graphical_keyboard_q_button_bug.py --ondevice
"""

import unittest
import lvgl as lv
from mpos.ui.keyboard import MposKeyboard
from mpos.ui.testing import (
    wait_for_render,
    find_button_with_text,
    get_widget_coords,
    simulate_click,
    print_screen_labels
)


class TestKeyboardQButtonBug(unittest.TestCase):
    """Test keyboard 'q' button behavior vs 'a' button."""

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

    def test_q_button_bug(self):
        """
        Test that clicking the 'q' button adds 'q' to textarea.

        This test demonstrates the bug where:
        1. Clicking 'q' button lights it up but doesn't add to textarea
        2. Clicking 'a' button works correctly

        Steps:
        1. Create textarea and keyboard
        2. Find 'q' button index in keyboard map
        3. Get button coordinates from keyboard widget
        4. Click it using simulate_click()
        5. Verify 'q' appears in textarea (EXPECTED TO FAIL due to bug)
        6. Repeat with 'a' button
        7. Verify 'a' appears correctly (EXPECTED TO PASS)
        """
        print("\n=== Testing keyboard 'q' and 'a' button behavior ===")

        # Create textarea
        textarea = lv.textarea(self.screen)
        textarea.set_size(200, 30)
        textarea.set_one_line(True)
        textarea.align(lv.ALIGN.TOP_MID, 0, 10)
        textarea.set_text("")  # Start empty
        wait_for_render(5)

        # Create keyboard and connect to textarea
        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        wait_for_render(10)

        print(f"Initial textarea: '{textarea.get_text()}'")
        self.assertEqual(textarea.get_text(), "", "Textarea should start empty")

        # --- Test 'q' button ---
        print("\n--- Testing 'q' button ---")

        # Find button index for 'q' in the keyboard
        q_button_id = None
        for i in range(100):  # Check first 100 button indices
            try:
                text = keyboard.get_button_text(i)
                if text == "q":
                    q_button_id = i
                    print(f"Found 'q' button at index {i}")
                    break
            except:
                break  # No more buttons

        self.assertIsNotNone(q_button_id, "Should find 'q' button on keyboard")

        # Get the keyboard widget coordinates to calculate button position
        keyboard_area = lv.area_t()
        keyboard.get_coords(keyboard_area)
        print(f"Keyboard area: x1={keyboard_area.x1}, y1={keyboard_area.y1}, x2={keyboard_area.x2}, y2={keyboard_area.y2}")

        # LVGL keyboards organize buttons in a grid
        # From the map: "q" is at index 0, in top row (10 buttons per row)
        # Let's estimate position based on keyboard layout
        # Top row starts at y1 + some padding, each button is ~width/10
        keyboard_width = keyboard_area.x2 - keyboard_area.x1
        keyboard_height = keyboard_area.y2 - keyboard_area.y1
        button_width = keyboard_width // 10  # ~10 buttons per row
        button_height = keyboard_height // 4  # ~4 rows

        # 'q' is first button (index 0), top row
        q_x = keyboard_area.x1 + button_width // 2
        q_y = keyboard_area.y1 + button_height // 2

        print(f"Estimated 'q' button position: ({q_x}, {q_y})")

        # Click the 'q' button
        print(f"Clicking 'q' button at ({q_x}, {q_y})")
        simulate_click(q_x, q_y)
        wait_for_render(10)

        # Check textarea content
        text_after_q = textarea.get_text()
        print(f"Textarea after clicking 'q': '{text_after_q}'")

        # THIS IS THE BUG: 'q' should be added but isn't
        if text_after_q != "q":
            print("BUG REPRODUCED: 'q' button was clicked but 'q' was NOT added to textarea!")
            print("Expected: 'q'")
            print(f"Got: '{text_after_q}'")

        self.assertEqual(text_after_q, "q",
                        "Clicking 'q' button should add 'q' to textarea (BUG: This test will fail)")

        # --- Test 'a' button for comparison ---
        print("\n--- Testing 'a' button (for comparison) ---")

        # Clear textarea
        textarea.set_text("")
        wait_for_render(5)
        print("Cleared textarea")

        # Find button index for 'a'
        a_button_id = None
        for i in range(100):
            try:
                text = keyboard.get_button_text(i)
                if text == "a":
                    a_button_id = i
                    print(f"Found 'a' button at index {i}")
                    break
            except:
                break

        self.assertIsNotNone(a_button_id, "Should find 'a' button on keyboard")

        # 'a' is at index 11 (second row, first position)
        a_x = keyboard_area.x1 + button_width // 2
        a_y = keyboard_area.y1 + button_height + button_height // 2

        print(f"Estimated 'a' button position: ({a_x}, {a_y})")

        # Click the 'a' button
        print(f"Clicking 'a' button at ({a_x}, {a_y})")
        simulate_click(a_x, a_y)
        wait_for_render(10)

        # Check textarea content
        text_after_a = textarea.get_text()
        print(f"Textarea after clicking 'a': '{text_after_a}'")

        # The 'a' button should work correctly
        self.assertEqual(text_after_a, "a",
                        "Clicking 'a' button should add 'a' to textarea (should PASS)")

        print("\nSummary:")
        print(f"  'q' button result: '{text_after_q}' (expected 'q')")
        print(f"  'a' button result: '{text_after_a}' (expected 'a')")
        if text_after_q != "q" and text_after_a == "a":
            print("  BUG CONFIRMED: 'q' doesn't work but 'a' does!")

    def test_keyboard_button_discovery(self):
        """
        Debug test: Discover all buttons on the keyboard.

        This test helps understand the keyboard layout and button structure.
        It prints all found buttons and their text.
        """
        print("\n=== Discovering keyboard buttons ===")

        # Create keyboard without textarea to inspect it
        keyboard = MposKeyboard(self.screen)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        wait_for_render(10)

        # Iterate through button indices to find all buttons
        print("\nEnumerating keyboard buttons by index:")
        found_buttons = []

        for i in range(100):  # Check first 100 indices
            try:
                text = keyboard.get_button_text(i)
                if text:  # Skip None/empty
                    found_buttons.append((i, text))
                    # Only print first 20 to avoid clutter
                    if i < 20:
                        print(f"  Button {i}: '{text}'")
            except:
                # No more buttons
                break

        if len(found_buttons) > 20:
            print(f"  ... (showing first 20 of {len(found_buttons)} buttons)")

        print(f"\nTotal buttons found: {len(found_buttons)}")

        # Try to find specific letters
        letters_to_test = ['q', 'w', 'e', 'r', 'a', 's', 'd', 'f']
        print("\nLooking for specific letters:")

        for letter in letters_to_test:
            found = False
            for idx, text in found_buttons:
                if text == letter:
                    print(f"  '{letter}' at index {idx}")
                    found = True
                    break
            if not found:
                print(f"  '{letter}' NOT FOUND")

        # Verify we can find at least some buttons
        self.assertTrue(len(found_buttons) > 0,
                       "Should find at least some buttons on keyboard")


if __name__ == "__main__":
    unittest.main()
