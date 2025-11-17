"""
Test for the abc button click bug - comma being added.

This test actually CLICKS the abc button to reproduce the comma bug.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_keyboard_abc_click_bug.py
"""

import unittest
import lvgl as lv
from mpos.ui.keyboard import MposKeyboard
from graphical_test_helper import wait_for_render


class TestAbcButtonClickBug(unittest.TestCase):
    """Test that clicking abc button doesn't add comma."""

    def setUp(self):
        """Set up test fixtures."""
        self.screen = lv.obj()
        self.screen.set_size(320, 240)

        # Create textarea
        self.textarea = lv.textarea(self.screen)
        self.textarea.set_size(280, 40)
        self.textarea.align(lv.ALIGN.TOP_MID, 0, 10)
        self.textarea.set_one_line(True)

        # Load screen
        lv.screen_load(self.screen)
        wait_for_render(5)

    def tearDown(self):
        """Clean up."""
        lv.screen_load(lv.obj())
        wait_for_render(5)

    def test_clicking_abc_button_should_not_add_comma(self):
        """
        Test that actually CLICKING the abc button doesn't add comma.

        This is the REAL test - simulating actual user clicks.
        """
        print("\n=== Testing ACTUAL CLICKING of abc button ===")

        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(self.textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        wait_for_render(10)

        # Start in lowercase, switch to numbers
        print("Step 1: Switch to numbers mode")
        keyboard.set_mode(MposKeyboard.MODE_NUMBERS)
        wait_for_render(10)

        # Clear textarea
        self.textarea.set_text("")
        print(f"  Textarea cleared: '{self.textarea.get_text()}'")

        # Find the "abc" button
        abc_button_index = None
        for i in range(100):
            try:
                text = keyboard.get_button_text(i)
                if text == "abc":
                    abc_button_index = i
                    print(f"  Found 'abc' button at index {i}")
                    break
            except:
                pass

        self.assertIsNotNone(abc_button_index, "Should find 'abc' button in numbers mode")

        # ACTUALLY CLICK THE BUTTON
        print(f"\nStep 2: ACTUALLY CLICK button index {abc_button_index}")
        print(f"  Before click: textarea='{self.textarea.get_text()}'")

        # Simulate button click by sending CLICKED event to the button matrix
        # Get the underlying button matrix object
        btnm = keyboard._keyboard

        # Method 1: Try to programmatically click the button
        # This simulates what happens when user actually touches the button
        btnm.set_selected_button(abc_button_index)
        wait_for_render(2)

        # Send the VALUE_CHANGED event
        btnm.send_event(lv.EVENT.VALUE_CHANGED, None)
        wait_for_render(5)

        textarea_after = self.textarea.get_text()
        print(f"  After click:  textarea='{textarea_after}'")

        # Check if comma was added
        if "," in textarea_after:
            print(f"\n  ❌ BUG CONFIRMED: Comma was added!")
            print(f"     Textarea contains: '{textarea_after}'")
            self.fail(f"BUG: Clicking 'abc' button added comma! Textarea: '{textarea_after}'")

        # Also check if anything else was added
        if textarea_after != "":
            print(f"\n  ❌ BUG CONFIRMED: Something was added!")
            print(f"     Expected: ''")
            print(f"     Got:      '{textarea_after}'")
            self.fail(f"BUG: Clicking 'abc' button added text! Textarea: '{textarea_after}'")

        print(f"\n  ✓ SUCCESS: No text added, textarea is still empty")

    def test_clicking_abc_multiple_times(self):
        """
        Test clicking abc button multiple times in a row.
        """
        print("\n=== Testing MULTIPLE clicks of abc button ===")

        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(self.textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        wait_for_render(10)

        for attempt in range(5):
            print(f"\n--- Attempt {attempt + 1} ---")

            # Go to numbers mode
            keyboard.set_mode(MposKeyboard.MODE_NUMBERS)
            wait_for_render(10)

            # Clear textarea
            self.textarea.set_text("")

            # Find abc button
            abc_button_index = None
            for i in range(100):
                try:
                    text = keyboard.get_button_text(i)
                    if text == "abc":
                        abc_button_index = i
                        break
                except:
                    pass

            # Click it
            print(f"Clicking 'abc' at index {abc_button_index}")
            keyboard._keyboard.set_selected_button(abc_button_index)
            wait_for_render(2)
            keyboard._keyboard.send_event(lv.EVENT.VALUE_CHANGED, None)
            wait_for_render(5)

            textarea_text = self.textarea.get_text()
            print(f"  Result: textarea='{textarea_text}'")

            if textarea_text != "":
                print(f"  ❌ FAIL on attempt {attempt + 1}: Got '{textarea_text}'")
                self.fail(f"Attempt {attempt + 1}: Clicking 'abc' added '{textarea_text}'")
            else:
                print(f"  ✓ OK")

        print("\n✓ SUCCESS: All 5 attempts worked correctly")


if __name__ == "__main__":
    unittest.main()
