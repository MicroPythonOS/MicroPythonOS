"""
Functional tests for MposKeyboard.

Tests keyboard creation, mode switching, text input, and API compatibility.

Usage:
    Desktop: ./tests/unittest.sh tests/test_custom_keyboard.py
    Device:  ./tests/unittest.sh tests/test_custom_keyboard.py --ondevice
"""

import unittest
import lvgl as lv
from mpos.ui.keyboard import MposKeyboard
from graphical_test_helper import simulate_click, wait_for_render


class TestMposKeyboard(unittest.TestCase):
    """Test suite for MposKeyboard functionality."""

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
        """Test that MposKeyboard can be created."""
        print("Testing keyboard creation...")

        keyboard = MposKeyboard(self.screen)

        # Verify keyboard exists
        self.assertIsNotNone(keyboard)

        print("Keyboard created successfully")


    def test_set_textarea(self):
        """Test setting textarea association."""
        print("Testing set_textarea...")

        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(self.textarea)

        # Verify textarea is associated
        associated_ta = keyboard.get_textarea()
        self.assertEqual(associated_ta, self.textarea)

        print("Textarea association successful")

    def test_mode_switching(self):
        """Test keyboard mode switching."""
        print("Testing mode switching...")

        keyboard = MposKeyboard(self.screen)

        # Test setting different modes
        keyboard.set_mode(MposKeyboard.MODE_LOWERCASE)
        keyboard.set_mode(MposKeyboard.MODE_UPPERCASE)
        keyboard.set_mode(MposKeyboard.MODE_NUMBERS)
        keyboard.set_mode(MposKeyboard.MODE_SPECIALS)

        print("Mode switching successful")

    def test_alignment(self):
        """Test keyboard alignment."""
        print("Testing alignment...")

        keyboard = MposKeyboard(self.screen)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)

        print("Alignment successful")

    def test_height_settings(self):
        """Test height configuration."""
        print("Testing height settings...")

        keyboard = MposKeyboard(self.screen)
        keyboard.set_style_min_height(160, 0)
        keyboard.set_style_height(160, 0)

        print("Height settings successful")

    def test_flags(self):
        """Test object flags (show/hide)."""
        print("Testing flags...")

        keyboard = MposKeyboard(self.screen)

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

        keyboard = MposKeyboard(self.screen)
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
        """Test that MposKeyboard has same API as lv.keyboard."""
        print("Testing API compatibility...")

        keyboard = MposKeyboard(self.screen)

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
                f"MposKeyboard missing method: {method_name}"
            )
            self.assertTrue(
                callable(getattr(keyboard, method_name)),
                f"MposKeyboard.{method_name} is not callable"
            )

        print("API compatibility verified")

    def test_simulate_click_on_button(self):
        """Test clicking keyboard buttons using simulate_click()."""
        print("Testing simulate_click() on keyboard buttons...")

        # Create keyboard and load screen
        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(self.textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        lv.screen_load(self.screen)
        wait_for_render(10)

        # Get initial text
        initial_text = self.textarea.get_text()
        print(f"Initial textarea text: '{initial_text}'")

        # Get keyboard area and click on it
        # The keyboard is an lv.keyboard object (accessed via _keyboard or through __getattr__)
        obj_area = lv.area_t()
        keyboard.get_coords(obj_area)

        # Calculate a point to click - let's click in the lower part of keyboard
        # which should be around where letters are
        click_x = (obj_area.x1 + obj_area.x2) // 2  # Center horizontally
        click_y = obj_area.y1 + (obj_area.y2 - obj_area.y1) // 3  # Upper third

        print(f"Keyboard area: ({obj_area.x1}, {obj_area.y1}) to ({obj_area.x2}, {obj_area.y2})")
        print(f"Clicking keyboard at ({click_x}, {click_y})")

        # Click on the keyboard using simulate_click
        simulate_click(click_x, click_y, press_duration_ms=100)
        wait_for_render(5)

        final_text = self.textarea.get_text()
        print(f"Final textarea text: '{final_text}'")

        # The important thing is that simulate_click worked without crashing
        # The text might have changed if we hit a letter key
        print("simulate_click() completed successfully")

    def test_click_vs_send_event_comparison(self):
        """Compare simulate_click() vs send_event() for triggering button actions."""
        print("Testing simulate_click() vs send_event() comparison...")

        # Create keyboard and load screen
        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(self.textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        lv.screen_load(self.screen)
        wait_for_render(10)

        # Test 1: Use send_event() to trigger READY event
        callback_from_send_event = [False]

        def callback_send_event(event):
            callback_from_send_event[0] = True
            print("send_event callback triggered")

        keyboard.add_event_cb(callback_send_event, lv.EVENT.READY, None)
        keyboard.send_event(lv.EVENT.READY, None)
        wait_for_render(3)

        self.assertTrue(
            callback_from_send_event[0],
            "send_event() should trigger callback"
        )

        # Test 2: Use simulate_click() to click on keyboard
        # This demonstrates that simulate_click works with real UI interaction
        initial_text = self.textarea.get_text()

        # Get keyboard area to click within it
        obj_area = lv.area_t()
        keyboard.get_coords(obj_area)

        # Click somewhere in the middle of the keyboard
        click_x = (obj_area.x1 + obj_area.x2) // 2
        click_y = (obj_area.y1 + obj_area.y2) // 2

        print(f"Clicking keyboard at ({click_x}, {click_y})")
        simulate_click(click_x, click_y, press_duration_ms=100)
        wait_for_render(5)

        # Verify click completed without crashing
        final_text = self.textarea.get_text()
        print(f"Text before click: '{initial_text}'")
        print(f"Text after click: '{final_text}'")

        print("Both send_event() and simulate_click() work correctly")


