# Manufacturer's website at https://www.lilygo.cc/en-pl/products/t-deck
#
# LilyGO T-Deck: ESP32-S3 (16 MB flash, 8 MB PSRAM), ST7789 320x240 (landscape,
# 240x320 panel), GT911 touch, trackball (5 GPIOs), I2C keyboard controller at
# 0x55, SX1262 LoRa, microSD on the same SPI bus, battery on ADC1 GPIO4.

import logging

logger = logging.getLogger(__name__)

if __debug__: logger.debug("lilygo_t_deck.py initialization")

import time

from machine import Pin
import machine
import lcd_bus
import lvgl as lv
import i2c
import drivers.display.st7789 as st7789
import drivers.indev.gt911 as gt911
import mpos.ui
from mpos import BatteryManager, InputManager, LoRaManager

# The panel is 240x320 portrait; the OS is used in landscape, so the display gets
# the native size and a 90 degree rotation (same trick as the Waveshare boards).
WIDTH = 240
HEIGHT = 320
BUFFER_SIZE = WIDTH * HEIGHT * 2 // 4

# Display: SPI2, CS 12, DC 11, MOSI 41, SCK 40, backlight 42, no reset line.
spi_bus = machine.SPI.Bus(host=2, sck=40, mosi=41, miso=38)
display_bus = lcd_bus.SPIBus(spi_bus=spi_bus, freq=40000000, dc=11, cs=12)
fb1 = display_bus.allocate_framebuffer(BUFFER_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)
fb2 = display_bus.allocate_framebuffer(BUFFER_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)
display = st7789.ST7789(
    data_bus=display_bus,
    display_width=WIDTH,
    display_height=HEIGHT,
    frame_buffer1=fb1,
    frame_buffer2=fb2,
    backlight_pin=42,
    backlight_on_state=st7789.STATE_PWM,
    color_space=lv.COLOR_FORMAT.RGB565,
    color_byte_order=st7789.BYTE_ORDER_BGR,
    rgb565_byte_swap=True,
)
mpos.ui.main_display = display
display.init(st7789.PROFILE_ST7789V)
display.set_power(True)
display.set_backlight(100)

# Touch: GT911 on I2C0 (SDA 18, SCL 8), interrupt 16, address 0x5D.
touch_bus = i2c.I2C.Bus(host=0, sda=18, scl=8, freq=400000, use_locks=False, timeout=20000)
touch_device = i2c.I2C.Device(bus=touch_bus, dev_id=0x5D, reg_bits=16)
touch = None
try:
    touch = gt911.GT911(
        device=touch_device,
        interrupt_pin=16,
        startup_rotation=lv.DISPLAY_ROTATION._90,
        debug=False,
    )
    InputManager.register_indev(touch)
except OSError as error:
    logger.warning("T-Deck touch unavailable: %s", error)

display.set_rotation(lv.DISPLAY_ROTATION._90)

# Battery: GPIO4 through a 1:2 divider, ADC1 (works with Wi-Fi up).
try:
    raw_to_volts = lambda raw: (raw / 4095.0) * 3.3 * 2.0
    BatteryManager.init_adc(4, raw_to_volts)
except Exception as error:
    logger.warning("T-Deck battery ADC unavailable: %s", error)

# Trackball: four directions plus press. Mapped to the LVGL keypad indev.
tb_up = Pin(3, Pin.IN, Pin.PULL_UP)
tb_down = Pin(15, Pin.IN, Pin.PULL_UP)
tb_left = Pin(1, Pin.IN, Pin.PULL_UP)
tb_right = Pin(2, Pin.IN, Pin.PULL_UP)
tb_press = Pin(0, Pin.IN, Pin.PULL_UP)
_tb_candidate = None
_tb_stable = None
_tb_changed_ms = 0
_tb_last_key = lv.KEY.ENTER


def _read_trackball(indev, data):
    global _tb_candidate, _tb_stable, _tb_changed_ms, _tb_last_key
    value = None
    if tb_press.value() == 0:
        value = lv.KEY.ENTER
    elif tb_up.value() == 0:
        value = lv.KEY.UP
    elif tb_down.value() == 0:
        value = lv.KEY.DOWN
    elif tb_left.value() == 0:
        value = lv.KEY.LEFT
    elif tb_right.value() == 0:
        value = lv.KEY.RIGHT
    now = time.ticks_ms()
    if value != _tb_candidate:
        _tb_candidate = value
        _tb_changed_ms = now
    if time.ticks_diff(now, _tb_changed_ms) >= 20:
        _tb_stable = _tb_candidate
    if _tb_stable is not None:
        _tb_last_key = _tb_stable
    data.key = _tb_last_key
    data.state = lv.INDEV_STATE.PRESSED if _tb_stable is not None else lv.INDEV_STATE.RELEASED


trackball = lv.indev_create()
trackball.set_type(lv.INDEV_TYPE.KEYPAD)
trackball.set_read_cb(_read_trackball)
trackball.set_group(lv.group_get_default())
trackball.set_display(lv.display_get_default())
InputManager.register_indev(trackball)

# LoRa: SX1262 shares SPI2 with the display (SCK 40, MOSI 41, MISO 38).
try:
    from drivers.lora.micropySX126X.sx1262 import SX1262

    sx = SX1262(
        spi_bus=2,
        clk=40,
        mosi=41,
        miso=38,
        cs=9,
        irq=45,
        rst=17,
        gpio=13,
    )
    LoRaManager.radioChip = sx
except Exception as error:
    logger.warning("T-Deck LoRa unavailable: %s", error)

logger.info("T-Deck display, touch, trackball, battery and LoRa initialized")

if __debug__: logger.debug("lilygo_t_deck.py finished")
