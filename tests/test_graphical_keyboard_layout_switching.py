"""
Test for keyboard layout switching bug.

This test reproduces the issue where clicking the "Abc" button in numbers mode
goes to the wrong (default LVGL) keyboard layout instead of our custom lowercase layout.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_keyboard_layout_switching.py
    Device:  ./tests/unittest.sh tests/test_graphical_keyboard_layout_switching.py --ondevice
"""

import unittest
import lvgl as lv
from mpos import MposKeyboard, wait_for_render


class TestKeyboardLayoutSwitching(unittest.TestCase):
    """Test keyboard layout switching between different modes."""

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

    def test_abc_button_from_numbers_mode(self):
        """
        Test that clicking "Abc" button in numbers mode goes to lowercase mode.

        BUG: Currently goes to the wrong (default LVGL) keyboard layout
             instead of our custom lowercase layout.

        Expected behavior:
        1. Start in lowercase mode (has "q", "w", "e", etc.)
        2. Switch to numbers mode (has "1", "2", "3", etc. and "Abc" button)
        3. Click "Abc" button
        4. Should return to lowercase mode (has "q", "w", "e", etc.)
        """
        print("\n=== Testing 'Abc' button from numbers mode ===")

        # Create keyboard
        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(self.textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        wait_for_render(10)

        # Verify we start in lowercase mode
        print("Step 1: Verify initial lowercase mode")
        # Find 'q' button (should be in lowercase layout)
        q_button_index = None
        for i in range(100):
            try:
                text = keyboard.get_button_text(i)
                if text == "q":
                    q_button_index = i
                    print(f"  Found 'q' at index {i} - GOOD (lowercase mode)")
                    break
            except:
                pass

        self.assertIsNotNone(q_button_index, "Should find 'q' in lowercase mode")

        # Switch to numbers mode
        print("\nStep 2: Switch to numbers mode")
        keyboard.set_mode(MposKeyboard.MODE_NUMBERS)
        wait_for_render(5)

        # Verify we're in numbers mode by finding '1' button
        one_button_index = None
        for i in range(100):
            try:
                text = keyboard.get_button_text(i)
                if text == "1":
                    one_button_index = i
                    print(f"  Found '1' at index {i} - GOOD (numbers mode)")
                    break
            except:
                pass

        self.assertIsNotNone(one_button_index, "Should find '1' in numbers mode")

        # Find the 'Abc' button in numbers mode
        print("\nStep 3: Find 'Abc' button in numbers mode")
        abc_button_index = None
        for i in range(100):
            try:
                text = keyboard.get_button_text(i)
                if text == "Abc":
                    abc_button_index = i
                    print(f"  Found 'Abc' at index {i}")
                    break
            except:
                pass

        self.assertIsNotNone(abc_button_index, "Should find 'Abc' button in numbers mode")

        # Switch back to lowercase by calling set_mode (simulating clicking 'Abc')
        print("\nStep 4: Click 'Abc' to switch back to lowercase")
        keyboard.set_mode(MposKeyboard.MODE_LOWERCASE)
        wait_for_render(5)

        # Verify we're back in lowercase mode using DISTINGUISHING LABELS
        # When in LOWERCASE mode:
        # - Our custom keyboard has "?123" (to switch to numbers)
        # - Default LVGL keyboard has "1#" (to switch to numbers) and "ABC" (to switch to uppercase)
        #
        # Note: "Abc" only appears in NUMBERS/SPECIALS modes to switch back to lowercase
        print("\nStep 5: Verify we're in OUR custom lowercase mode (not default LVGL)")

        found_labels = {}
        for i in range(100):
            try:
                text = keyboard.get_button_text(i)
                # Check for all possible distinguishing labels
                if text in ["Abc", "ABC", "?123", "1#", lv.SYMBOL.UP, lv.SYMBOL.DOWN]:
                    found_labels[text] = i
                    print(f"  Found label '{text}' at index {i}")
            except:
                pass

        # Check for WRONG labels (default LVGL keyboard in lowercase mode)
        if "ABC" in found_labels:
            print(f"  ERROR: Found 'ABC' - this is the DEFAULT LVGL keyboard!")
            self.fail("BUG DETECTED: Got default LVGL lowercase keyboard with 'ABC' label instead of custom keyboard")

        if "1#" in found_labels:
            print(f"  ERROR: Found '1#' - this is the DEFAULT LVGL keyboard!")
            self.fail("BUG DETECTED: Got default LVGL lowercase keyboard with '1#' label instead of custom keyboard with '?123'")

        # Check for CORRECT labels (our custom lowercase keyboard)
        if "?123" not in found_labels:
            print(f"  ERROR: Did not find '?123' - should be in custom lowercase layout!")
            print(f"  Found labels: {list(found_labels.keys())}")
            self.fail("BUG: Should find '?123' label in custom lowercase mode, but got: " + str(list(found_labels.keys())))

        # Also verify we have the UP symbol (our custom keyboard) not ABC (default)
        if lv.SYMBOL.UP not in found_labels:
            print(f"  ERROR: Did not find UP symbol - should be in custom lowercase layout!")
            print(f"  Found labels: {list(found_labels.keys())}")
            self.fail("BUG: Should find UP symbol in custom lowercase mode")

        print(f"  Found '?123' at index {found_labels['?123']} - GOOD (custom keyboard)")
        print(f"  Found UP symbol at index {found_labels[lv.SYMBOL.UP]} - GOOD (custom keyboard)")
        print("\nSUCCESS: 'Abc' button correctly returns to custom lowercase layout!")

    def test_layout_switching_cycle(self):
        """
        Test full cycle of layout switching: lowercase -> numbers -> specials -> lowercase.

        This ensures all mode switches preserve our custom layouts.
        """
        print("\n=== Testing full layout switching cycle ===")

        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(self.textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        wait_for_render(10)

        # Define what we expect to find in each mode
        mode_tests = [
            (MposKeyboard.MODE_LOWERCASE, "q", "lowercase"),
            (MposKeyboard.MODE_NUMBERS, "1", "numbers"),
            (MposKeyboard.MODE_SPECIALS, "~", "specials"),
            (MposKeyboard.MODE_LOWERCASE, "q", "lowercase (again)"),
        ]

        for mode, expected_key, mode_name in mode_tests:
            print(f"\nSwitching to {mode_name}...")
            keyboard.set_mode(mode)
            wait_for_render(5)

            # Find the expected key
            found = False
            for i in range(100):
                try:
                    text = keyboard.get_button_text(i)
                    if text == expected_key:
                        print(f"  Found '{expected_key}' at index {i} - GOOD")
                        found = True
                        break
                except:
                    pass

            self.assertTrue(found,
                           f"Should find '{expected_key}' in {mode_name} mode")

        print("\nSUCCESS: All layout switches preserve custom layouts!")

    def test_event_handler_switches_layout(self):
        """
        Test that the event handler properly switches layouts.

        This simulates what happens when the user actually CLICKS the "Abc" button,
        going through the _handle_events method instead of calling set_mode() directly.
        """
        print("\n=== Testing event handler layout switching ===")

        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(self.textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        wait_for_render(10)

        # Switch to numbers mode first
        print("Step 1: Switch to numbers mode")
        keyboard.set_mode(MposKeyboard.MODE_NUMBERS)
        wait_for_render(5)

        # Verify we're in numbers mode
        one_found = False
        for i in range(100):
            try:
                if keyboard.get_button_text(i) == "1":
                    one_found = True
                    print(f"  Found '1' - in numbers mode")
                    break
            except:
                pass
        self.assertTrue(one_found, "Should be in numbers mode")

        # Now simulate what the event handler does when "Qbc" is clicked
        # The event handler checks: elif text == lv.SYMBOL.DOWN or text == self.LABEL_LETTERS:
        # Then it calls: self._keyboard.set_map() and self._keyboard.set_mode()
        print("\nStep 2: Simulate clicking 'Abc' (via event handler logic)")

        # This is what the event handler does:
        keyboard._keyboard.set_map(
            MposKeyboard.MODE_LOWERCASE,
            keyboard._lowercase_map,
            keyboard._lowercase_ctrl
        )
        keyboard._keyboard.set_mode(MposKeyboard.MODE_LOWERCASE)
        wait_for_render(5)

        # Verify we're back in lowercase mode with OUR custom layout
        # When in LOWERCASE mode:
        # - Our custom keyboard has "?123" (to switch to numbers)
        # - Default LVGL keyboard has "1#" (to switch to numbers) and "ABC" (to switch to uppercase)
        print("\nStep 3: Verify we have custom lowercase layout (not default LVGL)")

        found_labels = {}
        for i in range(100):
            try:
                text = keyboard.get_button_text(i)
                if text in ["Abc", "ABC", "?123", "1#", lv.SYMBOL.UP]:
                    found_labels[text] = i
                    print(f"  Found label '{text}' at index {i}")
            except:
                pass

        # Check for WRONG labels (default LVGL keyboard)
        if "ABC" in found_labels:
            print(f"  ERROR: Found 'ABC' - this is the DEFAULT LVGL keyboard!")
            print("  Found these labels:", list(found_labels.keys()))
            self.fail("BUG DETECTED: Event handler caused switch to default LVGL keyboard with 'ABC' label")

        if "1#" in found_labels:
            print(f"  ERROR: Found '1#' - this is the DEFAULT LVGL keyboard!")
            print("  Found these labels:", list(found_labels.keys()))
            self.fail("BUG DETECTED: Event handler caused switch to default LVGL keyboard with '1#' label")

        # Check for CORRECT labels (our custom keyboard in lowercase mode)
        self.assertIn("?123", found_labels,
                     "Should find '?123' label in custom lowercase mode (not '1#' from default)")
        self.assertIn(lv.SYMBOL.UP, found_labels,
                     "Should find UP symbol in custom lowercase mode")

        print(f"  Found '?123' at index {found_labels['?123']} - GOOD")
        print(f"  Found UP symbol at index {found_labels[lv.SYMBOL.UP]} - GOOD")
        print("\nSUCCESS: Event handler preserves custom layout!")


