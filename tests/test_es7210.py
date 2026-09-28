"""Unit tests for the ES7210 microphone ADC driver (CPython, no hardware).

Verifies that configure() writes the exact register sequence from the vendor
reference driver (Waveshare ESP32-S3-Touch-LCD-1.54 Arduino demo, 10_esp_sr
example es7210.cpp, which mirrors the Espressif esp_codec_dev driver).
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "internal_filesystem", "lib", "drivers", "codec"))

import es7210  # noqa: E402


class FakeI2C:
    """Records writeto_mem calls so the register sequence can be asserted."""

    def __init__(self):
        self.written = []

    def writeto_mem(self, addr, reg, data):
        assert addr == es7210.I2C_ADDR
        self.written.append((reg, data[0]))

    def readfrom_mem_into(self, addr, reg, buf):
        buf[0] = 0


class ES7210Tests(unittest.TestCase):
    def setUp(self):
        self.i2c = FakeI2C()
        self.codec = es7210.ES7210(self.i2c)

    def test_configure_16k_registers(self):
        """MCLK = 16000 x 256 = 4.096 MHz: coeff entry
        (adc_div=0x01, dll=0x01, doubler=0x01, osr=0x20, lrck 0x01/0x00)."""
        self.codec.configure(sample_rate_hz=16000, mclk_ratio=256, gain_db=30)
        regs = dict(self.i2c.written)

        self.assertEqual(regs[0x00], 0x41)  # ends enabled
        self.assertIn((0x00, 0xFF), self.i2c.written)  # reset performed
        self.assertEqual(regs[0x11], 0x60)  # 16-bit, normal I2S
        self.assertEqual(regs[0x12], 0x00)  # no TDM
        self.assertEqual(regs[0x07], 0x20)  # OSR
        # REG02 = adc_div | doubler << 6 | dll << 7
        self.assertEqual(regs[0x02], 0x01 | (0x01 << 6) | (0x01 << 7))
        self.assertEqual(regs[0x04], 0x01)  # LRCK divider high
        self.assertEqual(regs[0x05], 0x00)  # LRCK divider low
        self.assertEqual(regs[0x40], 0xC3)  # analog power / VMID
        self.assertEqual(regs[0x41], 0x70)  # mic bias 2.87 V
        self.assertEqual(regs[0x43], 10 | 0x10)  # MIC1 PGA 30 dB
        self.assertEqual(regs[0x46], 10 | 0x10)  # MIC4 PGA 30 dB
        self.assertEqual(regs[0x47], 0x08)  # MIC1 power on
        self.assertEqual(regs[0x4B], 0x0F)  # MIC1/2 bias+ADC+PGA power
        self.assertEqual(regs[0x4C], 0x0F)  # MIC3/4 bias+ADC+PGA power
        self.assertEqual(regs[0x06], 0x04)  # DLL powered down (slave mode)
        # Final write is the enable sequence end
        self.assertEqual(self.i2c.written[-1], (0x00, 0x41))

    def test_volume(self):
        self.codec.set_volume(30)
        expected = 191 + 60  # 0xBF is 0 dB, 0.5 dB per step
        for reg in (0x1B, 0x1C, 0x1D, 0x1E):
            self.assertIn((reg, expected), self.i2c.written)

    def test_volume_out_of_range(self):
        with self.assertRaises(ValueError):
            self.codec.set_volume(33)
        with self.assertRaises(ValueError):
            self.codec.set_volume(-100)

    def test_unsupported_sample_rate(self):
        with self.assertRaises(ValueError):
            self.codec.configure(sample_rate_hz=12345, mclk_ratio=256)

    def test_set_mic_gain(self):
        self.codec.set_mic_gain(12)
        self.assertIn((0x43, 4 | 0x10), self.i2c.written)


if __name__ == "__main__":
    unittest.main(verbosity=2)
