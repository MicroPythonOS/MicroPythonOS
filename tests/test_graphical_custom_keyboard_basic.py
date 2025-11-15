"""
Functional tests for CustomKeyboard.

Tests keyboard creation, mode switching, text input, and API compatibility.

Usage:
    Desktop: ./tests/unittest.sh tests/test_custom_keyboard.py
    Device:  ./tests/unittest.sh tests/test_custom_keyboard.py ondevice
"""

import unittest
import lvgl as lv
from mpos.ui.keyboard import CustomKeyboard, create_keyboard


class TestCustomKeyboard(unittest.TestCase):
    """Test suite for CustomKeyboard functionality."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        # Create a test screen
        self.screen = lv.obj()
        self.screen.set_size(320, 240)

        # Create a textarea for testing
        self.textarea = lv.textarea(self.screen)
        self.textarea.set_size(280, 40)
        self.textarea.align(lv.ALIGN.TOP_MID, 0, 10)
        self.textarea.set_one_line(True)

        print(f"\n=== Test Setup Complete ===")

    def tearDown(self):
        """Clean up after each test method."""
        # Clean up objects
        lv.screen_load(lv.obj())
        print("=== Test Cleanup Complete ===\n")

    def test_keyboard_creation(self):
        """Test that CustomKeyboard can be created."""
        print("Testing keyboard creation...")

        keyboard = CustomKeyboard(self.screen)

        # Verify keyboard exists
        self.assertIsNotNone(keyboard)
        self.assertIsNotNone(keyboard.get_lvgl_obj())

        print("Keyboard created successfully")

    def test_keyboard_factory_custom(self):
        """Test factory function creates custom keyboard."""
        print("Testing factory function with custom=True...")

        keyboard = create_keyboard(self.screen, custom=True)

        # Verify it's a CustomKeyboard instance
        self.assertIsInstance(keyboard, CustomKeyboard)

        print("Factory created CustomKeyboard successfully")

    def test_keyboard_factory_standard(self):
        """Test factory function creates standard keyboard."""
        print("Testing factory function with custom=False...")

        keyboard = create_keyboard(self.screen, custom=False)

        # Verify it's an LVGL keyboard (not CustomKeyboard)
        self.assertFalse(isinstance(keyboard, CustomKeyboard),
                        "Factory with custom=False should not create CustomKeyboard")
        # It should be an lv.keyboard instance
        self.assertEqual(type(keyboard).__name__, 'keyboard')

        print("Factory created standard keyboard successfully")

    def test_set_textarea(self):
        """Test setting textarea association."""
        print("Testing set_textarea...")

        keyboard = CustomKeyboard(self.screen)
        keyboard.set_textarea(self.textarea)

        # Verify textarea is associated
        associated_ta = keyboard.get_textarea()
        self.assertEqual(associated_ta, self.textarea)

        print("Textarea association successful")

    def test_mode_switching(self):
        """Test keyboard mode switching."""
        print("Testing mode switching...")

        keyboard = CustomKeyboard(self.screen)

        # Test setting different modes
        keyboard.set_mode(CustomKeyboard.MODE_LOWERCASE)
        keyboard.set_mode(CustomKeyboard.MODE_UPPERCASE)
        keyboard.set_mode(CustomKeyboard.MODE_NUMBERS)
        keyboard.set_mode(CustomKeyboard.MODE_SPECIALS)

        print("Mode switching successful")

    def test_alignment(self):
        """Test keyboard alignment."""
        print("Testing alignment...")

        keyboard = CustomKeyboard(self.screen)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)

        print("Alignment successful")

    def test_height_settings(self):
        """Test height configuration."""
        print("Testing height settings...")

        keyboard = CustomKeyboard(self.screen)
        keyboard.set_style_min_height(160, 0)
        keyboard.set_style_height(160, 0)

        print("Height settings successful")

    def test_flags(self):
        """Test object flags (show/hide)."""
        print("Testing flags...")

        keyboard = CustomKeyboard(self.screen)

        # Test hiding
        keyboard.add_flag(lv.obj.FLAG.HIDDEN)
        self.assertTrue(keyboard.has_flag(lv.obj.FLAG.HIDDEN))

        # Test showing
        keyboard.remove_flag(lv.obj.FLAG.HIDDEN)
        self.assertFalse(keyboard.has_flag(lv.obj.FLAG.HIDDEN))

        print("Flag operations successful")

    def test_event_callback(self):
        """Test adding event callbacks."""
        print("Testing event callbacks...")

        keyboard = CustomKeyboard(self.screen)
        callback_called = [False]

        def test_callback(event):
            callback_called[0] = True

        # Add callback
        keyboard.add_event_cb(test_callback, lv.EVENT.READY, None)

        # Send READY event
        keyboard.send_event(lv.EVENT.READY, None)

        # Verify callback was called
        self.assertTrue(callback_called[0], "Callback was not called")

        print("Event callback successful")

    def test_api_compatibility(self):
        """Test that CustomKeyboard has same API as lv.keyboard."""
        print("Testing API compatibility...")

        keyboard = CustomKeyboard(self.screen)

        # Check that all essential methods exist
        essential_methods = [
            'set_textarea',
            'get_textarea',
            'set_mode',
            'align',
            'add_flag',
            'remove_flag',
            'has_flag',
            'add_event_cb',
            'send_event',
        ]

        for method_name in essential_methods:
            self.assertTrue(
                hasattr(keyboard, method_name),
                f"CustomKeyboard missing method: {method_name}"
            )
            self.assertTrue(
                callable(getattr(keyboard, method_name)),
                f"CustomKeyboard.{method_name} is not callable"
            )

        print("API compatibility verified")


if __name__ == "__main__":
    unittest.main()
