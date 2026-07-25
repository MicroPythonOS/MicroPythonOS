import unittest
from mpos.device_info import DeviceInfo


class TestDeviceInfo(unittest.TestCase):

    def setUp(self):
        DeviceInfo.hardware_id = "missing-hardware-info"

    def test_default_hardware_id(self):
        self.assertEqual(DeviceInfo.get_hardware_id(), "missing-hardware-info")

    def test_set_and_get_hardware_id(self):
        DeviceInfo.set_hardware_id("m5stack_core2")
        self.assertEqual(DeviceInfo.get_hardware_id(), "m5stack_core2")

    def test_overwrite_hardware_id(self):
        DeviceInfo.set_hardware_id("first")
        self.assertEqual(DeviceInfo.get_hardware_id(), "first")
        DeviceInfo.set_hardware_id("second")
        self.assertEqual(DeviceInfo.get_hardware_id(), "second")

