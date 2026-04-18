# ES8311 mono audio codec driver
# Initialises the ES8311 over I2C so that the ESP32 I2S peripheral can route
# audio to/from the on-board speaker/microphone.
#
# The codec must be configured once at boot (before any I2S TX/RX session).
# It does NOT need to be re-initialised per session; the same divider values
# are valid for every sample rate because MCLK is always supplied as
# 256 × sample_rate by the caller (PWM or I2S MCK pin).
#
# Clock maths (MCLK_MULTIPLE = 256, bits-per-slot = 16, two slots per frame):
#   BCLK    = sample_rate × 2 × 16 = sample_rate × 32
#   SCLKDIV = MCLK / BCLK          = 256 × SR   / (32 × SR) = 8
#   LRCKDIV = MCLK / LRCK          = 256 × SR   / SR        = 256 = 0x100
# → REG03 = 8, REG04 = 0x01, REG05 = 0x00 — constant for all sample rates.
#
# The codec is configured as I2S slave (ESP32 drives BCLK and LRCK).
# I2S format: standard I2S, 16-bit word length.
# Microphone input: single-ended analogue (MIC1P/MIC1N differential pair).
# Speaker output:   mono analogue line output via built-in HP driver.

import time

try:
    from micropython import const
except ImportError:
    def const(x): return x

I2C_ADDR = const(0x18)

# ---------------------------------------------------------------------------
# Register addresses (from ES8311 datasheet)
# ---------------------------------------------------------------------------
_REG_RESET         = const(0x00)
_REG_CLK1          = const(0x01)
_REG_CLK2          = const(0x02)
_REG_CLK3          = const(0x03)  # SCLKDIV (MCLK→BCLK divider)
_REG_CLK4          = const(0x04)  # LRCKDIV high byte
_REG_CLK5          = const(0x05)  # LRCKDIV low byte
_REG_CLK6          = const(0x06)  # ADC oversampling clock
_REG_CLK7          = const(0x07)  # DAC oversampling clock
_REG_CLK8          = const(0x08)  # Clock enable mask
_REG_SDPIN         = const(0x09)  # ADC serial data format (I2S slave → codec RX)
_REG_SDPOUT        = const(0x0A)  # DAC serial data format (codec TX → I2S master)
_REG_SYSTEM0D      = const(0x0D)
_REG_SYSTEM0E      = const(0x0E)
_REG_SYSTEM0F      = const(0x0F)
_REG_SYSTEM10      = const(0x10)  # VSEL (reference voltage)
_REG_SYSTEM11      = const(0x11)
_REG_SYSTEM12      = const(0x12)  # Microphone bias
_REG_SYSTEM13      = const(0x13)
_REG_SYSTEM14      = const(0x14)  # ADC power and MIC input mux
_REG_ADC1          = const(0x17)  # ADC power / PGA gain
_REG_ADC2          = const(0x18)
_REG_ADC3          = const(0x19)  # ADC high-pass filter
_REG_ADC_VOL       = const(0x1A)  # ADC digital volume (0x00 = 0 dB)
_REG_ADC5          = const(0x1B)
_REG_ADC6          = const(0x1C)  # ALC / noise-gate control
_REG_DAC1          = const(0x32)  # DAC power
_REG_DAC2          = const(0x33)  # DAC output mixer / HP driver
_REG_DAC3          = const(0x34)
_REG_DAC4          = const(0x35)
_REG_DAC_VOL       = const(0x37)  # DAC digital volume (0x00 = 0 dB, 0xFF = −96 dB)
_REG_ANALOG_PWR    = const(0x45)  # Analogue power management

# ---------------------------------------------------------------------------
# _CLK1: MCLK from external pin, clocks enabled, no pre-divider, no doubler
# _SDPIN / _SDPOUT: slave mode, 16-bit word length, standard I2S format
# ---------------------------------------------------------------------------
_CLK1_MCLK_FROM_PIN = const(0x30)  # ENCLK=1, CLK_CPU_EN=1, MCLKDIV=÷1
_I2S_16BIT_SLAVE    = const(0x0C)  # MASTER=0, WL[2:0]=011 (16-bit), FMT=I2S
_VOL_REG_MAX_ATTEN  = const(0xBF)  # register value that gives maximum attenuation (~−96 dB)


class ES8311:
    """
    Minimal ES8311 codec initialiser.

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
        # Reset then release
        self._wr(_REG_RESET, 0x1F)
        time.sleep_ms(20)
        self._wr(_REG_RESET, 0x00)

        # Clock configuration — fixed dividers, valid for all sample rates
        # when MCLK = 256 × sample_rate (see module header).
        self._wr(_REG_CLK1, _CLK1_MCLK_FROM_PIN)
        self._wr(_REG_CLK2, 0x00)   # no pre-divider, no frequency doubler
        self._wr(_REG_CLK3, 0x08)   # SCLKDIV = 8  → BCLK = MCLK / 8
        self._wr(_REG_CLK4, 0x01)   # LRCKDIV = 0x0100 = 256  (high byte)
        self._wr(_REG_CLK5, 0x00)   # LRCKDIV low byte
        self._wr(_REG_CLK6, 0x03)   # ADC oversampling clock divider
        self._wr(_REG_CLK7, 0x03)   # DAC oversampling clock divider
        self._wr(_REG_CLK8, 0xFF)   # enable all internal clocks

        # I2S serial data format: 16-bit standard I2S, slave mode
        self._wr(_REG_SDPIN,  _I2S_16BIT_SLAVE)  # ADC (recording)
        self._wr(_REG_SDPOUT, _I2S_16BIT_SLAVE)  # DAC (playback)

        # System / power-up settings (from Espressif ES8311 reference driver)
        self._wr(_REG_SYSTEM0D, 0x01)
        self._wr(_REG_SYSTEM0E, 0x02)
        self._wr(_REG_SYSTEM0F, 0x44)
        self._wr(_REG_SYSTEM10, 0x1C)  # VSEL: reference voltage for 3.3 V supply
        self._wr(_REG_SYSTEM11, 0x00)
        self._wr(_REG_SYSTEM12, 0x02)  # enable MICBIAS for on-board microphone
        self._wr(_REG_SYSTEM13, 0x10)
        self._wr(_REG_SYSTEM14, 0x1A)  # power-up ADC; select MIC1 input

        # ADC (microphone recording)
        self._wr(_REG_ADC1,    0xBF)  # power on ADC, PGA gain enabled
        self._wr(_REG_ADC2,    0x00)
        self._wr(_REG_ADC3,    0x02)  # enable ADC high-pass filter
        self._wr(_REG_ADC_VOL, 0x00)  # ADC digital volume: 0 dB
        self._wr(_REG_ADC5,    0x00)
        self._wr(_REG_ADC6,    0x6C)  # ALC off, noise gate off

        # DAC (speaker playback)
        self._wr(_REG_DAC1,    0x00)  # power on DAC
        self._wr(_REG_DAC2,    0xBF)  # enable DAC output and HP driver
        self._wr(_REG_DAC3,    0x00)
        self._wr(_REG_DAC4,    0x00)
        self._wr(_REG_DAC_VOL, 0x00)  # DAC digital volume: 0 dB

        # Analogue power-up
        self._wr(_REG_ANALOG_PWR, 0x00)

        print("ES8311: codec initialised")

    def set_dac_volume(self, percent):
        """
        Set DAC (playback) volume.

        Args:
            percent: 0 (mute) … 100 (0 dB, maximum)
        """
        # Linear mapping: 0% → _VOL_REG_MAX_ATTEN (≈ −96 dB), 100% → 0x00 (0 dB)
        val = int((100 - max(0, min(100, percent))) * _VOL_REG_MAX_ATTEN // 100)
        self._wr(_REG_DAC_VOL, val)

    def set_adc_volume(self, percent):
        """
        Set ADC (recording) gain.

        Args:
            percent: 0 (mute) … 100 (0 dB, maximum)
        """
        val = int((100 - max(0, min(100, percent))) * _VOL_REG_MAX_ATTEN // 100)
        self._wr(_REG_ADC_VOL, val)
