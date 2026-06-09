"""
Graphical tests for focus_direction layer_top / modal-overlay behaviour.

Covers the scenario where a confirmation dialog (lv.obj on lv.layer_top())
appears while a normal-screen widget has focus — e.g. the memory game or
lights-out game showing a "New game?" popup.

Expected behaviour (Android-style "first keypress redirects"):
  1. Normal-screen widgets are focused before overlay appears.
  2. Overlay appears (buttons added to focus group on layer_top).
  3. User presses a directional key.
  4. On that FIRST keypress, focus jumps to the overlay — it does NOT stay
     on the normal screen and does NOT do directional navigation on the screen.
  5. Subsequent keypresses navigate within the overlay only.
  6. Once the overlay is removed, focus returns to normal-screen navigation.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_focus_layer_top.py
    Device:  ./tests/unittest.sh tests/test_graphical_focus_layer_top.py --ondevice
"""

import time
import unittest
import lvgl as lv
import mpos.ui
from mpos import wait_for_widget

from mpos.ui.focus_direction import (
    _is_on_layer_top,
    _first_focusable_on_layer_top,
    move_focus_direction,
    UP, DOWN, LEFT, RIGHT,
)
from mpos.ui.testing import GraphicalTestCase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wait_ms(ms):
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < ms:
        lv.task_handler()
        time.sleep(0.01)


def _focused_obj():
    group = lv.group_get_default()
    return group.get_focused() if group else None


def _move(angle):
    move_focus_direction(angle)
    _wait_ms(50)


def _move_until_focused(angle, target, attempts=3):
    for _ in range(attempts):
        _move(angle)
        focused = wait_for_widget(
            lambda: target if _focused_obj() is target else None,
            timeout=0.6,
            interval=0.05,
        )
        if focused is not None:
            return True
    return False


# ---------------------------------------------------------------------------

class TestLayerTopDetection(GraphicalTestCase):
    """Unit-level tests for _is_on_layer_top and _first_focusable_on_layer_top."""

    def test_normal_widget_not_on_layer_top(self):
        """A button on a normal screen is not on layer_top."""
        btn = lv.button(self.screen)
        lbl = lv.label(btn)
        lbl.set_text("Normal")
        self.assertFalse(_is_on_layer_top(btn))

    def test_widget_on_layer_top_detected(self):
        """A button parented directly to layer_top is detected."""
        overlay = lv.obj(lv.layer_top())
        btn = lv.button(overlay)
        lbl = lv.label(btn)
        lbl.set_text("Overlay")
        try:
            self.assertTrue(_is_on_layer_top(btn))
            self.assertTrue(_is_on_layer_top(overlay))
        finally:
            overlay.delete()

    def test_no_focusable_on_layer_top_returns_none(self):
        """When layer_top has no focusable group members, returns None."""
        group = lv.group_get_default()
        # Add a normal button — should not be on layer_top
        btn = lv.button(self.screen)
        lbl = lv.label(btn)
        lbl.set_text("Screen btn")
        self.wait_for_render()
        self.assertIsNone(_first_focusable_on_layer_top(group))

    def test_focusable_on_layer_top_returned(self):
        """When a focus-group member lives on layer_top, it is returned."""
        group = lv.group_get_default()
        overlay = lv.obj(lv.layer_top())
        overlay_btn = lv.button(overlay)
        lbl = lv.label(overlay_btn)
        lbl.set_text("Yes")
        self.wait_for_render()
        try:
            result = _first_focusable_on_layer_top(group)
            self.assertIsNotNone(result, "Should find focusable button on layer_top")
            self.assertIs(result, overlay_btn)
        finally:
            overlay.delete()

    def test_hidden_overlay_button_not_returned(self):
        """A hidden button on layer_top does not count as active modal content."""
        group = lv.group_get_default()
        overlay = lv.obj(lv.layer_top())
        overlay_btn = lv.button(overlay)
        overlay_btn.add_flag(lv.obj.FLAG.HIDDEN)
        lbl = lv.label(overlay_btn)
        lbl.set_text("Hidden")
        self.wait_for_render()
        try:
            self.assertIsNone(_first_focusable_on_layer_top(group))
        finally:
            overlay.delete()


class TestModalOverlayFocusRedirect(GraphicalTestCase):
    """Verify that move_focus_direction redirects to layer_top on first keypress."""

    def _make_screen_button(self, text):
        btn = lv.button(self.screen)
        lbl = lv.label(btn)
        lbl.set_text(text)
        btn.set_size(100, 40)
        return btn

    def _make_overlay_button(self, parent, text):
        btn = lv.button(parent)
        lbl = lv.label(btn)
        lbl.set_text(text)
        btn.set_size(80, 35)
        return btn

    def test_first_keypress_redirects_to_overlay(self):
        """When overlay appears, the first directional key jumps focus to it."""
        # Set up normal screen with a button that has focus
        screen_btn = self._make_screen_button("Game board")
        self.wait_for_render()
        lv.group_focus_obj(screen_btn)
        _wait_ms(50)
        self.assertIs(_focused_obj(), screen_btn, "screen_btn should start focused")

        # Simulate overlay appearing (confirmation dialog on layer_top)
        overlay = lv.obj(lv.layer_top())
        overlay.set_size(200, 100)
        overlay.center()
        yes_btn = self._make_overlay_button(overlay, "Yes")
        no_btn  = self._make_overlay_button(overlay, "No")
        yes_btn.align(lv.ALIGN.BOTTOM_LEFT,  10, -10)
        no_btn.align(lv.ALIGN.BOTTOM_RIGHT, -10, -10)
        self.wait_for_render()

        try:
            # Focus is still on screen_btn — overlay just appeared
            self.assertIs(_focused_obj(), screen_btn)

            # First directional keypress must redirect to the overlay, not navigate screen
            _move(UP)

            focused = _focused_obj()
            self.assertIsNotNone(focused, "Something should be focused after first keypress")
            self.assertTrue(
                _is_on_layer_top(focused),
                "After first keypress with overlay present, focus must be on layer_top, "
                "got: " + str(focused)
            )
            # Specifically it should be the first focusable overlay widget
            self.assertIs(focused, yes_btn,
                          "Focus should land on yes_btn (first in focus group on layer_top)")
        finally:
            overlay.delete()
            _wait_ms(50)

    def test_navigation_stays_within_overlay(self):
        """Directional navigation after redirect stays within the overlay."""
        screen_btn = self._make_screen_button("Screen")
        self.wait_for_render()
        lv.group_focus_obj(screen_btn)

        overlay = lv.obj(lv.layer_top())
        overlay.set_size(300, 60)
        overlay.center()
        yes_btn = self._make_overlay_button(overlay, "Yes")
        no_btn  = self._make_overlay_button(overlay, "No")
        yes_btn.set_pos(10, 10)
        no_btn.set_pos(160, 10)
        self.wait_for_render()

        try:
            # First key redirects to overlay
            _move(DOWN)
            self.assertTrue(_is_on_layer_top(_focused_obj()),
                            "Focus should be on overlay after first key")

            # Navigate within overlay: yes_btn is left of no_btn
            lv.group_focus_obj(yes_btn)
            _wait_ms(50)
            _move(RIGHT)

            focused = _focused_obj()
            self.assertIs(focused, no_btn,
                          "RIGHT from yes_btn should reach no_btn within overlay")

            # And pressing LEFT from no_btn goes back to yes_btn
            _move(LEFT)
            self.assertIs(_focused_obj(), yes_btn,
                          "LEFT from no_btn should return to yes_btn")

            # Normal screen is not reachable while overlay is active
            _move(DOWN)  # screen_btn is below overlay in y — but must not be reached
            self.assertTrue(_is_on_layer_top(_focused_obj()),
                            "Focus must not escape overlay to normal screen")
        finally:
            overlay.delete()
            _wait_ms(50)

    def test_normal_navigation_resumes_after_overlay_closed(self):
        """Once the overlay is removed, directional navigation works on the screen again."""
        btn_a = self._make_screen_button("A")
        btn_b = self._make_screen_button("B")
        btn_a.set_pos(10, 50)
        btn_b.set_pos(10, 150)
        self.wait_for_render()

        # Show overlay, redirect focus, then close it
        overlay = lv.obj(lv.layer_top())
        overlay.set_size(150, 60)
        overlay.center()
        overlay_btn = self._make_overlay_button(overlay, "OK")
        self.wait_for_render()

        lv.group_focus_obj(btn_a)
        _wait_ms(50)
        _move(DOWN)  # redirects to overlay
        self.assertTrue(_is_on_layer_top(_focused_obj()))

        # Close overlay — focus is now dangling (overlay deleted)
        overlay.delete()
        _wait_ms(100)

        # Return focus to a screen widget
        lv.group_focus_obj(btn_a)
        _wait_ms(50)
        focused_btn_a = wait_for_widget(
            lambda: btn_a if _focused_obj() is btn_a else None,
            timeout=1.5,
            interval=0.05,
        )
        self.assertIsNotNone(focused_btn_a, "btn_a should regain focus after overlay close")

        # Normal directional navigation should work again
        self.assertTrue(
            _move_until_focused(DOWN, btn_b),
            "After overlay is closed, DOWN from btn_a should reach btn_b",
        )
