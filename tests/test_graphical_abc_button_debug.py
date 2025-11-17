"""
Automated test that simulates clicking the abc button and shows debug output.

This will show us exactly what's happening when the abc button is clicked.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_abc_button_debug.py
"""

import unittest
import lvgl as lv
from mpos.ui.keyboard import MposKeyboard
from graphical_test_helper import wait_for_render


class TestAbcButtonDebug(unittest.TestCase):
    """Test that shows debug output when clicking abc button."""

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

    def test_simulate_abc_button_click(self):
        """
        Simulate clicking the abc button and show what happens.
        """
        print("\n" + "="*70)
        print("SIMULATING ABC BUTTON CLICK - WATCH FOR DEBUG OUTPUT")
        print("="*70)

        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(self.textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        wait_for_render(10)

        # Start in lowercase, switch to numbers
        print("\n>>> Switching to NUMBERS mode...")
        keyboard.set_mode(MposKeyboard.MODE_NUMBERS)
        wait_for_render(10)

        # Wait for debounce period to expire (150ms + margin)
        import time
        print(">>> Waiting 200ms for debounce period to expire...")
        time.sleep(0.2)

        # Clear textarea
        self.textarea.set_text("")
        print(f">>> Textarea cleared: '{self.textarea.get_text()}'")

        # Find the "abc" button
        abc_button_index = None
        for i in range(100):
            try:
                text = keyboard.get_button_text(i)
                if text == "abc":
                    abc_button_index = i
                    print(f">>> Found 'abc' button at index {abc_button_index}")
                    break
            except:
                pass

        # Now simulate what happens when user TOUCHES the button
        # When user touches a button, LVGL's button matrix:
        # 1. Sets the button as selected
        # 2. Triggers VALUE_CHANGED event
        print(f"\n>>> Simulating user clicking button {abc_button_index}...")
        print(f">>> Before click: textarea = '{self.textarea.get_text()}'")
        print("\n--- DEBUG OUTPUT SHOULD APPEAR BELOW ---\n")

        # Trigger the VALUE_CHANGED event which our handler catches
        # This simulates a real button press
        keyboard._keyboard.send_event(lv.EVENT.VALUE_CHANGED, None)
        wait_for_render(5)

        print("\n--- END DEBUG OUTPUT ---\n")

        textarea_after = self.textarea.get_text()
        print(f">>> After click:  textarea = '{textarea_after}'")

        if textarea_after != "":
            print(f"\n❌ BUG CONFIRMED!")
            print(f"   Expected: '' (empty)")
            print(f"   Got:      '{textarea_after}'")
        else:
            print(f"\n✓ No text added (but check debug output above)")

        print("="*70)


if __name__ == "__main__":
    unittest.main()
