# ES8311 mono audio codec driver
# Initialises the ES8311 over I2C so that the ESP32 I2S peripheral can route
# audio to/from the on-board speaker/microphone.
#
# Register layout and initialisation sequence are taken directly from the
# Espressif reference driver shipped with the Freenove ESP32-S3 Display
# tutorial sketches (Sketch_07.1_Music / Sketch_07.2_Echo, es8311.cpp).
#
# Clock configuration (MCLK_MULTIPLE = 256, 16-bit I2S, two slots per frame):
#   MCLK   = sample_rate × 256  (driven by MCK PWM pin)
#   BCLK   = MCLK / 4  (bclk_div = 4  → REG06 = bclk_div−1 = 3)
#   LRCK   = MCLK / 256 = sample_rate  (lrck_h=0x00, lrck_l=0xFF → REG07/08)
#   ADC/DAC oversampling rate = 0x10  (REG03 / REG04)
# These divider values are identical for every standard sample rate when
# MCLK = rate × 256 (verified against Espressif coeff_div[] table).
#
# The codec runs as I2S slave (ESP32-S3 drives BCLK and LRCK).

import time

try:
    from micropython import const
except ImportError:
    def const(x): return x

I2C_ADDR = const(0x18)

# ---------------------------------------------------------------------------
# Register addresses (from es8311_reg.h, Espressif reference driver)
# ---------------------------------------------------------------------------
_REG00_RESET    = const(0x00)  # reset + power control
_REG01_CLK_SRC  = const(0x01)  # clock source select, all-clock enable
_REG02_CLK_DIV  = const(0x02)  # pre-divider / pre-multiplier
_REG03_ADC_OSR  = const(0x03)  # ADC fs-mode and oversampling rate
_REG04_DAC_OSR  = const(0x04)  # DAC oversampling rate
_REG05_CLKDIV   = const(0x05)  # ADC and DAC clock dividers
_REG06_BCLKDIV  = const(0x06)  # BCLK (SCLK) inverter and divider
_REG07_LRCK_H   = const(0x07)  # LRCK divider high byte
_REG08_LRCK_L   = const(0x08)  # LRCK divider low byte
_REG09_SDP_IN   = const(0x09)  # serial data port for DAC (playback input to codec)
_REG0A_SDP_OUT  = const(0x0A)  # serial data port for ADC (recording output from codec)
_REG0D_SYS      = const(0x0D)  # system: power-up analog circuitry
_REG0E_SYS      = const(0x0E)  # system: enable analog PGA + ADC modulator
_REG12_DAC_EN   = const(0x12)  # system: power-up DAC
_REG13_SYS      = const(0x13)  # system: enable HP output driver
_REG14_MIC      = const(0x14)  # microphone: DMIC select, analog PGA gain
_REG16_ADC_GAIN = const(0x16)  # ADC digital gain (separate from volume; default 4 = 24 dB)
_REG17_ADC_VOL  = const(0x17)  # ADC volume / gain
_REG1C_ADC_EQ   = const(0x1C)  # ADC equalizer bypass + DC-offset cancel
_REG31_DAC_MUTE = const(0x31)  # DAC soft-mute control (bits[6:5] = 11 → muted)
_REG32_DAC_VOL  = const(0x32)  # DAC output volume (0x00=muted, 0xFF=max)
_REG37_DAC_EQ   = const(0x37)  # DAC equalizer / ramp-rate control

# SDP format word: slave mode (bit7=0), 16-bit resolution (bits[4:2]=011)
_SDP_16BIT_SLAVE = const(0x0C)

# Default DAC volume at init: 85% using Espressif formula (volume*256/100)−1
_DEFAULT_VOL_REG = const(0xD8)  # = (85*256//100) - 1 ≈ 85% output volume


class ES8311:
    """
    ES8311 codec initialiser.

    Usage::

        i2c = machine.I2C(0, sda=Pin(16), scl=Pin(15), freq=400_000)
        codec = ES8311(i2c)
    """

    def __init__(self, i2c):
        self._i2c = i2c
        self._init()

    # ------------------------------------------------------------------
    def _wr(self, reg, val):
        self._i2c.writeto_mem(I2C_ADDR, reg, bytes([val]))

    def _rd(self, reg):
        buf = bytearray(1)
        self._i2c.readfrom_mem_into(I2C_ADDR, reg, buf)
        return buf[0]

    # ------------------------------------------------------------------
    def _init(self):
        # --- Reset sequence (matches Espressif es8311_init) ---
        self._wr(_REG00_RESET, 0x1F)   # assert reset
        time.sleep_ms(20)
        self._wr(_REG00_RESET, 0x00)   # release reset
        self._wr(_REG00_RESET, 0x80)   # power-on command (required)

        # --- Clock configuration ---
        # REG01: enable all internal clocks; select MCLK from MCLK pin (bit7=0)
        self._wr(_REG01_CLK_SRC, 0x3F)
        # REG02: pre_div=1 (bits[7:5]=000), pre_multi=×1 (bits[4:3]=00)
        self._wr(_REG02_CLK_DIV, 0x00)
        # REG03: ADC fs_mode=single-speed (bit6=0), ADC OSR=0x10
        self._wr(_REG03_ADC_OSR, 0x10)
        # REG04: DAC OSR=0x10
        self._wr(_REG04_DAC_OSR, 0x10)
        # REG05: ADC clk_div=1 (bits[7:4]=0000), DAC clk_div=1 (bits[3:0]=0000)
        self._wr(_REG05_CLKDIV,  0x00)
        # REG06: BCLK divider = bclk_div−1 = 4−1 = 3  (MCLK/4 = BCLK for 16-bit stereo)
        self._wr(_REG06_BCLKDIV, 0x03)
        # REG07/08: LRCK divider = 0x00FF = 255+1 = 256  (MCLK/256 = sample_rate)
        self._wr(_REG07_LRCK_H,  0x00)
        self._wr(_REG08_LRCK_L,  0xFF)

        # --- I2S serial data format: 16-bit, standard I2S, slave mode ---
        self._wr(_REG09_SDP_IN,  _SDP_16BIT_SLAVE)  # DAC (playback)
        self._wr(_REG0A_SDP_OUT, _SDP_16BIT_SLAVE)  # ADC (recording)

        # --- System / analog power-up ---
        self._wr(_REG0D_SYS,    0x01)   # power up analog circuitry
        self._wr(_REG0E_SYS,    0x02)   # enable analog PGA + ADC modulator
        self._wr(_REG12_DAC_EN, 0x00)   # power up DAC
        self._wr(_REG13_SYS,    0x10)   # enable output to HP driver
        self._wr(_REG14_MIC,    0x1A)   # enable analog mic input, max PGA gain

        # --- ADC (microphone) ---
        self._wr(_REG16_ADC_GAIN, 0x04)  # ADC digital gain = 24 dB (default)
        self._wr(_REG17_ADC_VOL, 0xC8)  # ADC gain/volume (Espressif default)
        self._wr(_REG1C_ADC_EQ,  0x6A)  # ADC equalizer bypass, cancel DC offset

        # --- DAC (speaker) ---
        self._wr(_REG32_DAC_VOL, _DEFAULT_VOL_REG)  # set output volume (~85%)
        self._wr(_REG37_DAC_EQ,  0x08)              # bypass DAC equalizer

        # Soft-mute the DAC at boot — unmuted by on_open callback when playback starts
        self.dac_mute(True)

        print("ES8311: codec initialised")

    def dac_mute(self, mute=True):
        """
        Soft-mute or unmute the DAC output.

        Uses the ES8311's built-in ramp so the transition is pop-free.
        Does not affect the DAC power state or volume register.

        Args:
            mute: True to mute, False to unmute
        """
        val = self._rd(_REG31_DAC_MUTE)
        if mute:
            val |= 0x60   # bits[6:5] = 11 → soft mute on
        else:
            val &= ~0x60  # bits[6:5] = 00 → soft mute off
        self._wr(_REG31_DAC_MUTE, val)

    def set_dac_volume(self, percent):
        """
        Set DAC (speaker) volume.

        Args:
            percent: 0 (mute) … 100 (maximum)
        """
        percent = max(0, min(100, percent))
        if percent == 0:
            val = 0
        else:
            val = (percent * 256 // 100) - 1
        self._wr(_REG32_DAC_VOL, val)

    def set_adc_volume(self, percent):
        """
        Set ADC (microphone) gain.

        Args:
            percent: 0 (minimum) … 100 (maximum, 0xC8 default)
        """
        percent = max(0, min(100, percent))
        val = percent * 0xC8 // 100
        self._wr(_REG17_ADC_VOL, val)
