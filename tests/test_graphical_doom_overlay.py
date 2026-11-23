"""Tests for Doom's touch-zone overlay.

The overlay is app-owned drawing, so these pin the app-side contract: it uses
the zones' own layout values, it is placed through the activity's game->panel
transform (letterboxed and rotated), and it never takes the pointer away from
the zones.
"""

import sys
import unittest

import lvgl as lv

from mpos.ui.native_activity import NativeActivity
from mpos.ui.native_input import ThumbZones

APP_DIR = "apps/com.micropythonos.doom"
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import doom  # noqa: E402
from doom_overlay import TouchOverlay  # noqa: E402


class _Surface:
    def __init__(self, width, height, panel=(240, 320)):
        self.width = width
        self.height = height
        self._image_x = (panel[0] - width) // 2
        self._image_y = (panel[1] - height) // 2


class _StubActivity(NativeActivity):
    def make_engine(self):
        return None


class TestTouchOverlay(unittest.TestCase):

    def setUp(self):
        self.screen = lv.obj()
        self.screen.set_size(240, 320)
        self.activity = _StubActivity()
        self.activity.screen = self.screen
        self.zones = ThumbZones({})
        self.overlays = []

    def tearDown(self):
        for overlay in self.overlays:
            for obj in overlay._objects:
                try:
                    obj.delete()
                except Exception:
                    pass
            overlay._objects = []
        self.screen.delete()

    def _overlay(self, width, height, rotated, panel=(240, 320)):
        self.screen.set_size(panel[0], panel[1])
        self.activity._surface = _Surface(width, height, panel)
        self.activity._rotated = rotated
        overlay = TouchOverlay(
            self.activity, self.zones, doom.GAME_WIDTH, doom.GAME_HEIGHT)
        self.overlays.append(overlay)
        # set_pos()/set_size() store style values; LVGL publishes the coords
        # (what get_x()/get_width() report) on the next layout pass.
        self.screen.update_layout()
        return overlay

    def _rect_at(self, overlay, index):
        return overlay._objects[index]

    def test_the_outlines_use_the_zone_layout(self):
        overlay = self._overlay(200, 320, True)
        stick = self.zones.stick_width
        menu = self.zones.menu_bottom
        use = self.zones.use_bottom
        expected = (
            (0, 0, stick, doom.GAME_HEIGHT),
            (stick, 0, doom.GAME_WIDTH - stick, menu),
            (stick, menu, doom.GAME_WIDTH - stick, use - menu),
            (stick, use, doom.GAME_WIDTH - stick, doom.GAME_HEIGHT - use),
        )
        self.assertEqual(len(overlay._objects), 8)
        for index, region in enumerate(expected):
            rect = self._rect_at(overlay, index)
            panel = self.activity.game_rect_to_panel(*region)
            self.assertEqual(
                (rect.get_x(), rect.get_y(),
                 rect.get_width(), rect.get_height()),
                panel, "outline %d does not match its zone" % index)

    def test_every_label_sits_at_its_zone_point(self):
        overlay = self._overlay(200, 320, True)
        labels = overlay._objects[4:]
        self.assertEqual(
            [label.get_text() for label in labels],
            ["TURN/WALK", "MENU", "OPEN/USE", "FIRE/ENTER"])

        stick = self.zones.stick_width
        points = (
            (stick // 2, doom.GAME_HEIGHT // 2),
            (stick + (doom.GAME_WIDTH - stick) // 2, self.zones.menu_bottom // 2),
            (stick + (doom.GAME_WIDTH - stick) // 2,
             (self.zones.menu_bottom + self.zones.use_bottom) // 2),
            (stick + (doom.GAME_WIDTH - stick) // 2,
             (self.zones.use_bottom + doom.GAME_HEIGHT) // 2),
        )
        for label, point in zip(labels, points):
            panel_x, panel_y = self.activity.game_to_panel(*point)
            centre_x = label.get_x() + label.get_width() // 2
            centre_y = label.get_y() + label.get_height() // 2
            self.assertTrue(abs(centre_x - panel_x) <= 1,
                            "symbol x %d != %d" % (centre_x, panel_x))
            self.assertTrue(abs(centre_y - panel_y) <= 1,
                            "symbol y %d != %d" % (centre_y, panel_y))

    def test_nothing_is_clickable(self):
        overlay = self._overlay(200, 320, True)
        for obj in overlay._objects:
            self.assertFalse(
                obj.has_flag(lv.obj.FLAG.CLICKABLE),
                "the overlay would steal a touch from the zones")

    def test_an_unrotated_surface_keeps_the_rect_unswapped(self):
        overlay = self._overlay(320, 200, False, panel=(320, 240))
        rect = self._rect_at(overlay, 0)
        panel = self.activity.game_rect_to_panel(0, 0, 160, 200)
        self.assertEqual(
            (rect.get_x(), rect.get_y(), rect.get_width(), rect.get_height()),
            panel)
        self.assertEqual(rect.get_width(), 160)
        self.assertEqual(rect.get_height(), 200)

    def test_visibility_toggles_every_object(self):
        overlay = self._overlay(200, 320, True)
        overlay.set_visible(False)
        for obj in overlay._objects:
            self.assertTrue(obj.has_flag(lv.obj.FLAG.HIDDEN))
        overlay.set_visible(True)
        for obj in overlay._objects:
            self.assertFalse(obj.has_flag(lv.obj.FLAG.HIDDEN))
