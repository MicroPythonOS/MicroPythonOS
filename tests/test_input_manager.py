import unittest

from mpos.ui.input_manager import InputManager


class TestInputManagerHapticFeedback(unittest.TestCase):

    def setUp(self):
        InputManager._has_haptic_feedback = False

    def test_has_haptic_feedback_initially_false(self):
        self.assertFalse(InputManager.has_haptic_feedback())

    def test_has_haptic_feedback_after_set_touch_feedback_cb(self):
        InputManager.set_touch_feedback_cb(lambda e: None)
        self.assertTrue(InputManager.has_haptic_feedback())

    def test_has_haptic_feedback_stays_true_after_multiple_calls(self):
        InputManager.set_touch_feedback_cb(lambda e: None)
        InputManager.set_touch_feedback_cb(lambda e: None)
        self.assertTrue(InputManager.has_haptic_feedback())


if __name__ == "__main__":
    unittest.main()
