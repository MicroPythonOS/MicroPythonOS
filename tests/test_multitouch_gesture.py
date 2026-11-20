import math
import unittest

from mpos.ui.multitouch import MultiTouchGesture, display_to_logical


class FakeIndev:
    def __init__(self):
        self.touches = []
        self.rotation = 0
        self.width = 240
        self.height = 320

    def get_touches(self):
        return self.touches

    def get_rotation(self):
        return self.rotation

    def get_width(self):
        return self.width

    def get_height(self):
        return self.height


class TestDisplayToLogical(unittest.TestCase):
    def test_identity(self):
        self.assertEqual(display_to_logical(0, 240, 320, 10, 20), (10, 20))

    def test_rotation_90(self):
        self.assertEqual(display_to_logical(1, 320, 240, 10, 20), (299, 10))

    def test_rotation_180(self):
        self.assertEqual(display_to_logical(2, 240, 320, 10, 20), (229, 299))

    def test_rotation_270(self):
        self.assertEqual(display_to_logical(3, 320, 240, 10, 20), (20, 229))


class TestMultiTouchGesture(unittest.TestCase):
    def setUp(self):
        self.indev = FakeIndev()
        self.gesture = MultiTouchGesture(self.indev)

    def assert_close(self, actual, expected, tolerance=1e-6):
        self.assertTrue(abs(actual - expected) < tolerance, "%s != %s" % (actual, expected))

    def test_idle(self):
        self.gesture.poll()
        self.assertEqual(self.gesture.fingers, 0)
        self.assertFalse(self.gesture.active)
        self.assertTrue(self.gesture.center is None)

    def test_pinch_start_and_scale(self):
        self.indev.touches = [(0, 100, 100), (1, 140, 100)]
        self.gesture.poll()
        self.assertTrue(self.gesture.just_started)
        self.assertTrue(self.gesture.active)
        self.assertEqual(self.gesture.center, (120.0, 100.0))
        self.assert_close(self.gesture.scale, 1.0)

        self.indev.touches = [(0, 80, 100), (1, 160, 100)]
        self.gesture.poll()
        self.assert_close(self.gesture.scale, 2.0)
        self.assertEqual(self.gesture.center, (120.0, 100.0))

    def test_rotation(self):
        self.indev.touches = [(0, 100, 100), (1, 140, 100)]
        self.gesture.poll()
        self.indev.touches = [(0, 120, 80), (1, 120, 120)]
        self.gesture.poll()
        self.assert_close(self.gesture.rotation, math.pi / 2.0)

    def test_finger_order_with_ids(self):
        self.indev.touches = [(1, 100, 100), (0, 140, 100)]
        self.gesture.poll()
        self.assert_close(self.gesture.scale, 1.0)
        self.indev.touches = [(0, 140, 100), (1, 100, 100)]
        self.gesture.poll()
        self.assert_close(self.gesture.scale, 1.0)

    def test_a_record_swap_is_not_a_half_turn(self):
        # The FT6x36 numbers its records by touch order, so the same two
        # fingers can come back with the records exchanged. Follow the points,
        # not the numbers, or the pair looks like it turned 180 degrees.
        self.indev.touches = [(0, 100, 100), (1, 140, 100)]
        self.gesture.poll()
        self.indev.touches = [(0, 140, 100), (1, 100, 100)]
        self.gesture.poll()
        self.assert_close(self.gesture.scale, 1.0)
        self.assert_close(self.gesture.rotation, 0.0)

    def test_finger_order_without_ids(self):
        self.indev.touches = [(None, 100, 100), (None, 140, 100)]
        self.gesture.poll()
        self.assert_close(self.gesture.scale, 1.0)
        self.indev.touches = [(None, 140, 100), (None, 100, 100)]
        self.gesture.poll()
        self.assert_close(self.gesture.scale, 1.0)

    def test_pair_stays_when_third_finger_lands(self):
        self.indev.touches = [(1, 100, 100), (2, 140, 100)]
        self.gesture.poll()
        self.assert_close(self.gesture.scale, 1.0)
        self.indev.touches = [(0, 120, 60), (1, 100, 100), (2, 140, 100)]
        self.gesture.poll()
        self.assert_close(self.gesture.scale, 1.0)

    def test_fingers_too_close_then_spread(self):
        self.indev.touches = [(0, 100, 100), (1, 105, 100)]
        self.gesture.poll()
        self.assertFalse(self.gesture.active)
        self.assertFalse(self.gesture.just_started)
        self.indev.touches = [(0, 100, 100), (1, 120, 100)]
        self.gesture.poll()
        self.assertTrue(self.gesture.active)
        self.assertTrue(self.gesture.just_started)

    def test_one_finger_pan_delta(self):
        self.indev.touches = [(0, 100, 100)]
        self.gesture.poll()
        self.assertEqual(self.gesture.center, (100, 100))
        self.indev.touches = [(0, 120, 90)]
        self.gesture.poll()
        self.assertEqual(self.gesture.delta_x, 20)
        self.assertEqual(self.gesture.delta_y, -10)

    def test_end(self):
        self.indev.touches = [(0, 100, 100), (1, 140, 100)]
        self.gesture.poll()
        self.indev.touches = [(0, 100, 100)]
        self.gesture.poll()
        self.assertTrue(self.gesture.just_ended)
        self.assertFalse(self.gesture.active)
        self.assertEqual(self.gesture.fingers, 1)

    def test_rotation_transform_applied_to_points(self):
        self.indev.rotation = 1
        self.indev.width = 320
        self.indev.height = 240
        self.indev.touches = [(0, 10, 20), (1, 10, 70)]
        self.gesture.poll()
        self.assertTrue(self.gesture.active)
        self.assertEqual(self.gesture.points[0], (299, 10))
        self.assertEqual(self.gesture.points[1], (249, 10))
