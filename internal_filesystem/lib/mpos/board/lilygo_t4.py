# Hardware initialization for LilyGo T4 V1.3
# Manufacturer's website at https://github.com/Xinyuan-LilyGO/LilyGo_Txx
# ESP32-D0WDQ6-V3, 4MB Flash, 8MB PSRAM
# Display: ILI9341 320x240 SPI
# Speaker: PWM
# SD Card: SPI

import logging

logger = logging.getLogger(__name__)

if __debug__: logger.debug("lilygo_t4.py running")

import time

import drivers.display.ili9341 as ili9341
import lcd_bus
import lvgl as lv
import machine
import mpos.ui
from machine import Pin
from micropython import const
from mpos import InputManager, BatteryManager, AudioManager
import mpos.sdcard

# Display settings (SPI)
LCD_SPI_BUS = const(1)
LCD_SPI_FREQ = const(40000000)
LCD_SCLK = const(18)
LCD_MOSI = const(23)
LCD_MISO = const(12)
LCD_DC = const(32)
LCD_CS = const(27)
LCD_BL = const(4)
LCD_RST = const(5)
LCD_TYPE = const(1)

TFT_HOR_RES = const(240)
TFT_VER_RES = const(320)

# Button settings:
BUTTON_A = const(39)
BUTTON_B = const(37)
BUTTON_C = const(38)

# SD Card
SD_SPI_BUS = const(2)
SD_SPI_FREQ = const(500000)
SD_MISO = const(2)
SD_SCLK = const(14)
SD_MOSI = const(15)
SD_CS = const(13)

# Power ADC
ADC_IN = const(35)

# Buzzer
SPEAKER_PWD = const(19)
SPEAKER_OUT = const(25)

if __debug__: logger.debug("lilygo_t4.py init buzzer")
buzzer_pwd = Pin(SPEAKER_PWD, Pin.OUT, value=1)
buzzer_output = AudioManager.add(AudioManager.Output("buzzer", "buzzer", buzzer_pin=SPEAKER_OUT))

if __debug__: logger.debug("lilygo_t4.py init SPI display")
try:
    display_spi_bus = machine.SPI.Bus(host=LCD_SPI_BUS, sck=LCD_SCLK, mosi=LCD_MOSI, miso=LCD_MISO)
except Exception as e:
    logger.error("Error initializing display SPI bus: %s" % (e))
    if __debug__: logger.debug("Attempting hard reset in 3sec...")
    time.sleep(3)
    machine.reset()

display_bus = lcd_bus.SPIBus(spi_bus=display_spi_bus, freq=LCD_SPI_FREQ, dc=LCD_DC, cs=LCD_CS)

mpos.ui.main_display = ili9341.ILI9341(
    data_bus=display_bus,
    display_width=TFT_HOR_RES,
    display_height=TFT_VER_RES,
    reset_pin=LCD_RST,
    reset_state=ili9341.STATE_LOW,
    backlight_pin=LCD_BL,
    backlight_on_state=ili9341.STATE_PWM,
    color_space=lv.COLOR_FORMAT.RGB565,
    color_byte_order=ili9341.BYTE_ORDER_BGR,
    rgb565_byte_swap=True,
) # this will trigger lv.init()

mpos.ui.main_display.init(LCD_TYPE)
mpos.ui.main_display.set_power(True)
mpos.ui.main_display.set_backlight(25)
mpos.ui.main_display.set_rotation(lv.DISPLAY_ROTATION._90)

if __debug__: logger.debug("lilygo_t4.py init battery monitoring")
VOLTAGE_REF = 3.6
DIVIDER_RATIO = 2.0

def adc_to_voltage(adc_value):
    voltage_pin = (adc_value / 4095.0) * VOLTAGE_REF
    battery_voltage = voltage_pin * DIVIDER_RATIO
    if battery_voltage >= 4.2:
        return 100
    elif battery_voltage <= 3.3:
        return 0
    percentage = (battery_voltage - 3.3) / (4.2 - 3.3) * 100
    return min(100, max(0, round(percentage)))

BatteryManager.init_adc(ADC_IN, adc_to_voltage)

if __debug__: logger.debug("lilygo_t4.py init SPI sdcard")
try:
    sdcard_spi_bus = machine.SPI.Bus(host=SD_SPI_BUS, sck=SD_SCLK, mosi=SD_MOSI, miso=SD_MISO)
    mpos.sdcard.init(spi_bus=sdcard_spi_bus, cs_pin=SD_CS)
except Exception as e:
    logger.error("Error initializing sdcard SPI bus: %s" % (e))

# Button handling code
btn_a = Pin(BUTTON_A, Pin.IN, Pin.PULL_UP)
btn_b = Pin(BUTTON_B, Pin.IN, Pin.PULL_UP)
btn_c = Pin(BUTTON_C, Pin.IN, Pin.PULL_UP)

# Repeat configuration
REPEAT_INITIAL_DELAY_MS = 300
REPEAT_RATE_MS = 100

# Hold A+C for ESC
ESC_HOLD_MS = 700

last_key = None
last_state = lv.INDEV_STATE.RELEASED

key_press_start = 0
last_repeat_time = 0

ac_hold_start = 0
ac_pressed_last = False
esc_sent = False


def keypad_read_cb(indev, data):
    global last_key
    global last_state
    global key_press_start
    global last_repeat_time
    global ac_hold_start
    global ac_pressed_last
    global esc_sent

    current_time = time.ticks_ms()

    # Read button states
    a_pressed = btn_a.value() == 0
    b_pressed = btn_b.value() == 0
    c_pressed = btn_c.value() == 0

    # Get focused object
    focused = None
    group = lv.group_get_default()

    if group:
        focused = group.get_focused()

    focus_keyboard = False
    focus_dropdown = False
    dropdown_open = False

    if focused:

        try:
            cls_name = focused.__class__.__name__.lower()
        except:
            cls_name = ""

        # Keyboard or button matrix
        if (
            isinstance(focused, lv.keyboard)
            or isinstance(focused, lv.buttonmatrix)
            or "keyboard" in cls_name
            or "buttonmatrix" in cls_name
        ):
            focus_keyboard = True

        # Dropdown
        elif isinstance(focused, lv.dropdown):
            focus_dropdown = True

            try:
                dropdown_open = focused.is_open()
            except:
                dropdown_open = False

    # A + C long press -> ESC
    ac_pressed = a_pressed and c_pressed and not b_pressed

    if ac_pressed:
        if not ac_pressed_last:
            ac_hold_start = current_time
            esc_sent = False

        hold_time = time.ticks_diff(current_time, ac_hold_start)

        if hold_time >= ESC_HOLD_MS and not esc_sent:
            data.key = lv.KEY.ESC
            data.state = lv.INDEV_STATE.PRESSED
            last_key = lv.KEY.ESC
            last_state = lv.INDEV_STATE.PRESSED
            esc_sent = True

            try:
                mpos.ui.back_screen()
            except:
                pass

            return
    else:
        ac_hold_start = 0
        esc_sent = False

    ac_pressed_last = ac_pressed

    # Ignore normal keys while A+C is held
    current_key = None

    if not ac_pressed:
        # Keyboard / ButtonMatrix
        if focus_keyboard:
            if a_pressed:
                current_key = lv.KEY.LEFT
            elif b_pressed:
                current_key = lv.KEY.ENTER
            elif c_pressed:
                current_key = lv.KEY.RIGHT

        # Dropdown
        elif focus_dropdown:
            if dropdown_open:
                if a_pressed:
                    current_key = lv.KEY.UP
                elif b_pressed:
                    current_key = lv.KEY.ENTER
                elif c_pressed:
                    current_key = lv.KEY.DOWN
            else:
                if a_pressed:
                    current_key = lv.KEY.PREV
                elif b_pressed:
                    current_key = lv.KEY.ENTER
                elif c_pressed:
                    current_key = lv.KEY.NEXT

        # Normal widgets
        else:
            if a_pressed:
                current_key = lv.KEY.PREV
            elif b_pressed:
                current_key = lv.KEY.ENTER
            elif c_pressed:
                current_key = lv.KEY.NEXT

    # LVGL input processing
    if current_key is None:
        data.key = last_key if last_key is not None else -1
        data.state = lv.INDEV_STATE.RELEASED
        last_key = None
        last_state = lv.INDEV_STATE.RELEASED
        key_press_start = 0
        last_repeat_time = 0
    elif last_key is None or current_key != last_key:
        # New key press
        data.key = current_key
        data.state = lv.INDEV_STATE.PRESSED
        last_key = current_key
        last_state = lv.INDEV_STATE.PRESSED
        key_press_start = current_time
        last_repeat_time = current_time
    else:
        elapsed = time.ticks_diff(
            current_time,
            key_press_start
        )
        since_last_repeat = time.ticks_diff(
            current_time,
            last_repeat_time
        )
        if (
            elapsed >= REPEAT_INITIAL_DELAY_MS and
            since_last_repeat >= REPEAT_RATE_MS
        ):
            # Alternate PRESSED/RELEASED
            next_state = (
                lv.INDEV_STATE.PRESSED
                if last_state == lv.INDEV_STATE.RELEASED
                else lv.INDEV_STATE.RELEASED
            )
            data.key = current_key
            data.state = next_state
            last_state = next_state
            last_repeat_time = current_time
        else:
            data.key = current_key
            data.state = lv.INDEV_STATE.RELEASED
            last_state = lv.INDEV_STATE.RELEASED

group = lv.group_get_default()

# Create and set up the input device
indev = lv.indev_create()
indev.set_type(lv.INDEV_TYPE.KEYPAD)
indev.set_read_cb(keypad_read_cb)
indev.set_group(group) # is this needed? maybe better to move the default group creation to main.py so it's available everywhere...
disp = lv.display_get_default()  # NOQA
indev.set_display(disp)  # different from display
indev.enable(True)  # NOQA
InputManager.register_indev(indev)

def startup_music():
    try:
        startup_jingle = "ShortBeeps:d=32,o=5,b=320:c6,c7"
        player = AudioManager.player(rtttl=startup_jingle, stream_type=AudioManager.STREAM_NOTIFICATION, volume=80, output=buzzer_output)
        player.start()
    except Exception as e:
        logger.error("Startup music error: %s" % (e))

import _thread
from mpos import TaskManager
_thread.stack_size(TaskManager.good_stack_size())
_thread.start_new_thread(startup_music, ())

if __debug__: logger.debug("lilygo_t4.py finished")