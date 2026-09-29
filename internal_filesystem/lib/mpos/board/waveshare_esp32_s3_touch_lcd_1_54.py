import logging

logger = logging.getLogger(__name__)

if __debug__: logger.debug("waveshare_esp32_s3_touch_lcd_1_54.py initialization")
# Hardware initialization for the Waveshare ESP32-S3-Touch-LCD-1.54:
# 1.54" 240x240 IPS (ST7789 over SPI), CST816S capacitive touch, ES8311 audio
# codec (speaker) + ES7210 mic ADC, TF card slot, BOOT button. No IMU, no
# camera, no battery (USB powered).
#
# Manufacturer's wiki: https://www.waveshare.com/wiki/ESP32-S3-Touch-LCD-1.54
# Pinout taken from the vendor BSP/driver sources:
# https://github.com/waveshareteam/ESP32-S3-Touch-LCD-1.54 (bsp header
# esp32_s3_touch_lcd_1_54.h and the 10_esp_sr Arduino example).

import time

import drivers.display.st7789 as st7789
import drivers.indev.cst816s as cst816s
import i2c
import lcd_bus
import lvgl as lv
import machine
import mpos.ui
from mpos import InputManager

# Pin configuration (from the vendor BSP header)
SPI_BUS = 2
SPI_FREQ = 40000000
LCD_SCLK = 38
LCD_MOSI = 39
LCD_CS = 21
LCD_DC = 45
LCD_RST = 40
LCD_BL = 46

I2C_SDA = 42
I2C_SCL = 41

TOUCH_ADDR = 0x15  # CST816S
TOUCH_RST = 47
ES8311_ADDR = 0x18  # DAC (speaker)
ES7210_ADDR = 0x40  # ADC (microphone)

# Shared I2C bus: CST816S touch, ES8311 codec, ES7210 mic ADC
i2c_bus = i2c.I2C.Bus(host=0, scl=I2C_SCL, sda=I2C_SDA, freq=400000, use_locks=False)

if __debug__: logger.debug("waveshare_esp32_s3_touch_lcd_1_54.py machine.SPI.Bus() initialization")
try:
    spi_bus = machine.SPI.Bus(host=SPI_BUS, mosi=LCD_MOSI, sck=LCD_SCLK)
except Exception as e:
    logger.error("Error initializing SPI bus: %s" % (e))
    if __debug__: logger.debug("Attempting hard reset in 3sec...")
    time.sleep(3)
    machine.reset()

display_bus = lcd_bus.SPIBus(
    spi_bus=spi_bus,
    freq=SPI_FREQ,
    dc=LCD_DC,
    cs=LCD_CS,
)

# 240*240*2 = 115200 bytes full frame; use small DMA strips like the
# ESP32-S3-Touch-LCD-2 board does (28800 there).
_BUFFER_SIZE = const(240 * 30 * 2)  # 14400
fb1 = display_bus.allocate_framebuffer(_BUFFER_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)
fb2 = display_bus.allocate_framebuffer(_BUFFER_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)

mpos.ui.main_display = st7789.ST7789(
    data_bus=display_bus,
    frame_buffer1=fb1,
    frame_buffer2=fb2,
    display_width=240,
    display_height=240,
    reset_pin=LCD_RST,
    reset_state=st7789.STATE_LOW,  # RST is active-low: idle HIGH, pulse LOW
    color_space=lv.COLOR_FORMAT.RGB565,
    color_byte_order=st7789.BYTE_ORDER_RGB,
    rgb565_byte_swap=True,
    backlight_pin=LCD_BL,
    backlight_on_state=st7789.STATE_PWM,
)  # triggers lv.init()
mpos.ui.main_display.init()
mpos.ui.main_display.set_power(True)
mpos.ui.main_display.set_backlight(70)  # 100 washes out colors on this panel

# Touch handling: the CST816S sits on the shared I2C bus, with dedicated
# reset (GPIO47) and interrupt (GPIO48) lines.
touch_dev = i2c.I2C.Device(bus=i2c_bus, dev_id=TOUCH_ADDR, reg_bits=8)
indev = cst816s.CST816S(touch_dev, reset_pin=TOUCH_RST, startup_rotation=lv.DISPLAY_ROTATION._180)
InputManager.register_indev(indev)

# Landscape orientation, like the other MPOS boards. Rotation only takes
# effect at init; flip between _90/_270 (and the touch startup_rotation)
# depending on how the board is oriented in its enclosure.
mpos.ui.main_display.set_rotation(lv.DISPLAY_ROTATION._90)

# === AUDIO (ES8311 DAC for the speaker + ES7210 ADC for the microphone) ===
# I2S pins from the vendor BSP: MCLK=8, SCLK=9, LRCK=10, DOUT (playback)=12,
# DSIN (recording)=11. Both codecs hang off the shared I2C bus. The onboard
# speaker amplifier is enabled via GPIO7 (BSP_POWER_AMP_IO); it must be
# driven high for any sound to be audible.
try:
    amp = machine.Pin(7, machine.Pin.OUT)
    amp.value(0)  # start muted; released after the codec is configured
except Exception as e:
    amp = None
    logger.error("Power amp pin init failed: %s" % (e))

_es8311 = None
_es7210 = None
try:
    import drivers.codec.es8311 as es8311_drv
    import drivers.codec.es7210 as es7210_drv

    class _CodecI2C:
        """Adapt the lcd_bus i2c wrapper to the machine.I2C-style API the
        codec drivers expect (writeto_mem/readfrom_mem_into)."""

        def __init__(self, bus, dev_id):
            self._dev = i2c.I2C.Device(bus=bus, dev_id=dev_id, reg_bits=8)

        def writeto_mem(self, addr, reg, data):
            self._dev.write_mem(reg, data)

        def readfrom_mem_into(self, addr, reg, buf):
            self._dev.read_mem(reg, buf=buf)

    _es8311 = es8311_drv.ES8311(_CodecI2C(i2c_bus, ES8311_ADDR))
    # 76% was tuned by ear on the sibling ESP32-S3-Touch-LCD-3.5 board which
    # uses the same codec; the driver's 85% default distorts.
    _es8311.set_dac_volume(76)

    _es7210 = es7210_drv.ES7210(_CodecI2C(i2c_bus, ES7210_ADDR))
    _es7210.configure(sample_rate_hz=16000, mclk_ratio=256, gain_db=30)
except Exception as e:
    logger.error("Audio codec init failed: %s" % (e))


def _audio_on_open():
    """Called after MCLK starts and before I2S init: enable the speaker amp
    and release the DAC soft-mute."""
    if amp:
        amp.value(1)
    if _es8311:
        time.sleep_ms(10)
        _es8311.dac_mute(False)


def _audio_on_close():
    """Called before I2S deinit: mute the DAC and cut the amp to suppress
    pops."""
    if _es8311:
        _es8311.dac_mute(True)
        time.sleep_ms(20)
    if amp:
        amp.value(0)


if _es8311:
    from mpos import AudioManager

    AudioManager.add(
        AudioManager.Output(
            name="Speaker",
            kind="i2s",
            channels=1,
            i2s_pins={
                'mck': 8,   # MCLK - 256 x sample_rate during playback
                'sck': 9,   # BCLK
                'ws':  10,  # LRCK
                'sd':  12,  # I2S TX (ESP32 -> ES8311 DAC)
            },
            on_open=_audio_on_open,
            on_close=_audio_on_close,
        )
    )

    if _es7210:
        AudioManager.add(
            AudioManager.Input(
                name="Microphone",
                kind="i2s",
                channels=1,
                i2s_pins={
                    'mck':   8,
                    'sck':   9,
                    'ws':    10,
                    'sd_in': 11,  # I2S RX (ES7210 ADC -> ESP32)
                },
                preferred_sample_rate=16000,
            )
        )

# === TF CARD ===
# SDMMC 4-bit slot, pins from the vendor BSP. Initialized here so the file
# manager and apps can mount it on demand via SDCardManager.mount().
from mpos import SDCardManager

SDCardManager.init(
    mode='sdio',
    cmd_pin=15,
    clk_pin=16,
    d0_pin=17,
    d1_pin=18,
    d2_pin=13,
    d3_pin=14,
    slot=0,
    width=4,
)

if __debug__: logger.debug("waveshare_esp32_s3_touch_lcd_1_54.py finished")
