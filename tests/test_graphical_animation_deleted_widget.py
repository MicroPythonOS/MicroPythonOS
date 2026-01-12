"""
Test that animations handle deleted widgets gracefully.

This test reproduces the crash that occurs when:
1. An animation is started on a widget (e.g., keyboard fade-in)
2. The widget is deleted while the animation is running (e.g., user closes app)
3. The animation callback tries to access the deleted widget
4. Result: LvReferenceError crash

The fix should make animations check if the widget still exists before
trying to access it.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_animation_deleted_widget.py
    Device:  ./tests/unittest.sh tests/test_graphical_animation_deleted_widget.py --ondevice
"""

import unittest
import lvgl as lv
import mpos.ui.anim
import time
from mpos import wait_for_render


class TestAnimationDeletedWidget(unittest.TestCase):
    """Test that animations don't crash when widget is deleted."""

    def setUp(self):
        """Set up test fixtures."""
        self.screen = lv.obj()
        self.screen.set_size(320, 240)
        lv.screen_load(self.screen)
        print("\n=== Animation Deletion Test Setup ===")

    def tearDown(self):
        """Clean up."""
        lv.screen_load(lv.obj())
        wait_for_render(5)
        print("=== Test Cleanup Complete ===\n")

    def test_smooth_show_with_deleted_widget(self):
        """
        Test that smooth_show doesn't crash if widget is deleted during animation.

        This reproduces the exact scenario:
        - User opens keyboard (smooth_show animation starts)
        - User presses escape (app closes, deleting all widgets)
        - Animation tries to complete on deleted widget
        """
        print("Testing smooth_show with deleted widget...")

        # Create a widget
        widget = lv.obj(self.screen)
        widget.set_size(200, 100)
        widget.center()
        widget.add_flag(lv.obj.FLAG.HIDDEN)

        # Start fade-in animation (500ms duration)
        print("Starting smooth_show animation...")
        mpos.ui.anim.smooth_show(widget)

        # Give animation time to start
        wait_for_render(2)

        # Delete the widget while animation is running (simulates app close)
        print("Deleting widget while animation is running...")
        widget.delete()

        # Process LVGL tasks - this should trigger animation callbacks
        # If not fixed, this will crash with LvReferenceError
        print("Processing LVGL tasks (animation callbacks)...")
        try:
            for _ in range(100):
                lv.task_handler()
                time.sleep(0.01)  # 1 second total to let animation complete
            print("SUCCESS: No crash when accessing deleted widget")
        except Exception as e:
            if "LvReferenceError" in str(type(e).__name__):
                self.fail(f"CRASH: Animation tried to access deleted widget: {e}")
            else:
                raise

        print("=== smooth_show deletion test PASSED ===")

    def test_smooth_hide_with_deleted_widget(self):
        """
        Test that smooth_hide doesn't crash if widget is deleted during animation.
        """
        print("Testing smooth_hide with deleted widget...")

        # Create a visible widget
        widget = lv.obj(self.screen)
        widget.set_size(200, 100)
        widget.center()
        # Start visible
        widget.remove_flag(lv.obj.FLAG.HIDDEN)

        # Start fade-out animation
        print("Starting smooth_hide animation...")
        mpos.ui.anim.smooth_hide(widget)

        # Give animation time to start
        wait_for_render(2)

        # Delete the widget while animation is running
        print("Deleting widget while animation is running...")
        widget.delete()

        # Process LVGL tasks
        print("Processing LVGL tasks (animation callbacks)...")
        try:
            for _ in range(100):
                lv.task_handler()
                time.sleep(0.01)
            print("SUCCESS: No crash when accessing deleted widget")
        except Exception as e:
            if "LvReferenceError" in str(type(e).__name__):
                self.fail(f"CRASH: Animation tried to access deleted widget: {e}")
            else:
                raise

        print("=== smooth_hide deletion test PASSED ===")

    def test_keyboard_scenario(self):
        """
        Test the exact scenario from QuasiNametag:
        1. Create keyboard with smooth_show
        2. Delete screen (simulating app close with ESC)
        3. Should not crash
        """
        print("Testing keyboard deletion scenario...")

        from mpos import MposKeyboard

        # Create textarea and keyboard (like QuasiNametag does)
        textarea = lv.textarea(self.screen)
        textarea.set_size(280, 40)
        textarea.align(lv.ALIGN.TOP_MID, 0, 10)

        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        keyboard.add_flag(lv.obj.FLAG.HIDDEN)

        # User clicks textarea - keyboard shows with animation
        print("Showing keyboard with animation...")
        mpos.ui.anim.smooth_show(keyboard)

        # Give animation time to start
        wait_for_render(2)

        # User presses ESC - app closes, screen is deleted
        print("Deleting screen (simulating app close)...")
        # Create new screen first, then delete old one
        new_screen = lv.obj()
        lv.screen_load(new_screen)
        self.screen.delete()
        self.screen = new_screen

        # Process LVGL tasks - animation callbacks should not crash
        print("Processing LVGL tasks after deletion...")
        try:
            for _ in range(100):
                lv.task_handler()
                time.sleep(0.01)
            print("SUCCESS: No crash after deleting screen with animating keyboard")
        except Exception as e:
            if "LvReferenceError" in str(type(e).__name__):
                self.fail(f"CRASH: Keyboard animation tried to access deleted widget: {e}")
            else:
                raise

        print("=== Keyboard scenario test PASSED ===")

    def test_multiple_animations_deleted(self):
        """
        Test that multiple widgets with animations can be deleted safely.
        """
        print("Testing multiple animated widgets deletion...")

        widgets = []
        for i in range(5):
            w = lv.obj(self.screen)
            w.set_size(50, 50)
            w.set_pos(i * 60, 50)
            w.add_flag(lv.obj.FLAG.HIDDEN)
            widgets.append(w)

        # Start animations on all widgets
        print("Starting animations on 5 widgets...")
        for w in widgets:
            mpos.ui.anim.smooth_show(w)

        wait_for_render(2)

        # Delete all widgets while animations are running
        print("Deleting all widgets while animations are running...")
        for w in widgets:
            w.delete()

        # Process tasks
        print("Processing LVGL tasks...")
        try:
            for _ in range(100):
                lv.task_handler()
                time.sleep(0.01)
            print("SUCCESS: No crash with multiple deleted widgets")
        except Exception as e:
            if "LvReferenceError" in str(type(e).__name__):
                self.fail(f"CRASH: Multiple animations crashed on deleted widgets: {e}")
            else:
                raise

        print("=== Multiple animations test PASSED ===")


