"""
Test that MposKeyboard forwards all methods to underlying lv.keyboard.

This demonstrates the __getattr__ magic method works correctly and that
MposKeyboard supports any LVGL keyboard method without manual wrapping.

Usage:
    Desktop: ./tests/unittest.sh tests/test_keyboard_method_forwarding.py
"""

import unittest
import lvgl as lv
from mpos.ui.keyboard import MposKeyboard


class TestMethodForwarding(unittest.TestCase):
    """Test that arbitrary LVGL methods are forwarded correctly."""

    def setUp(self):
        """Set up test fixtures."""
        self.screen = lv.obj()
        self.screen.set_size(320, 240)
        lv.screen_load(self.screen)

    def tearDown(self):
        """Clean up."""
        lv.screen_load(lv.obj())

    def test_common_methods_work(self):
        """Test commonly used LVGL methods work via __getattr__."""
        print("\nTesting common LVGL methods...")

        keyboard = MposKeyboard(self.screen)

        # These should all work without explicit wrapper methods:
        methods_to_test = [
            ('set_style_opa', (128, 0)),
            ('get_x', ()),
            ('get_y', ()),
            ('get_width', ()),
            ('get_height', ()),
            ('add_flag', (lv.obj.FLAG.HIDDEN,)),
            ('has_flag', (lv.obj.FLAG.HIDDEN,)),
            ('remove_flag', (lv.obj.FLAG.HIDDEN,)),
        ]

        for method_name, args in methods_to_test:
            try:
                method = getattr(keyboard, method_name)
                result = method(*args)
                print(f"  ✓ {method_name}{args} -> {result}")
            except Exception as e:
                self.fail(f"{method_name} failed: {e}")

        print("All common methods work!")

    def test_style_methods_work(self):
        """Test various style methods work."""
        print("\nTesting style methods...")

        keyboard = MposKeyboard(self.screen)

        # All these style methods should work:
        keyboard.set_style_min_height(100, 0)
        keyboard.set_style_max_height(200, 0)
        keyboard.set_style_height(150, 0)
        keyboard.set_style_opa(255, 0)

        print("All style methods work!")

    def test_position_methods_work(self):
        """Test position methods work."""
        print("\nTesting position methods...")

        keyboard = MposKeyboard(self.screen)

        # Position methods:
        x = keyboard.get_x()
        y = keyboard.get_y()
        print(f"  Initial position: ({x}, {y})")

        keyboard.set_x(50)
        keyboard.set_y(100)
        keyboard.set_pos(25, 75)

        new_x = keyboard.get_x()
        new_y = keyboard.get_y()
        print(f"  After set_pos(25, 75): ({new_x}, {new_y})")

        print("All position methods work!")

    def test_undocumented_methods_still_work(self):
        """
        Test that even undocumented/obscure LVGL methods work.

        The beauty of __getattr__ is that ANY lv.keyboard method works,
        even ones we didn't explicitly think about.
        """
        print("\nTesting that arbitrary LVGL methods work...")

        keyboard = MposKeyboard(self.screen)

        # Try some less common methods:
        try:
            # Get the parent object
            parent = keyboard.get_parent()
            print(f"  ✓ get_parent() -> {parent}")

            # Get style properties
            border_width = keyboard.get_style_border_width(lv.PART.MAIN)
            print(f"  ✓ get_style_border_width() -> {border_width}")

            # These methods exist on lv.obj and should work:
            keyboard.set_style_border_width(2, 0)
            print(f"  ✓ set_style_border_width(2, 0)")

        except Exception as e:
            self.fail(f"Arbitrary LVGL method failed: {e}")

        print("Even undocumented methods work via __getattr__!")

    def test_method_forwarding_preserves_behavior(self):
        """
        Test that forwarded methods behave identically to native calls.
        """
        print("\nTesting that forwarding preserves behavior...")

        keyboard = MposKeyboard(self.screen)
        textarea = lv.textarea(self.screen)

        # Set textarea through MposKeyboard
        keyboard.set_textarea(textarea)

        # Get it back
        returned_ta = keyboard.get_textarea()

        # Should be the same object
        self.assertEqual(returned_ta, textarea,
                        "Forwarded methods should preserve object identity")

        print("Method forwarding preserves behavior correctly!")


if __name__ == "__main__":
    unittest.main()
