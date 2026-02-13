# Hardware initialization for ESP32 M5Stack-Fire board
# Manufacturer's website at https://https://docs.m5stack.com/en/core/fire_v2.7
# Original author: https://github.com/ancebfer

import drivers.display.ili9341 as ili9341
import lcd_bus
import machine

import lvgl as lv
import task_handler

import mpos.ui
import mpos.ui.focus_direction
from mpos import InputManager

# Pin configuration
SPI_BUS = 1  # SPI2
SPI_FREQ = 40000000
LCD_SCLK = 18
LCD_MOSI = 23
LCD_DC = 27
LCD_CS = 14
LCD_BL = 32
LCD_RST = 33
LCD_TYPE = 2  # ILI9341 type 2

TFT_HOR_RES=320
TFT_VER_RES=240

spi_bus = machine.SPI.Bus(
    host=SPI_BUS,
    mosi=LCD_MOSI,
    sck=LCD_SCLK
)
display_bus = lcd_bus.SPIBus(
    spi_bus=spi_bus,
    freq=SPI_FREQ,
    dc=LCD_DC,
    cs=LCD_CS
)

# M5Stack-Fire ILI9342 uses ILI9341 type 2 with a modified orientation table.
class ILI9341(ili9341.ILI9341):
    _ORIENTATION_TABLE = (
        0x00,
        0x40 | 0x20,  # _MADCTL_MX | _MADCTL_MV
        0x80 | 0x40,  # _MADCTL_MY | _MADCTL_MX
        0x80 | 0x20   # _MADCTL_MY | _MADCTL_MV
    )

mpos.ui.main_display = ILI9341(
    data_bus=display_bus,
    display_width=TFT_HOR_RES,
    display_height=TFT_VER_RES,
    color_space=lv.COLOR_FORMAT.RGB565,
    color_byte_order=ili9341.BYTE_ORDER_BGR,
    rgb565_byte_swap=True,
    reset_pin=LCD_RST,
    reset_state=ili9341.STATE_LOW,
    backlight_pin=LCD_BL,
    backlight_on_state=ili9341.STATE_PWM
)
mpos.ui.main_display.init(LCD_TYPE)
mpos.ui.main_display.set_power(True)
mpos.ui.main_display.set_color_inversion(True)
mpos.ui.main_display.set_backlight(25)

lv.init()

# Button handling code:
from machine import Pin
import time

btn_a = Pin(39, Pin.IN, Pin.PULL_UP) # A
btn_b = Pin(38, Pin.IN, Pin.PULL_UP) # B
btn_c = Pin(37, Pin.IN, Pin.PULL_UP) # C

# Key repeat configuration
# This whole debounce logic is only necessary because LVGL 9.2.2 seems to have an issue where
# the lv_keyboard widget doesn't handle PRESSING (long presses) properly, it loses focus.
REPEAT_INITIAL_DELAY_MS = 300  # Delay before first repeat
REPEAT_RATE_MS = 100  # Interval between repeats
last_key = None
last_state = lv.INDEV_STATE.RELEASED
key_press_start = 0  # Time when key was first pressed
last_repeat_time = 0  # Time of last repeat event

# Read callback
# Warning: This gets called several times per second, and if it outputs continuous debugging on the serial line,
# that will break tools like mpremote from working properly to upload new files over the serial line, thus needing a reflash.
def keypad_read_cb(indev, data):
    global last_key, last_state, key_press_start, last_repeat_time
    since_last_repeat = 0

    # Check buttons
    current_key = None
    current_time = time.ticks_ms()
    if btn_a.value() == 0:
        current_key = lv.KEY.PREV
    elif btn_b.value() == 0:
        current_key = lv.KEY.ENTER
    elif btn_c.value() == 0:
        current_key = lv.KEY.NEXT

    if (btn_a.value() == 0) and (btn_c.value() == 0):
        current_key = lv.KEY.ESC

    # Key repeat logic
    if current_key:
        if current_key != last_key:
            # New key press
            data.key = current_key
            data.state = lv.INDEV_STATE.PRESSED
            last_key = current_key
            last_state = lv.INDEV_STATE.PRESSED
            key_press_start = current_time
            last_repeat_time = current_time
        else: # same key
            # Key held: Check for repeat
            elapsed = time.ticks_diff(current_time, key_press_start)
            since_last_repeat = time.ticks_diff(current_time, last_repeat_time)
            if elapsed >= REPEAT_INITIAL_DELAY_MS and since_last_repeat >= REPEAT_RATE_MS:
                # Send a new PRESSED/RELEASED pair for repeat
                data.key = current_key
                data.state = lv.INDEV_STATE.PRESSED if last_state == lv.INDEV_STATE.RELEASED else lv.INDEV_STATE.RELEASED
                last_state = data.state
                last_repeat_time = current_time
            else:
                # No repeat yet, send RELEASED to avoid PRESSING
                data.state = lv.INDEV_STATE.RELEASED
                last_state = lv.INDEV_STATE.RELEASED
    else:
        # No key pressed
        data.key = last_key if last_key else lv.KEY.ENTER
        data.state = lv.INDEV_STATE.RELEASED
        last_key = None
        last_state = lv.INDEV_STATE.RELEASED
        key_press_start = 0
        last_repeat_time = 0

    # Handle ESC for back navigation (only on initial PRESSED)
    if last_state == lv.INDEV_STATE.PRESSED:
        if current_key == lv.KEY.ESC and since_last_repeat == 0:
            mpos.ui.back_screen()

group = lv.group_create()
group.set_default()

# Create and set up the input device
indev = lv.indev_create()
indev.set_type(lv.INDEV_TYPE.KEYPAD)
indev.set_read_cb(keypad_read_cb)
indev.set_group(group) # is this needed? maybe better to move the default group creation to main.py so it's available everywhere...
disp = lv.display_get_default()  # NOQA
indev.set_display(disp)  # different from display
indev.enable(True)  # NOQA
InputManager.register_indev(indev)

print("m5stack_fire.py finished")
