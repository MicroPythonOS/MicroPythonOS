import math
import time
import unittest

from mpos import AudioManager, DeviceInfo, LightsManager, SensorManager


class DShellHardwareTests(unittest.TestCase):
    def setUp(self):
        if DeviceInfo.get_hardware_id() != "d_shell":
            self.skipTest("D-Shell hardware required")
        from mpos.board import d_shell
        self.board = d_shell

    def test_board_and_display(self):
        self.assertEqual(DeviceInfo.get_hardware_id(), "d_shell")
        self.assertEqual(self.board.display.get_horizontal_resolution(), 240)
        self.assertEqual(self.board.display.get_vertical_resolution(), 320)
        self.assertEqual(self.board.BUFFER_SIZE, 38400)

    def test_gt911_identity(self):
        product = bytearray(4)
        self.board.touch_device.write_readinto(b"\x81\x40", product)
        self.assertEqual(bytes(product), b"911\x00")

    def test_buttons_idle(self):
        self.assertEqual(self.board.key_up.value(), 1)
        self.assertEqual(self.board.key_down.value(), 1)

    def test_qmi8658(self):
        self.assertEqual(self.board.imu_i2c.readfrom_mem(0x6A, 0, 1), b"\x05")
        sensor = SensorManager.get_default_sensor(SensorManager.TYPE_ACCELEROMETER)
        self.assertTrue(sensor is not None)
        xyz = SensorManager.read_sensor(sensor)
        self.assertEqual(len(xyz), 3)
        magnitude = math.sqrt(sum(value * value for value in xyz))
        self.assertTrue(5 < magnitude < 15)
        print("QMI8658 acceleration m/s2:", xyz)

    def test_aht20(self):
        self.assertTrue(0x38 in self.board.sensor_i2c.scan())
        self.board.sensor_i2c.writeto(0x38, b"\xac\x33\x00")
        time.sleep_ms(100)
        data = self.board.sensor_i2c.readfrom(0x38, 6)
        self.assertEqual(data[0] & 0x80, 0)
        humidity = ((data[1] << 12) | (data[2] << 4) | (data[3] >> 4)) * 100 / 1048576
        temperature = (((data[3] & 15) << 16) | (data[4] << 8) | data[5]) * 200 / 1048576 - 50
        self.assertTrue(0 <= humidity <= 100)
        self.assertTrue(-40 <= temperature <= 85)
        print("AHT20 Celsius, %RH:", temperature, humidity)

    def test_veml7700(self):
        self.assertTrue(0x10 in self.board.sensor_i2c.scan())
        self.board.sensor_i2c.writeto_mem(0x10, 0, b"\xc0\x18")
        time.sleep_ms(900)
        als = self.board.sensor_i2c.readfrom_mem(0x10, 4, 2)
        white = self.board.sensor_i2c.readfrom_mem(0x10, 5, 2)
        self.assertEqual(len(als), 2)
        print("VEML7700 raw ALS, white:", als[0] | als[1] << 8, white[0] | white[1] << 8)

    def test_ds1307(self):
        self.assertTrue(0x68 in self.board.sensor_i2c.scan())
        first = self.board.sensor_i2c.readfrom_mem(0x68, 0, 7)
        time.sleep_ms(1100)
        second = self.board.sensor_i2c.readfrom_mem(0x68, 0, 7)
        self.assertEqual(first[0] & 0x80, 0)
        self.assertTrue(first[:3] != second[:3])
        print("DS1307 BCD bytes:", list(second))

    def test_registered_outputs(self):
        self.assertTrue(LightsManager.is_available())
        self.assertEqual(LightsManager.get_led_count(), 8)
        self.assertTrue(self.board.speaker in AudioManager.get_outputs())
        self.assertTrue(self.board.buzzer in AudioManager.get_outputs())
        self.assertEqual(self.board.amp_enable.value(), 0)


if __name__ == "__main__":
    unittest.main()
