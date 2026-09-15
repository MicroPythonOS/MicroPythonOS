import lvgl as lv

from drivers.indev.usb_hid import _CURSOR_H, _CURSOR_W, _cursor_map, FakeHIDSource, USBMouse
from mpos.ui.appearance_manager import AppearanceManager
from mpos.ui.testing import GraphicalTestCase


class TestUSBMouse(GraphicalTestCase):
    def setUp(self):
        super().setUp()
        self.source = FakeHIDSource()
        self.mouse = USBMouse(source=self.source)
        self.addCleanup(self.mouse.delete)

    def test_starts_at_display_center(self):
        self.assertEqual(
            (self.mouse._x, self.mouse._y),
            (self.mouse._width // 2, self.mouse._height // 2),
        )

    def test_movement_accumulates(self):
        self.source.inject_mouse(dx=10, dy=-4)
        state, x, y = self.mouse._get_coords()
        self.assertEqual((x, y), (self.mouse._width // 2 + 10, self.mouse._height // 2 - 4))
        self.assertEqual(state, lv.INDEV_STATE.RELEASED)

    def test_position_clamps_at_edges(self):
        for _ in range(10):
            self.source.inject_mouse(dx=127, dy=127)
        _, x, y = self.mouse._get_coords()
        self.assertEqual((x, y), (self.mouse._width - 1, self.mouse._height - 1))
        for _ in range(10):
            self.source.inject_mouse(dx=-128, dy=-128)
        _, x, y = self.mouse._get_coords()
        self.assertEqual((x, y), (0, 0))

    def test_button_press_latches_until_release(self):
        self.source.inject_mouse(buttons=1)
        state, _, _ = self.mouse._get_coords()
        self.assertEqual(state, lv.INDEV_STATE.PRESSED)
        state, _, _ = self.mouse._get_coords()
        self.assertEqual(state, lv.INDEV_STATE.PRESSED)
        self.source.inject_mouse(buttons=0)
        state, _, _ = self.mouse._get_coords()
        self.assertEqual(state, lv.INDEV_STATE.RELEASED)

    def test_coords_are_absolute(self):
        self.assertTrue(USBMouse.__usb_absolute__)
        self.assertEqual(self.mouse._calc_coords(123, 45), (123, 45))

    def test_click_reaches_button(self):
        clicked = []
        btn = lv.button(self.screen)
        btn.set_size(80, 40)
        btn.center()
        btn.add_event_cb(lambda e: clicked.append(True), lv.EVENT.CLICKED, None)
        self.wait_for_render()
        area = lv.area_t()
        btn.get_coords(area)
        cx = (area.x1 + area.x2) // 2
        cy = (area.y1 + area.y2) // 2
        self.source.inject_mouse(dx=cx - self.mouse._x, dy=cy - self.mouse._y)
        self.mouse.read()
        self.wait_for_render()
        self.source.inject_mouse(buttons=1)
        self.mouse.read()
        self.wait_for_render()
        self.source.inject_mouse(buttons=0)
        self.mouse.read()
        self.wait_for_render()
        self.assertTrue(clicked)

    def test_cursor_attaches_above_ui(self):
        disp = lv.display_get_default()
        before = disp.get_layer_sys().get_child_count()
        self.mouse.attach_cursor()
        self.assertIsNotNone(self.mouse._cursor)
        after = disp.get_layer_sys().get_child_count()
        self.assertEqual(after, before + 1)
        self.assertEqual(self.screen.get_child_count(), 0)

    def test_cursor_is_arrow_shaped(self):
        def alpha(x, y):
            return _cursor_map()[(y * _CURSOR_W + x) * 4 + 3]

        self.assertEqual((_CURSOR_W, _CURSOR_H), (16, 16))
        self.assertEqual(alpha(0, 0), 255)
        self.assertEqual(alpha(15, 0), 0)
        self.assertEqual(alpha(15, 15), 0)
        self.assertEqual(alpha(0, 12), 255)
        self.assertEqual(alpha(12, 12), 0)

    def test_wheel_does_not_crash(self):
        target = lv.obj(self.screen)
        target.set_size(300, 200)
        self.source.inject_mouse(wheel=1)
        self.mouse.read()
        self.wait_for_render()
        self.source.inject_mouse(wheel=-1)
        self.mouse.read()
        self.wait_for_render()

    def _cursor_rgb(self):
        c = self.mouse._cursor.get_style_image_recolor(0)
        return (c.red, c.green, c.blue)

    def test_cursor_is_black_in_light_theme(self):
        self.assertTrue(AppearanceManager.is_light_mode())
        self.mouse.attach_cursor()
        self.assertEqual(self.mouse._cursor_theme, "black")
        self.assertEqual(self._cursor_rgb(), (0, 0, 0))

    def test_cursor_follows_theme_switch(self):
        prev = AppearanceManager._is_light_mode
        self.addCleanup(setattr, AppearanceManager, "_is_light_mode", prev)
        self.mouse.attach_cursor()
        AppearanceManager._is_light_mode = False
        self.mouse._get_coords()
        self.assertEqual(self.mouse._cursor_theme, "white")
        self.assertEqual(self._cursor_rgb(), (255, 255, 255))
        AppearanceManager._is_light_mode = True
        self.mouse._get_coords()
        self.assertEqual(self.mouse._cursor_theme, "black")
        self.assertEqual(self._cursor_rgb(), (0, 0, 0))
