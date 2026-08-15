import unittest

from mpos.board.unihiker_k10_input import K10ButtonInput


class TestK10ButtonInput(unittest.TestCase):
    def setUp(self):
        self.input = K10ButtonInput(long_press_ms=700)

    def test_short_a_emits_enter_on_release(self):
        self.assertEqual(self.input.update(True, False, 100, False), (None, False, False))
        self.assertEqual(self.input.update(False, False, 200, False), ("enter", True, False))
        self.assertEqual(self.input.update(False, False, 220, False), ("enter", False, False))

    def test_long_a_emits_back_without_enter(self):
        self.assertEqual(self.input.update(True, False, 100, False), (None, False, False))
        self.assertEqual(self.input.update(True, False, 800, False), (None, False, True))
        self.assertEqual(self.input.update(False, False, 820, False), (None, False, False))

    def test_b_moves_to_next_widget(self):
        self.assertEqual(self.input.update(False, True, 100, False), ("next", True, False))
        self.assertEqual(self.input.update(False, False, 120, False), ("next", False, False))

    def test_b_moves_to_next_keyboard_key(self):
        self.assertEqual(self.input.update(False, True, 100, True), ("right", True, False))
        self.assertEqual(self.input.update(False, False, 120, True), ("right", False, False))

    def test_a_takes_priority_when_b_is_also_pressed(self):
        self.assertEqual(self.input.update(False, True, 100, False), ("next", True, False))
        self.assertEqual(self.input.update(True, True, 120, False), ("next", False, False))
        self.assertEqual(self.input.update(False, False, 200, False), ("enter", True, False))
        self.assertEqual(self.input.update(False, False, 220, False), ("enter", False, False))


if __name__ == "__main__":
    unittest.main()
