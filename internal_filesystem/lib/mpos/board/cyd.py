print("cyd.py initialization")
"""
Cheap Yellow Display:
    https://github.com/witnessmenow/ESP32-Cheap-Yellow-Display
Tested with "ESP32-2432S028"

 * Display: ili9341 320x240
 * Touch: xpt2046

Original author: https://github.com/jedie
"""

import time

import drivers.display.ili9341 as ili9341
import lcd_bus
import lvgl as lv
import machine
import mpos.ui
from drivers.indev.xpt2046 import XPT2046
from machine import ADC, Pin
from micropython import const
from mpos import InputManager

# Display (HSPI)
SPI_HOST = const(0)
SPI_FREQ = const(8_000_000)  # 8MHz max for ILI9341
SPI_DC = const(2)  # TFT_RS / TFT_DC
SPI_CS = const(15)  # TFT_CS
SPI_RST = const(15)  # No reset pin, so use CS pin
SPI_SCK = const(14)  # TFT_SCK
SPI_MISO = const(12)  # TFT_SDO / TFT_MISO
SPI_MOSI = const(13)  # TFT_SDI / TFT_MOSI

BACKLIGHT_PIN = const(21)  # TFT_BL (also on P3)
DISPLAY_WIDTH = const(320)
DISPLAY_HEIGHT = const(240)
LCD_TYPE = const(2)  # ILI9341 type 2

# Touch Screen (XPT2046)
TOUCH_SPI_HOST = const(1)
TOUCH_SPI_FREQ = const(1_000_000)  # 1MHz
TOUCH_SPI_SCK = const(25)
TOUCH_SPI_MOSI = const(32)
TOUCH_SPI_MISO = const(39)
TOUCH_SPI_CS = const(33)
TOUCH_SPI_INT = const(36)

# SD Card (VSPI)
SDCARD_SLOT = const(2)
SDCARD_SCK = const(18)
SDCARD_MISO = const(19)
SDCARD_MOSI = const(23)
SDCARD_CS = const(5)

# RGB LED (active low)
LED_RED = const(4)
LED_GREEN = const(16)
LED_BLUE = const(17)

# Light Sensor
LIGHTSENSOR_ADC_PIN = const(34)

# Speaker (amplified)
SPEAKER_PIN = const(26)

# Buttons
BUTTON_BOOT = const(0)

# Connectors
P3_IO35 = const(35)  # Input only
P3_IO22 = const(22)
CN1_IO22 = const(22)
CN1_IO27 = const(27)
P1_IO1 = const(1)  # TX (maybe usable as GPIO)
P1_IO3 = const(3)  # RX (maybe usable as GPIO)


# RGB LED at the back
red_led = Pin(LED_RED, Pin.OUT)
green_led = Pin(LED_GREEN, Pin.OUT)
blue_led = Pin(LED_BLUE, Pin.OUT)

# RGB LED (and backlight) will also work with machine.PWM for dimming

# Turn on all LEDs (active low):
red_led.on()
green_led.on()
blue_led.on()


# Read light sensor
lightsensor = ADC(LIGHTSENSOR_ADC_PIN, atten=ADC.ATTN_0DB)
print(f"{lightsensor.read_uv()=}")


print("cyd.py machine.SPI.Bus() initialization")
try:
    spi_bus = machine.SPI.Bus(
        host=TOUCH_SPI_HOST, sck=SPI_SCK, mosi=SPI_MOSI, miso=SPI_MISO
    )
except Exception as e:
    print(f"Error initializing SPI bus: {e}")
    print("Attempting hard reset in 3sec...")
    time.sleep(3)
    machine.reset()

print("cyd.py lcd_bus.SPIBus() initialization")
display_bus = lcd_bus.SPIBus(spi_bus=spi_bus, freq=SPI_FREQ, dc=SPI_DC, cs=SPI_CS)

print("cyd.py ili9341.ILI9341() initialization")
try:
    mpos.ui.main_display = ili9341.ILI9341(
        data_bus=display_bus,
        display_width=DISPLAY_WIDTH,
        display_height=DISPLAY_HEIGHT,
        color_space=lv.COLOR_FORMAT.RGB565,
        color_byte_order=ili9341.BYTE_ORDER_BGR,
        rgb565_byte_swap=True,
        reset_pin=SPI_RST,
        reset_state=ili9341.STATE_LOW,
        backlight_pin=BACKLIGHT_PIN,
        backlight_on_state=ili9341.STATE_PWM,
    )
except Exception as e:
    print(f"Error initializing ILI9341: {e}")
    print("Attempting hard reset in 3sec...")
    time.sleep(3)
    machine.reset()


print("cyd.py display.init()")
mpos.ui.main_display.init(LCD_TYPE)
mpos.ui.main_display.set_power(True)
mpos.ui.main_display.set_color_inversion(False)
mpos.ui.main_display.set_backlight(100)

print("cyd.py lv.init() initialization")
lv.init()

print("cyd.py Touch initialization")
touch_dev = machine.SPI.Device(spi_bus=spi_bus, freq=TOUCH_SPI_FREQ, cs=TOUCH_SPI_CS)

indev = XPT2046(
    touch_dev,
    lcd_cs=SPI_CS,
    touch_cs=TOUCH_SPI_CS,
    display_width=DISPLAY_WIDTH,
    display_height=DISPLAY_HEIGHT,
    startup_rotation=lv.DISPLAY_ROTATION._0,
)


group = lv.group_create()
group.set_default()
#
# # Create and set up the input device
# indev = lv.indev_create()
# indev.set_type(lv.INDEV_TYPE.KEYPAD)
#
indev.set_group(
    group
)  # is this needed? maybe better to move the default group creation to main.py so it's available everywhere...
# disp = lv.display_get_default()  # NOQA
# indev.set_display(disp)  # different from display
indev.enable(True)  # NOQA
InputManager.register_indev(indev)

# Turn off all LEDs to indicate initialization is done:
red_led.off()
green_led.off()
blue_led.off()

print("\ncyd.py init finished\n")
