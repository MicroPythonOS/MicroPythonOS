# Hardware initialization for Fri3d Camp 2024 Badge
from machine import Pin, SPI, SDCard
import st7789 
import lcd_bus
import machine
import cst816s
import i2c
import math

import micropython
import gc

import lvgl as lv
import task_handler

import mpos.ui
import mpos.ui.focus_direction
from mpos import InputManager

from ..task_manager import TaskManager

# Pin configuration
SPI_BUS = 2
SPI_FREQ = 40000000
#SPI_FREQ = 20000000 # also works but I guess higher is better
LCD_SCLK = 7
LCD_MOSI = 6
LCD_MISO = 8
LCD_DC = 4
LCD_CS = 5
#LCD_BL = 1 # backlight can't be controlled on this hardware
LCD_RST = 48

TFT_HOR_RES=296
TFT_VER_RES=240

spi_bus = machine.SPI.Bus(
    host=SPI_BUS,
    mosi=LCD_MOSI,
    miso=LCD_MISO,
    sck=LCD_SCLK
)
display_bus = lcd_bus.SPIBus(
    spi_bus=spi_bus,
    freq=SPI_FREQ,
    dc=LCD_DC,
    cs=LCD_CS
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
    reset_pin=LCD_RST, # doesn't seem needed
    reset_state=STATE_LOW # doesn't seem needed
)

mpos.ui.main_display.init()
mpos.ui.main_display.set_power(True)
mpos.ui.main_display.set_backlight(100)

mpos.ui.main_display.set_color_inversion(False)

lv.init()
mpos.ui.main_display.set_rotation(lv.DISPLAY_ROTATION._270) # must be done after initializing display and creating the touch drivers, to ensure proper handling
mpos.ui.main_display.set_params(0x36, bytearray([0x28]))

# Button and joystick handling code:
from machine import ADC, Pin
import time

btn_x = Pin(38, Pin.IN, Pin.PULL_UP) # X
btn_y = Pin(41, Pin.IN, Pin.PULL_UP) # Y
btn_a = Pin(39, Pin.IN, Pin.PULL_UP) # A
btn_b = Pin(40, Pin.IN, Pin.PULL_UP) # B
btn_start = Pin(0, Pin.IN, Pin.PULL_UP) # START
btn_menu = Pin(45, Pin.IN, Pin.PULL_UP) # MENU

ADC_KEY_MAP = [
    {'key': 'UP', 'unit': 1, 'channel': 2, 'min': 3072, 'max': 4096},
    {'key': 'DOWN', 'unit': 1, 'channel': 2, 'min': 0, 'max': 1024},
    {'key': 'RIGHT', 'unit': 1, 'channel': 0, 'min': 3072, 'max': 4096},
    {'key': 'LEFT', 'unit': 1, 'channel': 0, 'min': 0, 'max': 1024},
]

# Initialize ADC for the two channels
adc_up_down = ADC(Pin(3))  # ADC1_CHANNEL_2 (GPIO 33)
adc_up_down.atten(ADC.ATTN_11DB)  # 0-3.3V range
adc_left_right = ADC(Pin(1))  # ADC1_CHANNEL_0 (GPIO 36)
adc_left_right.atten(ADC.ATTN_11DB)  # 0-3.3V range

def read_joystick():
    # Read ADC values
    val_up_down = adc_up_down.read()
    val_left_right = adc_left_right.read()

    # Check each key's range
    for mapping in ADC_KEY_MAP:
        adc_val = val_up_down if mapping['channel'] == 2 else val_left_right
        if mapping['min'] <= adc_val <= mapping['max']:
            return mapping['key']
    return None  # No key triggered

# Rotate: UP = 0°, RIGHT = 90°, DOWN = 180°, LEFT = 270°
def read_joystick_angle(threshold=0.1):
    # Read ADC values
    val_up_down = adc_up_down.read()
    val_left_right = adc_left_right.read()

    #if time.time() < 60:
    #    print(f"val_up_down: {val_up_down}")
    #    print(f"val_left_right: {val_left_right}")

    # Normalize to [-1, 1]
    x = (val_left_right - 2048) / 2048  # Positive x = RIGHT
    y = (val_up_down - 2048) / 2048    # Positive y = UP
    #if time.time() < 60:
    #    print(f"x,y = {x},{y}")

    # Check if joystick is near center
    magnitude = math.sqrt(x*x + y*y)
    #if time.time() < 60:
    #    print(f"magnitude: {magnitude}")
    if magnitude < threshold:
        return None  # Neutral position

    # Calculate angle in degrees with UP = 0°, clockwise
    angle_rad = math.atan2(x, y)
    angle_deg = math.degrees(angle_rad)
    angle_deg = (angle_deg + 360) % 360  # Normalize to [0, 360)
    return angle_deg

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

    # Check buttons and joystick
    current_key = None
    current_time = time.ticks_ms()

    # Check buttons
    if btn_x.value() == 0:
        current_key = lv.KEY.ESC
    elif btn_y.value() == 0:
        current_key = ord("Y")
    elif btn_a.value() == 0:
        current_key = lv.KEY.ENTER
    elif btn_b.value() == 0:
        current_key = ord("B")
    elif btn_menu.value() == 0:
        current_key = lv.KEY.HOME
    elif btn_start.value() == 0:
        current_key = lv.KEY.END
    else:
        # Check joystick
        angle = read_joystick_angle(0.30) # 0.25-0.27 is right on the edge so 0.30 should be good
        if angle:
            if angle > 45 and angle < 135:
                current_key = lv.KEY.RIGHT
            elif angle > 135 and angle < 225:
                current_key = lv.KEY.DOWN
            elif angle > 225 and angle < 315:
                current_key = lv.KEY.LEFT
            elif angle < 45 or angle > 315:
                current_key = lv.KEY.UP
            else:
                print(f"WARNING: unhandled joystick angle {angle}") # maybe we could also handle diagonals?

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

# Register the input device with InputManager
InputManager.register_indev(indev)

# Battery voltage ADC measuring
# NOTE: GPIO13 is on ADC2, which requires WiFi to be disabled during reading on ESP32-S3.
# BatteryManager handles this automatically: disables WiFi, reads ADC, reconnects WiFi.
from mpos import BatteryManager
"""
best fit on battery power:
2482 is 4.180
2470 is 4.170
2457 is 4.147
# 2444 is 4.12
2433 is 4.109
2429 is 4.102
2393 is 4.044
2369 is 4.000
2343 is 3.957
2319 is 3.916
2269 is 3.831
2227 is 3.769
"""
def adc_to_voltage(adc_value):
    """
    Convert raw ADC value to battery voltage using calibrated linear function.
    Calibration data shows linear relationship: voltage = -0.0016237 * adc + 8.2035
    This is ~10x more accurate than simple scaling (error ~0.01V vs ~0.1V).
    """
    return (0.001651* adc_value + 0.08709)

BatteryManager.init_adc(13, adc_to_voltage)

import mpos.sdcard
mpos.sdcard.init(spi_bus, cs_pin=14)

# === AUDIO HARDWARE ===
from machine import PWM, Pin
from mpos import AudioFlinger

# Initialize buzzer (GPIO 46)
buzzer = PWM(Pin(46), freq=550, duty=0)

# I2S pin configuration for audio output (DAC) and input (microphone)
# Note: I2S is created per-stream, not at boot (only one instance can exist)
# The DAC uses BCK (bit clock) on GPIO 2, while the microphone uses SCLK on GPIO 17
# See schematics: DAC has BCK=2, WS=47, SD=16; Microphone has SCLK=17, WS=47, DIN=15
i2s_pins = {
    # Output (DAC/speaker) pins
    'sck': 2,       # BCK - Bit Clock for DAC output
    'ws': 47,       # Word Select / LRCLK (shared between DAC and mic)
    'sd': 16,       # Serial Data OUT (speaker/DAC)
    # Input (microphone) pins
    'sck_in': 17,   # SCLK - Serial Clock for microphone input
    'sd_in': 15,    # DIN - Serial Data IN (microphone)
}

# Initialize AudioFlinger with I2S and buzzer
AudioFlinger(i2s_pins=i2s_pins, buzzer_instance=buzzer)

# === LED HARDWARE ===
import mpos.lights as LightsManager

# Initialize 5 NeoPixel LEDs (GPIO 12)
LightsManager.init(neopixel_pin=12, num_leds=5)

# === SENSOR HARDWARE ===
from mpos import SensorManager

# Create I2C bus for IMU (different pins from display)
from machine import I2C
imu_i2c = I2C(0, sda=Pin(9), scl=Pin(18))
SensorManager.init(imu_i2c, address=0x6B, mounted_position=SensorManager.FACING_EARTH)

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
        AudioFlinger.play_rtttl(
            startup_jingle,
            stream_type=AudioFlinger.STREAM_NOTIFICATION,
            volume=60
        )

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

_thread.stack_size(TaskManager.good_stack_size()) # default stack size won't work, crashes!
_thread.start_new_thread(startup_wow_effect, ())

print("fri3d_2024.py finished")
