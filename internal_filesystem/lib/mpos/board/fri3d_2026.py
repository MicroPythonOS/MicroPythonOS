# Hardware initialization for Fri3d Camp 2026 Badge

# Overview:
# - Touch screen controller is cst816s
# - IMU (LSM6DSO) is different from fri3d_2024 (and address 0x6A instead of 0x6B) but the API seems the same, except different chip ID (0x6C iso 0x6A)
# - I2S audio (communicator) is the same
# - headphone jack microphone is on ESP.IO1
# - CH32X035GxUx over I2C:
#   - battery voltage measurement
#   - analog joystick
#   - digital buttons (X,Y,A,B, MENU)
#   - buzzer
#       - audio DAC emulation using buzzer might be slow or need specific buffered protocol
# - test it on the Waveshare to make sure no syntax / variable errors

from machine import Pin, SPI, SDCard
import lcd_bus
import machine
import i2c
import math

import micropython
import gc

import lvgl as lv
import task_handler

import drivers.display.st7789 as st7789
import drivers.indev.cst816s as cst816s

import mpos.ui
import mpos.ui.focus_direction
from mpos import InputManager

TFT_HOR_RES=320
TFT_VER_RES=240

spi_bus = machine.SPI.Bus(
    host=2,
    mosi=6,
    miso=8,
    sck=7
)
display_bus = lcd_bus.SPIBus(
    spi_bus=spi_bus,
    freq=40000000,
    dc=4,
    cs=5
)

# lv.color_format_get_size(lv.COLOR_FORMAT.RGB565) = 2 bytes per pixel * 320 * 240 px = 153600 bytes
# The default was /10 so 15360 bytes.
# /2 = 76800 shows something on display and then hangs the board
# /2 = 38400 works and pretty high framerate but camera gets ESP_FAIL
# /2 = 19200 works, including camera at 9FPS
# 28800 is between the two and still works with camera!
# 30720 is /5 and is already too much
#_BUFFER_SIZE = const(28800)
buffersize = const(28800)
fb1 = display_bus.allocate_framebuffer(buffersize, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)
fb2 = display_bus.allocate_framebuffer(buffersize, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)

STATE_HIGH = 1
STATE_LOW = 0

# see ./lvgl_micropython/api_drivers/py_api_drivers/frozen/display/display_driver_framework.py
mpos.ui.main_display = st7789.ST7789(
    data_bus=display_bus,
    frame_buffer1=fb1,
    frame_buffer2=fb2,
    display_width=TFT_VER_RES,
    display_height=TFT_HOR_RES,
    color_space=lv.COLOR_FORMAT.RGB565,
    color_byte_order=st7789.BYTE_ORDER_BGR,
    rgb565_byte_swap=True,
    reset_pin=48, # LCD reset: TODO: this is now on the CH32
    reset_state=STATE_LOW # TODO: is this correct?
)

mpos.ui.main_display.init()
mpos.ui.main_display.set_power(True)
mpos.ui.main_display.set_backlight(100)
mpos.ui.main_display.set_color_inversion(False)

# Touch handling:
# touch pad interrupt TP Int is on ESP.IO13
i2c_bus = i2c.I2C.Bus(host=0, scl=18, sda=9, freq=400000, use_locks=False)
touch_dev = i2c.I2C.Device(bus=i2c_bus, dev_id=0x15, reg_bits=8)
try:
    tindev=cst816s.CST816S(touch_dev,startup_rotation=lv.DISPLAY_ROTATION._180) # button in top left, good
    InputManager.register_indev(tindev)
except Exception as e:
    print(f"Touch screen init got exception: {e}")

lv.init()
mpos.ui.main_display.set_rotation(lv.DISPLAY_ROTATION._270) # must be done after initializing display and creating the touch drivers, to ensure proper handling
mpos.ui.main_display.set_params(0x36, bytearray([0x28]))

# Button handling code:
from machine import ADC, Pin
import time

btn_start = Pin(0, Pin.IN, Pin.PULL_UP) # START

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
    data.continue_reading = False
    since_last_repeat = 0

    # Check buttons
    current_key = None
    current_time = time.ticks_ms()

    # Check buttons
    if btn_start.value() == 0:
        current_key = lv.KEY.END

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
        elif current_key == lv.KEY.RIGHT:
            mpos.ui.focus_direction.move_focus_direction(90)
        elif current_key == lv.KEY.LEFT:
            mpos.ui.focus_direction.move_focus_direction(270)
        elif current_key == lv.KEY.UP:
            mpos.ui.focus_direction.move_focus_direction(0)
        elif current_key == lv.KEY.DOWN:
            mpos.ui.focus_direction.move_focus_direction(180)

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

# Battery voltage ADC measuring: sits on PC0 of CH32X035GxUx
from mpos import BatteryManager
def adc_to_voltage(adc_value):
    """
    Convert raw ADC value to battery voltage using calibrated linear function.
    Calibration data shows linear relationship: voltage = -0.0016237 * adc + 8.2035
    This is ~10x more accurate than simple scaling (error ~0.01V vs ~0.1V).
    """
    return (0.001651* adc_value + 0.08709)
#BatteryManager.init_adc(13, adc_to_voltage) # TODO

import mpos.sdcard
mpos.sdcard.init(spi_bus, cs_pin=14)

# === AUDIO HARDWARE ===
from machine import PWM, Pin
from mpos import AudioManager

# Initialize buzzer: now sits on PC14/CC1 of the CH32X035GxUx so needs custom code
#buzzer = PWM(Pin(46), freq=550, duty=0)

# I2S pin configuration for audio output (DAC) and input (microphone)
# Note: I2S is created per-stream, not at boot (only one instance can exist)
# The DAC uses BCK (bit clock) on GPIO 2, while the microphone uses SCLK on GPIO 17
# See schematics: DAC has BCK=2, WS=47, SD=16; Microphone has SCLK=17, WS=47, DIN=15

# This worked briefly, way too loud and with distortion:
i2s_pins = {
    'sck': 2,       # SCLK or BCLK (optional)
    'ws': 47,       # Word Select / LRCLK shared between DAC and mic (mandatory)
    'sd': 16,       # Serial Data OUT (speaker/DAC)
    'sck_in': 17,   # SCLK - Serial Clock for microphone input (optional for audio out)
}

# This is how it should be (untested)
i2s_pins = {
    # Output (DAC/speaker) pins
    'mck': 2,       # MCLK (mandatory)
    #'sck': 17,      # SCLK aka BCLK (optional)
    'ws': 47,       # Word Select / LRCLK shared between DAC and mic (mandatory)
    'sd': 16,       # Serial Data OUT (speaker/DAC)
}

# Initialize AudioManager with I2S (buzzer TODO)
# ADC microphone is on GPIO 1
AudioManager(i2s_pins=i2s_pins, adc_mic_pin=1)

# === SENSOR HARDWARE ===
from mpos import SensorManager
# Create I2C bus for IMU (LSM6DSOTR-C / LSM6DSO)
from machine import I2C
SensorManager.init(i2c_bus, address=0x6A, mounted_position=SensorManager.FACING_EARTH)

# === LED HARDWARE ===
import mpos.lights as LightsManager
# Initialize 5 NeoPixel LEDs (GPIO 12)
LightsManager.init(neopixel_pin=12, num_leds=5)

print("Fri3d hardware: Audio, LEDs, and sensors initialized")

# === STARTUP "WOW" EFFECT ===
import time
import _thread

def startup_wow_effect():
    """
    Epic startup effect with rainbow LED chase and upbeat startup jingle.
    Runs in background thread to avoid blocking boot.
    """
    try:
        # Startup jingle: Happy upbeat sequence (ascending scale with flourish)
        startup_jingle = "Startup:d=8,o=6,b=200:c,d,e,g,4c7,4e,4c7"
        #startup_jingle = "ShortBeeps:d=32,o=5,b=320:c6,c7"

        # Start the jingle
        # Disabled until buzzer works
        #AudioManager.play_rtttl(startup_jingle,stream_type=AudioManager.STREAM_NOTIFICATION,volume=60)

        # Rainbow colors for the 5 LEDs
        rainbow = [
            (255, 0, 0),    # Red
            (255, 128, 0),  # Orange
            (255, 255, 0),  # Yellow
            (0, 255, 0),    # Green
            (0, 0, 255),    # Blue
        ]

        # Rainbow sweep effect (3 passes, getting faster)
        for pass_num in range(3):
            for i in range(5):
                # Light up LEDs progressively
                for j in range(i + 1):
                    LightsManager.set_led(j, *rainbow[j])
                LightsManager.write()
                time.sleep_ms(80 - pass_num * 20)  # Speed up each pass

        # Flash all LEDs bright white
        LightsManager.set_all(255, 255, 255)
        LightsManager.write()
        time.sleep_ms(150)

        # Rainbow finale
        for i in range(5):
            LightsManager.set_led(i, *rainbow[i])
        LightsManager.write()
        time.sleep_ms(300)

        # Fade out
        LightsManager.clear()
        LightsManager.write()

    except Exception as e:
        print(f"Startup effect error: {e}")

from mpos import TaskManager
_thread.stack_size(TaskManager.good_stack_size()) # default stack size won't work, crashes!
_thread.start_new_thread(startup_wow_effect, ())

print("fri3d_2026.py finished")
