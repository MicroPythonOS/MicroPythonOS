"""
Unit test for mpos.ui.focus deferred focus borders.

A focus border highlights which widget directional (keypad/joystick) focus is
on. It must not be drawn until the user actually navigates by direction, so a
touch-only UI (widgets focused by tapping) never shows a stray ring. Borders
are enabled on the first move_focus_direction() via enable_focus_borders();
_focus_border_handler() is a no-op until then.

Usage:
"""

import unittest

from mpos.ui import focus


class _FakeTarget:
    def __init__(self):
        self.border_widths = []

    def set_style_border_color(self, *a):
        pass

    def set_style_border_width(self, w, *a):
        self.border_widths.append(w)

    def set_style_border_opa(self, *a):
        pass

    def set_style_radius(self, *a):
        pass

    def scroll_to_view(self, *a):
        pass


class _FakeEvent:
    def __init__(self, target):
        self._target = target

    def get_target_obj(self):
        return self._target


class TestDeferredFocusBorder(unittest.TestCase):
    def setUp(self):
        self._orig = focus._focus_nav_active
        focus._focus_nav_active = False

    def tearDown(self):
        focus._focus_nav_active = self._orig

    def test_no_border_before_directional_nav(self):
        t = _FakeTarget()
        focus._focus_border_handler(_FakeEvent(t), 1, None, None, None)
        self.assertEqual(
            t.border_widths, [],
            "no border should be drawn before directional navigation",
        )

    def test_border_after_enable(self):
        focus.enable_focus_borders()
        t = _FakeTarget()
        focus._focus_border_handler(_FakeEvent(t), 2, None, None, None)
        self.assertEqual(
            t.border_widths, [2],
            "border should be drawn once focus navigation is enabled",
        )


if __name__ == "__main__":
    unittest.main()
