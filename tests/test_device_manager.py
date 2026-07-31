import unittest
from mpos.device_manager import DeviceManager


class TestDeviceManager(unittest.TestCase):

    def setUp(self):
        DeviceManager._i2c_buses = []

    def test_register_bus_adds_to_list(self):
        bus = object()
        DeviceManager.registerBus("i2c", i2c_bus=bus)
        self.assertEqual(len(DeviceManager._i2c_buses), 1)
        self.assertIs(DeviceManager._i2c_buses[0], bus)

    def test_register_bus_ignores_non_i2c(self):
        bus = object()
        DeviceManager.registerBus("spi", i2c_bus=bus)
        self.assertEqual(len(DeviceManager._i2c_buses), 0)

    def test_register_bus_ignores_none_bus(self):
        DeviceManager.registerBus("i2c", i2c_bus=None)
        self.assertEqual(len(DeviceManager._i2c_buses), 0)

    def test_get_bus_returns_first(self):
        bus1 = object()
        bus2 = object()
        DeviceManager.registerBus("i2c", i2c_bus=bus1)
        DeviceManager.registerBus("i2c", i2c_bus=bus2)
        self.assertIs(DeviceManager.getBus(), bus1)

    def test_get_bus_returns_none_when_empty(self):
        self.assertIsNone(DeviceManager.getBus())

    def test_get_bus_returns_none_for_non_i2c(self):
        bus = object()
        DeviceManager.registerBus("i2c", i2c_bus=bus)
        self.assertIsNone(DeviceManager.getBus("spi"))
