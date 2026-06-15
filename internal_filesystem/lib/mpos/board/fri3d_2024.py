# Hardware initialization for Fri3d Camp 2024 Badge
import logging

logger = logging.getLogger(__name__)

from machine import Pin
import lcd_bus
import machine
import math


import lvgl as lv

import drivers.display.st7789 as st7789

import mpos.ui
import mpos.ui.focus_direction
from mpos import InputManager, IRManager

spi_bus = machine.SPI.Bus(
    host=2,
    mosi=6,
    miso=8, # not connected to the display, only to the SD card, so can't read from it
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

# see ./lvgl_micropython/api_drivers/py_api_drivers/frozen/display/display_driver_framework.py
mpos.ui.main_display = st7789.ST7789(
    data_bus=display_bus,
    frame_buffer1=fb1,
    frame_buffer2=fb2,
    display_width=240,
    display_height=296,
    color_space=lv.COLOR_FORMAT.RGB565,
    color_byte_order=st7789.BYTE_ORDER_BGR,
    rgb565_byte_swap=True,
    reset_pin=48,
    reset_state=0
)

mpos.ui.main_display.init()
mpos.ui.main_display.set_power(True)
mpos.ui.main_display.set_backlight(100)
mpos.ui.main_display.set_color_inversion(False)

lv.init()
mpos.ui.main_display.set_rotation(lv.DISPLAY_ROTATION._270) # must be done after initializing display and creating the touch drivers, to ensure proper handling
mpos.ui.main_display.set_params(0x36, bytearray([0x28])) # mirror

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

    # Normalize to [-1, 1]
    x = (val_left_right - 2048) / 2048  # Positive x = RIGHT
    y = (val_up_down - 2048) / 2048    # Positive y = UP
    #if time.time() < 60:

    # Check if joystick is near center
    magnitude = math.sqrt(x*x + y*y)
    #if time.time() < 60:
    if magnitude < threshold:
        return None  # Neutral position

    # Calculate angle in degrees with UP = 0°, clockwise
    angle_rad = math.atan2(x, y)
    angle_deg = math.degrees(angle_rad)
    angle_deg = (angle_deg + 360) % 360  # Normalize to [0, 360)
    return angle_deg

# Repeat timing for navigation actions (same as LVGL indev timing for consistency)
LONG_PRESS_TIME = const(400)
LONG_PRESS_REPEAT_TIME = const(100)
_last_key = None
_next_repeat_at = 0

# Read callback
# Warning: This gets called several times per second, and if it outputs continuous debugging on the serial line,
# that will break tools like mpremote from working properly to upload new files over the serial line, thus needing a reflash.
def keypad_read_cb(indev, data):
    global _last_key, _next_repeat_at
    current_key = None

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
                logger.warning("WARNING: unhandled joystick angle %s" % (angle))

    data.continue_reading = False

    if current_key is not None:
        data.key = current_key
        data.state = lv.INDEV_STATE.PRESSED
        now = time.ticks_ms()

        if current_key != _last_key:
            _last_key = current_key
            _next_repeat_at = now + LONG_PRESS_TIME
            should_act = True
        elif time.ticks_diff(now, _next_repeat_at) >= 0:
            _next_repeat_at = now + LONG_PRESS_REPEAT_TIME
            should_act = True
        else:
            should_act = False

        if should_act:
            if __debug__: logger.debug("key: %s" % (current_key))
            if current_key == lv.KEY.ESC:
                mpos.ui.back_screen()
            elif current_key == lv.KEY.HOME:
                from mpos.ui import topmenu as topmenu
                topmenu.toggle_drawer()
            elif current_key == lv.KEY.RIGHT:
                mpos.ui.focus_direction.move_focus_direction(90)
            elif current_key == lv.KEY.LEFT:
                mpos.ui.focus_direction.move_focus_direction(270)
            elif current_key == lv.KEY.UP:
                mpos.ui.focus_direction.move_focus_direction(0)
            elif current_key == lv.KEY.DOWN:
                mpos.ui.focus_direction.move_focus_direction(180)

        _last_key = current_key
    else:
        data.key = _last_key if _last_key is not None else lv.KEY.ENTER
        data.state = lv.INDEV_STATE.RELEASED
        _last_key = None
        _next_repeat_at = 0

group = lv.group_get_default()

# Create and set up the input device
indev = lv.indev_create()
indev.set_type(lv.INDEV_TYPE.KEYPAD)
indev.set_read_cb(keypad_read_cb)
indev.set_group(group) # is this needed? maybe better to move the default group creation to main.py so it's available everywhere...
disp = lv.display_get_default()
indev.set_display(disp)  # different from display
indev.enable(True)
indev.set_long_press_time(LONG_PRESS_TIME)
indev.set_long_press_repeat_time(LONG_PRESS_REPEAT_TIME)
InputManager.register_indev(indev)

import mpos.sdcard
mpos.sdcard.init(spi_bus=spi_bus, cs_pin=14)

IRManager.txPin = Pin(13, Pin.OUT) # IO10 is "blaster" but this doesn't control the IR LED directly, it takes "Link Packets"
IRManager.rxPin = Pin(11, Pin.IN)

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

# === AUDIO HARDWARE ===
from mpos import AudioManager

# Would be better to only add these if the communicator is connected:

# I2S pin configuration for audio output (DAC) and input (microphone)
# Note: I2S is created per-stream, not at boot (only one instance can exist)
# The DAC uses BCK (bit clock) on GPIO 2, while the microphone uses SCLK on GPIO 17
# See schematics: DAC has BCK=2, WS=47, SD=16; Microphone has SCLK=17, WS=47, DIN=15
i2s_output_pins = {
    'ws': 47,       # Word Select / LRCLK shared between DAC and mic (mandatory)
    'sck': 2,       # SCLK or BCLK - Bit Clock for DAC output (mandatory)
    'sd': 16,       # Serial Data OUT (speaker/DAC)
}

i2s_input_pins = {
    'ws': 47,       # Word Select / LRCLK shared between DAC and mic (mandatory)
    'sck_in': 17,   # SCLK - Serial Clock for microphone input
    'sd_in': 15,    # DIN - Serial Data IN (microphone)
}

speaker_output = AudioManager.add(
    AudioManager.Output(
        name="Communicator Output",
        kind="i2s",
        i2s_pins=i2s_output_pins,
    )
)

mic_input = AudioManager.add(
    AudioManager.Input(
        name="Communicator Input",
        kind="i2s",
        i2s_pins=i2s_input_pins,
    )
)

# Add this after the headset output so that it doesn't become the default:
buzzer_output = AudioManager.add(
    AudioManager.Output(
        name="Badge Buzzer",
        kind="buzzer",
        buzzer_pin=46,
    )
)

# === SENSOR HARDWARE ===
from mpos import SensorManager
# Create I2C bus for IMU (different pins from display)
from machine import I2C
imu_i2c = I2C(0, sda=Pin(9), scl=Pin(18))
from mpos import DeviceManager
DeviceManager.registerBus(i2c_bus=imu_i2c) # register because Communicator needs it
SensorManager.init(imu_i2c, address=0x6B, mounted_position=SensorManager.FACING_EARTH)

# === LED HARDWARE ===
import mpos.lights as LightsManager
# Initialize 5 NeoPixel LEDs (GPIO 12)
LightsManager.init(neopixel_pin=12)
LightsManager.set_led_num(5)

# Communicator add-on keyboard input (UART HID reports -> LVGL keypad indev)
try:
    if __debug__: logger.debug("Checking for 2024 or 2026 Communicator Add-On over I2C")
    from machine import UART

    COMMUNICATOR_2024_ADDR = const(0x38)
    COMMUNICATOR_2026_ADDR = const(0x39)

    comm_i2c_bus = DeviceManager.getBus(type="i2c")
    comm_uart = UART(2, baudrate=115200, rx=Pin(44), tx=Pin(43))

    communicator = None
    i2c_devices = comm_i2c_bus.scan()

    if COMMUNICATOR_2026_ADDR in i2c_devices:
        from drivers.fri3d.communicator import Communicator2026
        communicator = Communicator2026(i2c_bus=comm_i2c_bus, uart_bus=comm_uart,use_irq=False)
    elif COMMUNICATOR_2024_ADDR in i2c_devices:
        from drivers.fri3d.communicator import Communicator2024
        communicator = Communicator2024(i2c_bus=comm_i2c_bus,uart_bus=comm_uart,use_irq=False)

    if communicator is not None:
        if __debug__: logger.debug("Disabling UART REPL because it receives data from the Communicator Add-On. Use esp.uart_repl(True) to re-enable.")
        import esp
        esp.uart_repl(False)
        if __debug__: logger.debug("Initializing Fri3dCommunicatorKeyboard and registering as indev")
        from drivers.indev.fri3d_communicator_keyboard import Fri3dCommunicatorKeyboard
        communicator_indev = Fri3dCommunicatorKeyboard(communicator)
        communicator_indev.set_group(group)
        communicator_indev.enable(True)
        InputManager.register_indev(communicator_indev)
except Exception as e:
    logger.error("communicator keyboard init got exception: %s" % (e))

# === STARTUP "WOW" EFFECT ===
import time
import _thread

def startup_wow_effect():
    try:
        # Startup jingle: Happy upbeat sequence (ascending scale with flourish)
        startup_jingle = "Startup:d=8,o=6,b=200:c,d,e,g,4c7,4e,4c7"
        #startup_jingle = "ShortBeeps:d=32,o=5,b=320:c6,c7"

        # Start the jingle
        player = AudioManager.player(
            rtttl=startup_jingle,
            stream_type=AudioManager.STREAM_NOTIFICATION,
            volume=60,
            output=buzzer_output,
        )
        player.start()

        # Rainbow colors for the 5 LEDs
        rainbow = [
            (255, 0, 0),    # Red
            (255, 128, 0),  # Orange
            (255, 255, 0),  # Yellow
            (0, 255, 0),    # Green
            (0, 0, 255),    # Blue
        ]

        # Single rainbow sweep
        for i in range(5):
            # Light up LEDs progressively
            for j in range(i + 1):
                LightsManager.set_led(j, *rainbow[j])
            LightsManager.write()
            time.sleep_ms(500)

        # Hold white, then fade out over 4 seconds
        LightsManager.set_all(255, 255, 255)
        LightsManager.write()
        time.sleep_ms(500)

        fade_steps = 80
        for step in range(fade_steps):
            level = int(255 * (fade_steps - 1 - step) / (fade_steps - 1))
            LightsManager.set_all(level, level, level)
            LightsManager.write()
            time.sleep_ms(25)

    except Exception as e:
        logger.error("Startup effect error: %s" % (e))

from mpos import TaskManager
_thread.stack_size(TaskManager.good_stack_size()) # default stack size won't work, crashes!
_thread.start_new_thread(startup_wow_effect, ())

if __debug__: logger.debug("fri3d_2024.py finished")
