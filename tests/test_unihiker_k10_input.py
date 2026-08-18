import unittest

from mpos.board.unihiker_k10_input import (
    K10ButtonInput,
    create_expander_i2c,
    initialize_camera_with_recovery,
    is_direct_navigation_target,
)


class FakePin:
    def __init__(self, number):
        self.number = number


class FakeI2C:
    instances = []

    def __init__(self, bus, sda, scl, freq):
        self.args = (bus, sda.number, scl.number, freq)
        self.registers = {0x06: 0xFF, 0x07: 0x00, 0x02: 0x00}
        self.writes = []
        self.instances.append(self)

    def readfrom_mem(self, address, register, size):
        return bytes([self.registers[register]])

    def writeto_mem(self, address, register, value):
        self.registers[register] = value[0]
        self.writes.append((address, register, value[0]))


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

    def test_long_a_emits_escape_for_an_open_dropdown(self):
        self.assertEqual(
            self.input.update(True, False, 100, True, dropdown_open=True),
            (None, False, False),
        )
        self.assertEqual(
            self.input.update(True, False, 800, True, dropdown_open=True),
            ("esc", True, False),
        )
        self.assertEqual(
            self.input.update(True, False, 820, True, dropdown_open=True),
            ("esc", False, False),
        )
        self.assertEqual(
            self.input.update(False, False, 840, True, dropdown_open=True),
            (None, False, False),
        )

    def test_b_moves_to_next_widget(self):
        self.assertEqual(self.input.update(False, True, 100, False), ("next", True, False))
        self.assertEqual(self.input.update(False, False, 120, False), ("next", False, False))

    def test_b_keeps_repeating_for_normal_navigation(self):
        self.assertEqual(self.input.update(False, True, 100, False), ("next", True, False))
        self.assertEqual(self.input.update(False, True, 800, False), ("next", True, False))
        self.assertEqual(self.input.update(False, False, 820, False), ("next", False, False))

    def test_b_moves_to_next_keyboard_key(self):
        self.assertEqual(self.input.update(False, True, 100, True), ("right", True, False))
        self.assertEqual(self.input.update(False, False, 120, True), ("right", False, False))

    def test_b_uses_next_for_a_closed_dropdown(self):
        class Keyboard:
            pass

        class ButtonMatrix:
            pass

        class Dropdown:
            def is_open(self):
                return False

        direct_navigation = is_direct_navigation_target(
            Dropdown(), Keyboard, ButtonMatrix, Dropdown
        )
        self.assertFalse(direct_navigation)
        self.assertEqual(
            self.input.update(False, True, 100, direct_navigation),
            ("next", True, False),
        )

    def test_short_b_moves_to_next_open_dropdown_option(self):
        class Keyboard:
            pass

        class ButtonMatrix:
            pass

        class Dropdown:
            def is_open(self):
                return True

        direct_navigation = is_direct_navigation_target(
            Dropdown(), Keyboard, ButtonMatrix, Dropdown
        )
        self.assertTrue(direct_navigation)
        self.assertEqual(
            self.input.update(False, True, 100, direct_navigation, dropdown_open=True),
            (None, False, False),
        )
        self.assertEqual(
            self.input.update(False, False, 200, direct_navigation, dropdown_open=True),
            ("right", True, False),
        )
        self.assertEqual(
            self.input.update(False, False, 220, direct_navigation, dropdown_open=True),
            ("right", False, False),
        )

    def test_long_b_moves_to_previous_open_dropdown_option(self):
        self.assertEqual(
            self.input.update(False, True, 100, True, dropdown_open=True),
            (None, False, False),
        )
        self.assertEqual(
            self.input.update(False, True, 800, True, dropdown_open=True),
            ("left", True, False),
        )
        self.assertEqual(
            self.input.update(False, True, 820, True, dropdown_open=True),
            ("left", False, False),
        )
        self.assertEqual(
            self.input.update(False, False, 840, True, dropdown_open=True),
            (None, False, False),
        )

    def test_a_takes_priority_when_b_is_also_pressed(self):
        self.assertEqual(self.input.update(False, True, 100, False), ("next", True, False))
        self.assertEqual(self.input.update(True, True, 120, False), ("next", False, False))
        self.assertEqual(self.input.update(False, False, 200, False), ("enter", True, False))
        self.assertEqual(self.input.update(False, False, 220, False), ("enter", False, False))


class TestK10CameraInitialization(unittest.TestCase):
    def test_all_failed_attempts_restore_expander_i2c(self):
        attempts = []
        failures = []
        recoveries = []

        def init_camera():
            attempts.append(True)
            raise OSError("camera unavailable")

        result = initialize_camera_with_recovery(
            init_camera,
            lambda attempt, error: failures.append(attempt),
            lambda: recoveries.append(True),
        )

        self.assertTrue(result is None)
        self.assertEqual(len(attempts), 3)
        self.assertEqual(failures, [0, 1, 2])
        self.assertEqual(recoveries, [True])

    def test_successful_camera_attempt_does_not_restore_expander_i2c(self):
        attempts = []
        failures = []
        recoveries = []
        camera = object()

        def init_camera():
            attempts.append(True)
            if len(attempts) < 3:
                raise OSError("camera unavailable")
            return camera

        result = initialize_camera_with_recovery(
            init_camera,
            lambda attempt, error: failures.append(attempt),
            lambda: recoveries.append(True),
        )

        self.assertTrue(result is camera)
        self.assertEqual(len(attempts), 3)
        self.assertEqual(failures, [0, 1])
        self.assertEqual(recoveries, [])


class TestK10ExpanderI2C(unittest.TestCase):
    def setUp(self):
        FakeI2C.instances = []

    def test_create_expander_i2c_recreates_and_configures_bus(self):
        bus = create_expander_i2c(FakeI2C, FakePin, 47, 48)

        self.assertTrue(bus is FakeI2C.instances[0])
        self.assertEqual(bus.args, (0, 47, 48, 400000))
        self.assertEqual(
            bus.writes,
            [(0x20, 0x06, 0xFC), (0x20, 0x07, 0x10), (0x20, 0x02, 0x03)],
        )


if __name__ == "__main__":
    unittest.main()
