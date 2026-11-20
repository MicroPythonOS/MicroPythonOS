import math
import os
import sys
import unittest

_app_dir = os.path.join("apps", "com.micropythonos.imageview")
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)

import imageview


class FakeImage:
    def __init__(self):
        self.width = 240
        self.height = 320
        self.x = 0
        self.y = 0
        self.scale = None
        self.rotation = None
        self.offset_x = None
        self.offset_y = None

    def set_scale(self, value):
        self.scale = value

    def set_rotation(self, value):
        self.rotation = value

    def set_offset_x(self, value):
        self.offset_x = value

    def set_offset_y(self, value):
        self.offset_y = value

    def get_width(self):
        return self.width

    def get_height(self):
        return self.height

    def get_x(self):
        return self.x

    def get_y(self):
        return self.y


class FakeGesture:
    def __init__(self):
        self.center = (0.0, 0.0)
        self.scale = 1.0
        self.rotation = 0.0


class TestImageViewGestureMath(unittest.TestCase):
    def setUp(self):
        self.view = imageview.ImageView()
        self.view.image = FakeImage()
        self.view._image_w = 120
        self.view._image_h = 160
        self.view._fit_scale = 512
        self.view._zoom = 1.0
        self.view._rotation = 0
        self.view._offset_x = 0
        self.view._offset_y = 0
        self.view._applied_scale = None
        self.view._applied_rotation = None
        self.view._applied_offset_x = None
        self.view._applied_offset_y = None
        self.view._pinch_base = None
        self.view._gesture = FakeGesture()

    def _start(self, center):
        self.view._gesture.center = center
        self.view._begin_pinch()

    def _update(self, center, scale=1.0, rotation=0.0):
        self.view._gesture.center = center
        self.view._gesture.scale = scale
        self.view._gesture.rotation = rotation
        self.view._update_pinch()

    def test_zoom_around_center(self):
        self._start((120.0, 160.0))
        self._update((120.0, 160.0), scale=2.0)
        self.assertEqual(self.view._zoom, 2.0)
        self.assertTrue(abs(self.view._offset_x) < 1e-6)
        self.assertTrue(abs(self.view._offset_y) < 1e-6)
        self.assertEqual(self.view.image.scale, 1024)

    def test_zoom_keeps_finger_anchor(self):
        anchor = (60.0, 80.0)
        self._start(anchor)
        self._update(anchor, scale=2.0)
        self.assertEqual(round(self.view._offset_x), 60)
        self.assertEqual(round(self.view._offset_y), 80)
        self.assertEqual(self.view.image.offset_x, 60)
        self.assertEqual(self.view.image.offset_y, 80)

    def test_rotation_around_center(self):
        self._start((120.0, 160.0))
        self._update((120.0, 160.0), scale=2.0, rotation=math.pi / 4.0)
        self.assertEqual(self.view._rotation, 450)
        self.assertEqual(self.view._zoom, 2.0)
        self.assertTrue(abs(self.view._offset_x) < 1e-6)
        self.assertTrue(abs(self.view._offset_y) < 1e-6)
        self.assertEqual(self.view.image.rotation, 450)

    def test_rotation_is_normalized(self):
        self._start((120.0, 160.0))
        self._update((120.0, 160.0), scale=1.0, rotation=math.radians(200))
        self.assertEqual(self.view._rotation, -1600)

    def test_zoom_is_clamped(self):
        self._start((120.0, 160.0))
        self._update((120.0, 160.0), scale=10.0)
        self.assertEqual(self.view._zoom, imageview.ImageView.MAX_ZOOM)

    def test_pan_is_clamped_to_image(self):
        self._start((120.0, 160.0))
        self._update((120.0, 160.0), scale=2.0)
        self.view._pan_by(1000, 1000)
        self.assertEqual(round(self.view._offset_x), 120)
        self.assertEqual(round(self.view._offset_y), 160)

    def test_pan_at_fit_stays_centered(self):
        self.view._pan_by(50, 50)
        self.assertEqual(self.view._offset_x, 0)
        self.assertEqual(self.view._offset_y, 0)
