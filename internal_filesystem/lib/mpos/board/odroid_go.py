print("odroid_go.py initialization")

# Hardware initialization for Hardkernel ODROID-Go
# https://github.com/hardkernel/ODROID-GO/
# https://wiki.odroid.com/odroid_go/odroid_go
# Original author: https://github.com/jedie

import time

import drivers.display.ili9341 as ili9341
import lcd_bus
import lvgl as lv
import machine
import mpos.ui
from machine import ADC, PWM, Pin
from micropython import const
from mpos import AudioManager, BatteryManager, InputManager

# Display settings:
SPI_HOST = const(1)
SPI_FREQ = const(40000000)

LCD_SCLK = const(18)
LCD_MOSI = const(23)
LCD_DC = const(21)
LCD_CS = const(5)
LCD_BL = const(32)
LCD_RST = const(33)
LCD_TYPE = const(2)  # ILI9341 type 2

TFT_VER_RES = const(320)
TFT_HOR_RES = const(240)


# Button settings:
BUTTON_MENU = const(13)
BUTTON_VOLUME = const(0)
BUTTON_SELECT = const(27)
BUTTON_START = const(39)

BUTTON_B = const(33)
BUTTON_A = const(32)

# The crossbar pin numbers:
CROSSBAR_X = const(34)
CROSSBAR_Y = const(35)


# Misc settings:
LED_BLUE = const(2)
BATTERY_PIN = const(36)

# Buzzer
BUZZER_PIN = const(26)
BUZZER_DAC_PIN = const(25)
BUZZER_TONE_CHANNEL = const(0)


print("odroid_go.py turn on blue LED")
blue_led = machine.Pin(LED_BLUE, machine.Pin.OUT)
blue_led.on()

print("odroid_go.py init buzzer")
buzzer = PWM(Pin(BUZZER_PIN, Pin.OUT, value=1), duty=5)


class BuzzerCallbacks:
    __slots__ = ("dac_pin",)

    def __init__(self):
        self.dac_pin = Pin(BUZZER_DAC_PIN, Pin.OUT, value=1)

    def unmute(self):
        print("Unmute buzzer")
        self.dac_pin.value(1)  # Unmute

    def mute(self):
        print("Mute buzzer")
        self.dac_pin.value(0)  # Mute


buzzer_callbacks = BuzzerCallbacks()
AudioManager(
    i2s_pins=None,
    buzzer_instance=buzzer,
    # The buzzer makes noise when it's unmuted, to avoid this we
    # mute it after playback and vice versa unmute it before playback:
    pre_playback=buzzer_callbacks.unmute,
    post_playback=buzzer_callbacks.mute,
)
AudioManager.set_volume(40)
AudioManager.play_rtttl("Star Trek:o=4,d=20,b=200:8f.,a#,4d#6.,8d6,a#.,g.,c6.,4f6")
while AudioManager.is_playing():
    time.sleep(0.1)

print("odroid_go.py machine.SPI.Bus() initialization")
try:
    spi_bus = machine.SPI.Bus(host=SPI_HOST, mosi=LCD_MOSI, sck=LCD_SCLK)
except Exception as e:
    print(f"Error initializing SPI bus: {e}")
    print("Attempting hard reset in 3sec...")
    time.sleep(3)
    machine.reset()

print("odroid_go.py lcd_bus.SPIBus() initialization")
display_bus = lcd_bus.SPIBus(spi_bus=spi_bus, freq=SPI_FREQ, dc=LCD_DC, cs=LCD_CS)

print("odroid_go.py ili9341.ILI9341() initialization")
try:
    mpos.ui.main_display = ili9341.ILI9341(
        data_bus=display_bus,
        display_width=TFT_HOR_RES,
        display_height=TFT_VER_RES,
        color_space=lv.COLOR_FORMAT.RGB565,
        color_byte_order=ili9341.BYTE_ORDER_BGR,
        rgb565_byte_swap=True,
        reset_pin=LCD_RST,
        reset_state=ili9341.STATE_LOW,
        backlight_pin=LCD_BL,
        backlight_on_state=ili9341.STATE_PWM,
    )
except Exception as e:
    print(f"Error initializing ILI9341: {e}")
    print("Attempting hard reset in 3sec...")
    time.sleep(3)
    machine.reset()

print("odroid_go.py display.init()")
mpos.ui.main_display.init(type=LCD_TYPE)
mpos.ui.main_display.set_rotation(lv.DISPLAY_ROTATION._270)
mpos.ui.main_display.set_power(True)
mpos.ui.main_display.set_color_inversion(False)
mpos.ui.main_display.set_backlight(25)

print("odroid_go.py lv.init() initialization")
lv.init()


print("odroid_go.py Battery initialization...")


def adc_to_voltage(raw_adc_value):
    """
    The percentage calculation uses MIN_VOLTAGE = 3.15 and MAX_VOLTAGE = 4.15
    0% at 3.15V -> raw_adc_value = 210
    100% at 4.15V -> raw_adc_value = 310

    4.15 - 3.15 = 1V
    310 - 210 = 100 raw ADC steps

    So each raw ADC step is 1V / 100 = 0.01V
    Offset calculation:
    210 * 0.01 = 2.1V. but we want it to be 3.15V
    So the offset is 3.15V - 2.1V = 1.05V
    """
    voltage = raw_adc_value * 0.01 + 1.05
    return voltage


BatteryManager.init_adc(BATTERY_PIN, adc_to_voltage)


print("odroid_go.py button initialization...")

button_menu = Pin(BUTTON_MENU, Pin.IN, Pin.PULL_UP)
button_volume = Pin(BUTTON_VOLUME, Pin.IN, Pin.PULL_UP)
button_select = Pin(BUTTON_SELECT, Pin.IN, Pin.PULL_UP)
button_start = Pin(BUTTON_START, Pin.IN, Pin.PULL_UP)  # -> ENTER

# PREV <- B | A -> NEXT
button_b = Pin(BUTTON_B, Pin.IN, Pin.PULL_UP)
button_a = Pin(BUTTON_A, Pin.IN, Pin.PULL_UP)


class CrossbarHandler:
    # ADC values are around low: ~236 and high ~511
    # So the mid value is around (236+511)/2 = 373.5
    CROSSBAR_MIN_ADC_LOW = const(100)
    CROSSBAR_MIN_ADC_MID = const(370)

    def __init__(self, pin, high_key, low_key):
        self.adc = ADC(Pin(pin, mode=Pin.IN))
        self.adc.width(ADC.WIDTH_9BIT)
        self.adc.atten(ADC.ATTN_11DB)

        self.high_key = high_key
        self.low_key = low_key

    def poll(self):
        value = self.adc.read()
        if value > self.CROSSBAR_MIN_ADC_LOW:
            if value > self.CROSSBAR_MIN_ADC_MID:
                return self.high_key
            elif value < self.CROSSBAR_MIN_ADC_MID:
                return self.low_key


class Crossbar:
    def __init__(self, *, up, down, left, right):
        self.joy_x = CrossbarHandler(CROSSBAR_X, high_key=left, low_key=right)
        self.joy_y = CrossbarHandler(CROSSBAR_Y, high_key=up, low_key=down)

    def poll(self):
        crossbar_pressed = self.joy_x.poll() or self.joy_y.poll()
        return crossbar_pressed


# see: internal_filesystem/lib/drivers/indev/sdl_keyboard.py
#         lv.KEY.UP
# lv.KEY.LEFT - lv.KEY.RIGHT
#         lv.KEY.DOWN
#
crossbar = Crossbar(
    up=lv.KEY.UP, down=lv.KEY.DOWN, left=lv.KEY.LEFT, right=lv.KEY.RIGHT
)

REPEAT_INITIAL_DELAY_MS = 300  # Delay before first repeat
REPEAT_RATE_MS = 100  # Interval between repeats
next_repeat = None  # Used for auto-repeat key handling


def input_callback(indev, data):
    global next_repeat

    current_key = None

    if crossbar_pressed := crossbar.poll():
        current_key = crossbar_pressed

    elif button_menu.value() == 0:
        current_key = lv.KEY.ESC
    elif button_volume.value() == 0:
        print("Volume button pressed -> reset")
        blue_led.on()
        AudioManager.play_rtttl(
            "Outro:o=5,d=32,b=160,b=160:c6,b,a,g,f,e,d,c",
            stream_type=AudioManager.STREAM_ALARM,
            volume=40,
        )
        while AudioManager.is_playing():
            time.sleep(0.1)
        machine.reset()
    elif button_select.value() == 0:
        current_key = lv.KEY.BACKSPACE
    elif button_start.value() == 0:
        current_key = lv.KEY.ENTER

    elif button_b.value() == 0:
        current_key = lv.KEY.PREV
    elif button_a.value() == 0:
        current_key = lv.KEY.NEXT
    else:
        # No crossbar/buttons pressed
        if data.key:  # A key was previously pressed and now released
            # print(f"Key {data.key=} released")
            data.key = 0
            data.state = lv.INDEV_STATE.RELEASED
            next_repeat = None
            blue_led.off()
        return

    # A key is currently pressed

    blue_led.on()  # Blink on key press and auto repeat for feedback

    current_time = time.ticks_ms()
    repeat = current_time > next_repeat if next_repeat else False  # Auto repeat?
    if repeat or current_key != data.key:
        print(f"Key {current_key} pressed {repeat=}")

        data.key = current_key
        data.state = lv.INDEV_STATE.PRESSED

        if current_key == lv.KEY.ESC:  # Handle ESC for back navigation
            mpos.ui.back_screen()
        elif current_key == lv.KEY.RIGHT:
            mpos.ui.focus_direction.move_focus_direction(90)
        elif current_key == lv.KEY.LEFT:
            mpos.ui.focus_direction.move_focus_direction(270)
        elif current_key == lv.KEY.UP:
            mpos.ui.focus_direction.move_focus_direction(0)
        elif current_key == lv.KEY.DOWN:
            mpos.ui.focus_direction.move_focus_direction(180)

        if not repeat:
            # Initial press: Delay before first repeat
            next_repeat = current_time + REPEAT_INITIAL_DELAY_MS
        else:
            # Faster auto repeat after initial press
            next_repeat = current_time + REPEAT_RATE_MS
            blue_led.off()  # Blink the LED, too


group = lv.group_create()
group.set_default()

# Create and set up the input device
indev = lv.indev_create()
indev.set_type(lv.INDEV_TYPE.KEYPAD)
indev.set_read_cb(input_callback)
indev.set_group(
    group
)  # is this needed? maybe better to move the default group creation to main.py so it's available everywhere...
disp = lv.display_get_default()  # NOQA
indev.set_display(disp)  # different from display
indev.enable(True)  # NOQA
InputManager.register_indev(indev)

print("odroid_go.py finished")
