print("lilygo_t_hmi.py initialization")

# --- POWER HOLD ---
from machine import Pin

Pin(10, Pin.OUT, value=1)
Pin(14, Pin.OUT, value=1)

import lcd_bus
import machine
import xpt2046

import mpos.ui

import lvgl as lv

from machine import Pin
from micropython import const
from mpos import BatteryManager

# display settings
_WIDTH = const(240)
_HEIGHT = const(320)
_BL = const(38)
_RST = -1
_CS = const(6)
_DC = const(7)
_WR = const(8)
_FREQ = const(20000000)
_DATA0 = const(48)
_DATA1 = const(47)
_DATA2 = const(39)
_DATA3 = const(40)
_DATA4 = const(41)
_DATA5 = const(42)
_DATA6 = const(45)
_DATA7 = const(46)
_BATTERY_PIN = const(5)

_BUFFER_SIZE = const(28800)

display_bus = lcd_bus.I80Bus(
    dc=_DC,
    wr=_WR,
    cs=_CS,
    data0=_DATA0,
    data1=_DATA1,
    data2=_DATA2,
    data3=_DATA3,
    data4=_DATA4,
    data5=_DATA5,
    data6=_DATA6,
    data7=_DATA7
)

fb1 = display_bus.allocate_framebuffer(_BUFFER_SIZE, lcd_bus.MEMORY_SPIRAM)
fb2 = display_bus.allocate_framebuffer(_BUFFER_SIZE, lcd_bus.MEMORY_SPIRAM)

import drivers.display.st7789 as st7789

mpos.ui.main_display = st7789.ST7789(
    data_bus=display_bus,
    frame_buffer1=fb1,
    frame_buffer2=fb2,
    display_width=_WIDTH,
    display_height=_HEIGHT,
    backlight_pin=_BL,
    color_byte_order=st7789.BYTE_ORDER_RGB,
    rgb565_byte_swap=False,
)

spi_bus = machine.SPI.Bus(
    host=2,
    mosi=3,
    miso=4,
    sck=1
)

touch_dev = machine.SPI.Device(
    spi_bus=spi_bus,
    freq=const(1000000),
    cs=2
)

indev = xpt2046.XPT2046(touch_dev,debug=False,startup_rotation=lv.DISPLAY_ROTATION._0)

mpos.ui.main_display.init()
mpos.ui.main_display.set_color_inversion(False)
mpos.ui.main_display.set_backlight(100)
mpos.ui.main_display.set_rotation(lv.DISPLAY_ROTATION._0) # must be done after initializing display and creating the touch drivers, to ensure proper handling

lv.init()

print("lilygo_t_hmi.py SDCard initialization...")

# Initialize SD card in SDIO mode
from mpos import sdcard
sdcard.init(cmd_pin=11,clk_pin=12,d0_pin=13)

print("lilygo_t_hmi.py Battery initialization...")


def adc_to_voltage(raw_adc_value):
    """
    The percentage calculation uses MIN_VOLTAGE = 3.15 and MAX_VOLTAGE = 4.15
    0% at 3.15V -> raw_adc_value = 210
    100% at 4.15V -> raw_adc_value = 310

    4.15 - 3.15 = 1V
    310 - 210 = 100 raw ADC steps

    So each raw ADC step is 1V / 100 = 0.01V
    Offset calculation:
    """
    return raw_adc_value * 0.001651 + 0.08709

BatteryManager.init_adc(_BATTERY_PIN, adc_to_voltage)

print("lilygo_t_hmi.py finished")