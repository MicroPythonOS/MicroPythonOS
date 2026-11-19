"""Tests for the two-thumb input path.

``TouchFingers`` turns the points a multi-point panel reports into events with
a stable finger number, and ``ThumbZones`` keeps one control state per finger
so a left thumb can walk while the right one fires.
"""

import unittest

from mpos.ui.native_input import (
    KeyHolds, ThumbZones, TouchFingers, TouchMonitor)

KEYS = {
    "left": 1, "right": 2, "up": 3, "down": 4,
    "menu": 5, "use": 6, "fire": 7,
}


class FakePanel:
    """A pointer device that reports every point, like the GT911/FT6x36."""

    def __init__(self, touches=(), rotation=0, width=240, height=320):
        self.touches = list(touches)
        self.rotation = rotation
        self.width = width
        self.height = height

    def get_touches(self):
        return self.touches

    def get_rotation(self):
        return self.rotation

    def get_width(self):
        return self.width

    def get_height(self):
        return self.height


class TestTouchFingers(unittest.TestCase):

    def setUp(self):
        self.panel = FakePanel()
        self.touches = TouchFingers(self.panel)

    def test_there_is_nothing_to_poll_without_a_multi_point_panel(self):
        idle = TouchFingers(FakePanel())
        # A single-touch controller and the SDL mouse have no get_touches().
        idle.indev = None
        self.assertFalse(idle.available)
        self.assertEqual(idle.poll(), [])

    def test_every_finger_is_pressed_in_one_poll(self):
        self.panel.touches = [(None, 30, 100), (None, 220, 180)]
        events = self.touches.poll()
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0][1:], (TouchFingers.PRESSED, 30, 100))
        self.assertEqual(events[1][1:], (TouchFingers.PRESSED, 220, 180))
        self.assertNotEqual(events[0][0], events[1][0])

    def test_a_finger_keeps_its_number_while_it_stays_down(self):
        self.panel.touches = [(None, 30, 100), (None, 220, 180)]
        first = self.touches.poll()
        left, right = first[0][0], first[1][0]

        # The driver lists the points in whatever order it read them; identity
        # comes from where they were, not from the list position.
        self.panel.touches = [(None, 224, 180), (None, 34, 100)]
        events = self.touches.poll()
        self.assertEqual(
            [(finger, phase) for finger, phase, _, _ in events],
            [(right, TouchFingers.MOVING), (left, TouchFingers.MOVING)])
        self.assertEqual(events[0][2:], (224, 180))
        self.assertEqual(events[1][2:], (34, 100))

    def test_a_still_finger_sends_nothing(self):
        self.panel.touches = [(None, 30, 100)]
        self.touches.poll()
        self.assertEqual(self.touches.poll(), [])

    def test_only_the_finger_that_lifted_is_released(self):
        self.panel.touches = [(None, 30, 100), (None, 220, 180)]
        left, right = [event[0] for event in self.touches.poll()]

        self.panel.touches = [(None, 30, 100)]
        events = self.touches.poll()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], right)
        self.assertEqual(events[0][1], TouchFingers.RELEASED)
        self.assertEqual(events[0][2:], (220, 180))

        self.panel.touches = []
        self.assertEqual(self.touches.poll()[0][0], left)

    def test_a_real_point_number_is_used_when_the_driver_has_one(self):
        self.panel.touches = [(4, 30, 100), (9, 220, 180)]
        self.assertEqual(
            [event[0] for event in self.touches.poll()], [4, 9])
        self.panel.touches = [(9, 220, 180)]
        events = self.touches.poll()
        self.assertEqual(events, [(4, TouchFingers.RELEASED, 30, 100)])

    def test_the_display_rotation_is_applied(self):
        # A 90 degree display turns the panel's (x, y) into (299 - y, x).
        self.panel.rotation = 1
        self.panel.width = 320
        self.panel.height = 240
        self.panel.touches = [(None, 10, 20)]
        self.assertEqual(
            self.touches.poll(), [(0, TouchFingers.PRESSED, 299, 10)])

    def test_reset_makes_the_next_poll_a_press(self):
        self.panel.touches = [(None, 30, 100)]
        self.touches.poll()
        self.touches.reset()
        events = self.touches.poll()
        self.assertEqual(events[0][1], TouchFingers.PRESSED)


class TestTouchMonitor(unittest.TestCase):

    def test_the_fingers_and_the_gesture_come_from_one_poll(self):
        monitor = TouchMonitor(FakePanel([(None, 30, 100), (None, 220, 180)]))
        events = monitor.poll()
        self.assertEqual(len(events), 2)
        self.assertEqual(monitor.gesture.fingers, 2)
        self.assertTrue(monitor.gesture.active)

    def test_one_finger_is_not_a_gesture(self):
        monitor = TouchMonitor(FakePanel([(None, 30, 100)]))
        self.assertEqual(len(monitor.poll()), 1)
        self.assertEqual(monitor.gesture.fingers, 1)
        self.assertFalse(monitor.gesture.active)

    def test_reset_clears_both_views(self):
        monitor = TouchMonitor(FakePanel([(None, 30, 100)]))
        monitor.poll()
        monitor.reset()
        self.assertEqual(monitor.events, [])
        self.assertEqual(monitor.gesture.fingers, 0)
        self.assertEqual(len(monitor.poll()), 1, "a reset must re-press")

    def test_a_single_point_panel_has_no_monitor(self):
        monitor = TouchMonitor(FakePanel())
        monitor.fingers.indev = None
        monitor.gesture.indev = None
        self.assertFalse(monitor.available)
        self.assertEqual(monitor.poll(), [])


class ThumbZonesTest(unittest.TestCase):

    def setUp(self):
        self.keys = []
        self.hold = KeyHolds(lambda code, pressed: self.keys.append(
            (code, pressed)))
        self.zones = ThumbZones(KEYS, self.hold)

    def test_a_left_thumb_walks_while_the_right_one_fires(self):
        self.assertEqual(self.zones.pressed(80, 100, 0), "stick")
        self.assertEqual(self.zones.pressed(240, 180, 1), "fire")
        self.assertEqual(self.keys, [(KEYS["fire"], True)])

        self.zones.moving(40, 100, 0)
        self.assertEqual(self.hold.held(), {
            KEYS["left"]: None, KEYS["fire"]: None})

        # The directional key is the one the stick owns, not the finger that
        # last touched.
        self.assertEqual(self.zones.released(40, 100, 0), "stick")
        self.assertTrue(self.hold.is_held(KEYS["fire"]))
        self.assertFalse(self.hold.is_held(KEYS["left"]))

        self.assertEqual(self.zones.released(240, 180, 1), "fire")
        self.assertEqual(self.hold.held(), {})

    def test_both_directions_of_one_finger_can_be_down(self):
        self.zones.pressed(80, 100, 0)
        self.zones.moving(60, 60, 0)
        self.assertTrue(self.hold.is_held(KEYS["left"]))
        self.assertTrue(self.hold.is_held(KEYS["up"]))

    def test_a_second_finger_cannot_steal_the_joystick(self):
        self.zones.pressed(80, 100, 0)
        self.assertIsNone(self.zones.pressed(100, 80, 1))
        self.zones.moving(40, 100, 1)
        self.assertEqual(self.hold.held(), {})

    def test_a_second_finger_in_the_same_band_is_ignored(self):
        # Two fingers in the fire band would otherwise share one key: the
        # first one to lift would release it while the other still presses.
        self.assertEqual(self.zones.pressed(240, 180, 0), "fire")
        self.assertIsNone(self.zones.pressed(250, 190, 1))

        self.assertIsNone(self.zones.released(250, 190, 1))
        self.assertTrue(self.hold.is_held(KEYS["fire"]))

        self.assertEqual(self.zones.released(240, 180, 0), "fire")
        self.assertFalse(self.hold.is_held(KEYS["fire"]))

    def test_two_fingers_in_the_menu_band_open_it_once(self):
        self.zones.pressed(240, 20, 0)
        self.zones.pressed(250, 30, 1)
        self.assertEqual(self.keys, [
            (KEYS["menu"], True), (KEYS["menu"], False)])

    def test_the_fire_band_keeps_working_after_the_other_finger_lifts(self):
        self.zones.pressed(240, 180, 0)
        self.zones.pressed(80, 100, 1)
        self.zones.moving(40, 100, 1)
        self.zones.released(40, 100, 1)
        self.assertTrue(self.hold.is_held(KEYS["fire"]))

    def test_reset_lets_go_of_every_zone(self):
        self.zones.pressed(80, 100, 0)
        self.zones.moving(40, 100, 0)
        self.zones.pressed(240, 180, 1)
        self.zones.reset()
        self.assertEqual(self.hold.held(), {})
        self.assertIsNone(self.zones.zone(0))
        self.assertIsNone(self.zones.zone(1))
