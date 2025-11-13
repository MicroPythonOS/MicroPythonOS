import unittest

from mpos import App, PackageManager

from camera import Camera, GrabMode, PixelFormat, FrameSize, GainCeiling

class TestCompareVersions(unittest.TestCase):

    def init_cam(self):
        try:
            cam = Camera(data_pins=[12,13,15,11,14,10,7,2],vsync_pin=6,href_pin=4,sda_pin=21,scl_pin=16,pclk_pin=9,xclk_pin=8,xclk_freq=20000000,pixel_format=PixelFormat.RGB565,powerdown_pin=-1,reset_pin=-1,frame_size=FrameSize.R240X240,grab_mode=GrabMode.LATEST)
            return cam
        except Exception as e:
            #self.assertTrue(False, f"camera init received exception: {e}")
            print(f"camera init received exception: {e}")
            return None

    def test_init_capture_deinit(self):
        cam = self.init_cam()
        self.assertTrue(cam is not None, "camera failed to initialize")
        self.assertEqual(cam.get_pixel_height(), 240, "wrong pixel height")
        self.assertEqual(cam.get_pixel_width(), 240, "wrong pixel width")
        memview = cam.capture()
        self.assertEqual(len(memview), 2 * 240 * 240, "capture size does not match expectations")
        cam.deinit()

    def disabled_test_multiple_runs(self):
        for _ in range(10):
            self.test_init_capture_deinit()

    def disabled_test_init_capture_deinit_poweroff(self):
        self.test_init_capture_deinit()
        from machine import Pin, I2C
        i2c = I2C(1, scl=Pin(16), sda=Pin(21), freq=100000)  # Adjust pins and frequency
        devices = i2c.scan()
        print([hex(addr) for addr in devices]) # finds it on 60 = 0x3C after init
        camera_addr = 0x3C # for OV5640
        reg_addr = 0x3008
        reg_high = (reg_addr >> 8) & 0xFF  # 0x30
        reg_low = reg_addr & 0xFF         # 0x08
        power_off_command = 0x40 # Power off command Bit[6]: Software power down
        #i2c.writeto(camera_addr, bytes([reg_high, reg_low, power_off_command]))
        print("\nSecond capture will fail!")
        self.test_init_capture_deinit()

    def test_init_twice_capture_deinit_poweroff(self):
        self.test_init_capture_deinit()
        from machine import Pin, I2C
        i2c = I2C(1, scl=Pin(16), sda=Pin(21), freq=100000)  # Adjust pins and frequency
        devices = i2c.scan()
        print([hex(addr) for addr in devices]) # finds it on 60 = 0x3C after init
        camera_addr = 0x3C # for OV5640
        reg_addr = 0x3008
        reg_high = (reg_addr >> 8) & 0xFF  # 0x30
        reg_low = reg_addr & 0xFF         # 0x08
        power_off_command = 0x40 # Power off command Bit[6]: Software power down
        #i2c.writeto(camera_addr, bytes([reg_high, reg_low, power_off_command]))
        cam = self.init_cam()
        self.assertTrue(cam is None, "expected camera to fail after i2c")
        print("\nSecond capture should now work!")
        self.test_init_capture_deinit()

