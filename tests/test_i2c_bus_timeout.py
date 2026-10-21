# Tests for the I2C.Bus timeout parameter (api_drivers frozen i2c module).
import unittest
import sys


class FakePin:
    def __init__(self, number):
        self.number = number


class FakeI2C:
    def __init__(self, host, scl=None, sda=None, freq=None, timeout=None):
        self.host = host
        self.scl = scl
        self.sda = sda
        self.freq = freq
        self.timeout = timeout


def make_fake_machine():
    return type("module", (), {"I2C": FakeI2C, "Pin": FakePin})()


class TestI2CBusTimeout(unittest.TestCase):
    def _load_bus_class(self):
        """Import i2c against a fake machine module, then restore globals."""
        saved_machine = sys.modules.get("machine")
        saved_i2c = sys.modules.pop("i2c", None)
        sys.modules["machine"] = make_fake_machine()
        try:
            import i2c

            return i2c.I2C.Bus
        finally:
            sys.modules.pop("i2c", None)
            if saved_i2c is not None:
                sys.modules["i2c"] = saved_i2c
            if saved_machine is not None:
                sys.modules["machine"] = saved_machine

    def test_bus_forwards_timeout(self):
        """Bus passes an explicit timeout through to machine.I2C."""
        bus_class = self._load_bus_class()
        bus = bus_class(host=1, scl=5, sda=6, freq=400000, timeout=20000)
        self.assertEqual(bus._bus.timeout, 20000)

    def test_bus_keeps_default_timeout_when_omitted(self):
        """Bus keeps machine.I2C's default when no timeout is given."""
        bus_class = self._load_bus_class()
        bus = bus_class(host=1, scl=5, sda=6)
        self.assertIsNone(bus._bus.timeout)
