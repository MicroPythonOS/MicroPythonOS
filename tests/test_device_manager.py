import unittest
from mpos.device_manager import DeviceManager


class TestDeviceManager(unittest.TestCase):

    def setUp(self):
        DeviceManager._i2c_buses = []

    def test_get_bus_empty_returns_none(self):
        self.assertIsNone(DeviceManager.getBus("i2c"))

    def test_register_and_get_bus(self):
        bus = {"sda": 21, "scl": 22}
        DeviceManager.registerBus("i2c", bus)
        self.assertIs(DeviceManager.getBus("i2c"), bus)

    def test_get_bus_returns_first_registered(self):
        bus1 = {"sda": 21}
        bus2 = {"sda": 22}
        DeviceManager.registerBus("i2c", bus1)
        DeviceManager.registerBus("i2c", bus2)
        self.assertIs(DeviceManager.getBus("i2c"), bus1)

    def test_register_non_i2c_ignored(self):
        DeviceManager.registerBus("spi", "spi_bus")
        self.assertIsNone(DeviceManager.getBus("i2c"))

    def test_register_none_bus_ignored(self):
        DeviceManager.registerBus("i2c", None)
        self.assertIsNone(DeviceManager.getBus("i2c"))

    def test_get_unknown_bus_type_returns_none(self):
        DeviceManager.registerBus("i2c", {"bus": 1})
        self.assertIsNone(DeviceManager.getBus("spi"))

