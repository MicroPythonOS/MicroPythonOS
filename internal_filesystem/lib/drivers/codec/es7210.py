# ES7210 4-channel microphone ADC (audio echo canceller) driver.
# Initialises the ES7210 over I2C so that the ESP32 I2S peripheral can record
# from the on-board microphone. Pairs with the ES8311 DAC driver (es8311.py)
# on boards that wire both codecs to the same I2S bus (e.g. the Waveshare
# ESP32-S3-Touch-LCD-1.54, which uses an ES8311 for the speaker and an
# ES7210 for the microphone).
#
# Register layout and initialisation sequence are taken directly from the
# Waveshare ESP32-S3-Touch-LCD-1.54 Arduino demo (10_esp_sr example,
# es7210.cpp/es7210_reg.h), which mirrors the Espressif esp_codec_dev /
# ESP-ADF es7210 reference driver.
#
# Clock configuration (MCLK_MULTIPLE = 256, 16-bit I2S):
#   MCLK = sample_rate x 256, LRCK = MCLK / 256 = sample_rate.
#   Divider values come from the vendor coeff table, which contains entries
#   for every standard rate at MCLK = rate x 256 (8k..96k).

try:
    from micropython import const
except ImportError:
    def const(x): return x

I2C_ADDR = const(0x40)  # 0x40..0x43 depending on the A0/A1 pins

# ---------------------------------------------------------------------------
# Register addresses (from es7210_reg.h, vendor reference driver)
# ---------------------------------------------------------------------------
_REG00_RESET        = const(0x00)  # reset control
_REG02_MAINCLK      = const(0x02)  # ADC clock division
_REG04_LRCK_DIVH    = const(0x04)  # lrck divider high
_REG05_LRCK_DIVL    = const(0x05)  # lrck divider low
_REG06_POWER_DOWN   = const(0x06)  # power down (DLL etc.)
_REG07_OSR          = const(0x07)  # ADC oversampling rate
_REG11_SDP_IF1      = const(0x11)  # sample bit width + I2S format
_REG12_SDP_IF2      = const(0x12)  # pins state / 1xFS TDM
_REG20_HPF2_ADC34   = const(0x20)  # HPF config
_REG21_HPF1_ADC34   = const(0x21)
_REG22_HPF2_ADC12   = const(0x22)
_REG23_HPF1_ADC12   = const(0x23)
_REG1B_ADC1_DB      = const(0x1B)  # ADC1 direct dB gain
_REG1C_ADC2_DB      = const(0x1C)
_REG1D_ADC3_DB      = const(0x1D)
_REG1E_ADC4_DB      = const(0x1E)
_REG40_ANALOG       = const(0x40)  # analog power / VMID
_REG41_MIC12_BIAS   = const(0x41)  # MIC1/2 bias voltage
_REG42_MIC34_BIAS   = const(0x42)
_REG43_MIC1_GAIN    = const(0x43)  # MIC1 PGA gain
_REG44_MIC2_GAIN    = const(0x44)
_REG45_MIC3_GAIN    = const(0x45)
_REG46_MIC4_GAIN    = const(0x46)
_REG47_MIC1_POWER   = const(0x47)
_REG48_MIC2_POWER   = const(0x48)
_REG49_MIC3_POWER   = const(0x49)
_REG4A_MIC4_POWER   = const(0x4A)
_REG4B_MIC12_POWER  = const(0x4B)  # MIC1/2 bias + ADC1/2 + PGA1/2 power
_REG4C_MIC34_POWER  = const(0x4C)
_REG09_TIME0        = const(0x09)  # chip initial state period
_REG0A_TIME1        = const(0x0A)  # power-up state period

# Vendor coeff table entries for MCLK = rate x 256 (lrck == rate):
#   rate -> (adc_div, dll, doubler, osr, lrck_h, lrck_l)
_COEFF_MCLK_256 = {
    8000:  (0x03, 0x01, 0x00, 0x20, 0x06, 0x00),  # from mclk 12288000
    16000: (0x01, 0x01, 0x01, 0x20, 0x01, 0x00),  # from mclk 4096000
    24000: (0x01, 0x00, 0x00, 0x20, 0x02, 0x00),  # from mclk 12288000
    32000: (0x01, 0x01, 0x00, 0x20, 0x02, 0x00),  # from mclk 16384000
    44100: (0x01, 0x01, 0x00, 0x20, 0x01, 0x00),  # from mclk 11289600
    48000: (0x01, 0x01, 0x01, 0x20, 0x01, 0x00),  # from mclk 12288000
    96000: (0x01, 0x01, 0x01, 0x20, 0x00, 0x80),  # from mclk 12288000
}


class ES7210:
    """Minimal ES7210 microphone ADC setup for one mic on SDP1, I2S format,
    16-bit, slave mode (the ESP32 I2S peripheral drives SCLK/LRCK)."""

    def __init__(self, i2c, addr=I2C_ADDR):
        self._i2c = i2c
        self._addr = addr

    def _wr(self, reg, val):
        self._i2c.writeto_mem(self._addr, reg, bytes([val]))

    def _rd(self, reg, buf):
        self._i2c.readfrom_mem_into(self._addr, reg, buf)

    def configure(self, sample_rate_hz=16000, mclk_ratio=256, gain_db=30,
                  bias_2v87=True, volume_db=30):
        """Full init mirroring the vendor es7210_config_codec() sequence.

        sample_rate_hz: recording rate; requires MCLK = rate x mclk_ratio.
        mclk_ratio:      256 by default (the ratio AudioManager drives MCLK at).
        gain_db:         analog mic PGA gain, 0..37.5 dB in 3 dB steps.
        bias_2v87:       electret mic bias voltage 2.87 V (vendor default).
        volume_db:       digital ADC volume, -95.5..+32 dB.
        """
        coeff = _COEFF_MCLK_256.get(sample_rate_hz * mclk_ratio // 256)
        if mclk_ratio != 256 or coeff is None:
            raise ValueError("unsupported sample rate for MCLK=rate*%d" % mclk_ratio)
        adc_div, dll, doubler, osr, lrck_h, lrck_l = coeff

        # Software reset
        self._wr(_REG00_RESET, 0xFF)
        self._wr(_REG00_RESET, 0x32)
        # Initial state / power-up periods
        self._wr(_REG09_TIME0, 0x30)
        self._wr(_REG0A_TIME1, 0x30)
        # HPF for ADC1-4
        self._wr(_REG23_HPF1_ADC12, 0x2A)
        self._wr(_REG22_HPF2_ADC12, 0x0A)
        self._wr(_REG21_HPF1_ADC34, 0x2A)
        self._wr(_REG20_HPF2_ADC34, 0x0A)
        # 16-bit per sample, normal I2S format, no TDM
        self._wr(_REG11_SDP_IF1, 0x60)
        self._wr(_REG12_SDP_IF2, 0x00)
        # Analog power + VMID
        self._wr(_REG40_ANALOG, 0xC3)
        # MIC bias 2.87 V (electret microphones)
        bias = 0x70 if bias_2v87 else 0x00
        self._wr(_REG41_MIC12_BIAS, bias)
        self._wr(_REG42_MIC34_BIAS, bias)
        # MIC1-4 PGA gain: 3 dB steps, bit 4 must be set (vendor code ORs 0x10)
        gain_reg = (gain_db // 3) | 0x10
        self._wr(_REG43_MIC1_GAIN, gain_reg)
        self._wr(_REG44_MIC2_GAIN, gain_reg)
        self._wr(_REG45_MIC3_GAIN, gain_reg)
        self._wr(_REG46_MIC4_GAIN, gain_reg)
        # Power on MIC1-4
        self._wr(_REG47_MIC1_POWER, 0x08)
        self._wr(_REG48_MIC2_POWER, 0x08)
        self._wr(_REG49_MIC3_POWER, 0x08)
        self._wr(_REG4A_MIC4_POWER, 0x08)
        # ADC oversampling + clock dividers for the requested rate
        self._wr(_REG07_OSR, osr)
        self._wr(_REG02_MAINCLK, adc_div | (doubler << 6) | (dll << 7))
        self._wr(_REG04_LRCK_DIVH, lrck_h)
        self._wr(_REG05_LRCK_DIVL, lrck_l)
        # Power down DLL (not needed in slave mode)
        self._wr(_REG06_POWER_DOWN, 0x04)
        # Power on MIC1-4 bias, ADC1-4 and PGA1-4
        self._wr(_REG4B_MIC12_POWER, 0x0F)
        self._wr(_REG4C_MIC34_POWER, 0x0F)
        # Digital volume
        self.set_volume(volume_db)
        # Enable device
        self._wr(_REG00_RESET, 0x71)
        self._wr(_REG00_RESET, 0x41)

    def set_volume(self, volume_db):
        """Digital ADC volume: 0x00 = -95.5 dB, 0xBF = 0 dB, 0xFF = +32 dB
        (0.5 dB per step)."""
        if volume_db < -95 or volume_db > 32:
            raise ValueError("volume_db must be -95..32")
        reg_val = 191 + volume_db * 2
        self._wr(_REG1B_ADC1_DB, reg_val)
        self._wr(_REG1C_ADC2_DB, reg_val)
        self._wr(_REG1D_ADC3_DB, reg_val)
        self._wr(_REG1E_ADC4_DB, reg_val)

    def set_mic_gain(self, gain_db):
        """Analog PGA gain in dB (0..37.5, 3 dB steps)."""
        gain_reg = (gain_db // 3) | 0x10
        self._wr(_REG43_MIC1_GAIN, gain_reg)
        self._wr(_REG44_MIC2_GAIN, gain_reg)
        self._wr(_REG45_MIC3_GAIN, gain_reg)
        self._wr(_REG46_MIC4_GAIN, gain_reg)
