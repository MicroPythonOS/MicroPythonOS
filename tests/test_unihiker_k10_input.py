import unittest

from mpos.board.unihiker_k10_input import K10ButtonInput, create_expander_i2c


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
