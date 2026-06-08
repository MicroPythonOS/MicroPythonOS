"""
Hardware initialization for the unPhone 9
https://unphone.net/

Based on C++ implementation (unPhone.h, unPhone.cpp) from:
https://gitlab.com/hamishcunningham/unphonelibrary/

other references:
https://gitlab.com/hamishcunningham/unphone/-/blob/master/examples/circuitpython/LCD.py
https://www.espboards.dev/esp32/unphone9/
https://github.com/espressif/arduino-esp32/blob/master/variants/unphone9/pins_arduino.h
https://github.com/meshtastic/device-ui/blob/master/include/graphics/LGFX/LGFX_UNPHONE.h

Original author: https://github.com/jedie
"""

import logging
logger = logging.getLogger(__name__)

import struct
import sys
import time

import esp32
import i2c
import lcd_bus
import lvgl as lv
import machine
import mpos.ui
from drivers.display.hx8357d import hx8357d
from drivers.indev.xpt2046 import XPT2046
from machine import Pin
from micropython import const
from mpos import InputManager

SDA = const(3)
SCL = const(4)
SCK = const(39)
MOSI = const(40)
MISO = const(41)

SPI_HOST = const(1)  # Shared SPI for hx8357d display and xpt2046 touch controller

# 27Mhz used in extras/port-lvgl/lib9/TFT_eSPI_files/Setup15_HX8357D.h
SPI_LCD_FREQ = const(27_000_000)

# SPI_LCD_FREQ = const(20_000_000)
# SPI_LCD_FREQ = const(10_000_000)
# SPI_LCD_FREQ = const(1_000_000)
I2C_BUS = const(0)
I2C_FREQ = const(100_000)

LCD_CS = const(48)
LCD_DC = const(47)
LCD_RESET = const(46)

LCD_BACKLIGHT = const(2)
# FIXME: Two backlights? One on the TCA9555 expander, one directly controlled by the ESP32?
BACKLIGHT = const(0x42)

TFT_WIDTH = const(320)
TFT_HEIGHT = const(480)

TOUCH_I2C_ADDR = const(106)
TOUCH_REGBITS = const(8)
TOUCH_CS = const(38)

# 2,5Mhz used in extras/port-lvgl/lib9/TFT_eSPI_files/Setup15_HX8357D.h
SPI_TOUCH_FREQ = const(2_500_000)

# SPI_TOUCH_FREQ = const(500_000)
# SPI_TOUCH_FREQ = const(100_000)
EXPANDER_POWER = const(0x40)
LED_GREEN = const(0x49)
LED_BLUE = const(0x4D)
LED_RED = const(13)

BM_I2C_ADDR = const(107)

# Power management (known variously as PMU, BMU or just BM):
LORA_CS = const(44)
LORA_RESET = const(42)
SD_CS = const(43)
VIBE = const(0x47)
IR_LEDS = const(12)
USB_VSENSE = const(78)

POWER_SWITCH = const(18)
BUTTON_LEFT = const(45)
BUTTON_MIDDLE = const(0)
BUTTON_RIGHT = const(21)


if __debug__: logger.debug("turn on red LED")
machine.Pin(LED_RED, machine.Pin.OUT).on()
time.sleep(1)
if __debug__: logger.debug("init...")


class UnPhoneTCA:
    I2C_DEV_ID = const(38)

    # Register addresses
    REG_INPUT = const(0x00)
    REG_OUTPUT = const(0x02)
    REG_CONFIG = const(0x06)

    def __init__(self, i2c_bus: i2c.I2C.Bus):
        self.tca_dev = i2c.I2C.Device(bus=i2c_bus, dev_id=self.I2C_DEV_ID)
        self.directions = 0xFFFF
        self.output_states = 0x0000

        # Set IO expander initially as all inputs
        self._write_word(0x06, self.directions)

        # Read current directions and states
        self.directions = self._read_word(0x06)
        self.output_states = self._read_word(0x02)

    def _write_word(self, reg, value):
        if __debug__: logger.debug("Writing to TCA9555: reg=%#02x, value=%#04x", reg, value)
        self.tca_dev.write(bytes([reg, value & 0xFF, (value >> 8) & 0xFF]))

    def _read_word(self, reg):
        self.tca_dev.write(bytes([reg]))
        data = self.tca_dev.read(2)
        return struct.unpack("<H", data)[0]

    def pin_mode(self, pin, mode):
        if pin & 0x40:
            pin &= 0xBF
            if mode == machine.Pin.OUT:
            # Ensure pin is set to output
                self.directions &= ~(1 << pin)
            else:
            # Ensure pin is set to input
                self.directions |= 1 << pin
            self._write_word(self.REG_OUTPUT, self.directions)
        else:
            # Handle standard ESP32 pin
            machine.Pin(pin, mode)

    def digital_write(self, pin, value):
        if pin & 0x40:
            pin &= 0xBF
            if value:
                self.output_states |= 1 << pin
            else:
                self.output_states &= ~(1 << pin)
            self._write_word(self.REG_OUTPUT, self.output_states)

            self.directions &= ~(1 << pin)
            self._write_word(self.REG_CONFIG, self.directions)
        else:
            # Handle standard ESP32 pin
            p = machine.Pin(pin, machine.Pin.OUT)
            p.value(value)

    def digital_read(self, pin):
        if pin & 0x40:
            pin &= 0xBF
            self.directions |= 1 << pin
            self._write_word(self.REG_CONFIG, self.directions)

            inputs = self._read_word(self.REG_INPUT)
            return 1 if (inputs & (1 << pin)) else 0
        else:
            # Handle standard ESP32 pin
            p = machine.Pin(pin, machine.Pin.IN)
            return p.value()


class UnPhone:
    # Power management chip API
    BM_I2CADD = const(0x6B)
    BM_WATCHDOG = const(0x05)
    BM_OPCON = const(0x07)
    BM_STATUS = const(0x08)

    STORE_SIZE = const(10)

    def __init__(self, i2c: i2c.I2C.Bus):
        self.i2c = i2c
        self.tca = UnPhoneTCA(self.i2c)

        # TODO: Persistent Store
        # # https://docs.micropython.org/en/latest/library/esp32.html#esp32.NVS
        # self.nvs = esp32.NVS("unPhoneStore")
        # try:
        #     self.current_store_index = self.nvs.get_i8("unPhoneStoreIdx")
        # except OSError:
        #     self.current_store_index = 0
        self.reset()

    def expander_power(self, *, on):
        if __debug__: logger.debug("Turning Expander power=%s...", on)
        self.tca.digital_write(EXPANDER_POWER, 1 if on else 0)

    def backlight(self, *, on):
        if __debug__: logger.debug("Turning LCD backlight=%s...", on)
        self.tca.digital_write(BACKLIGHT, 1 if on else 0)

    def vibe(self, *, on):
        if __debug__: logger.debug("Turning VIBE=%s...", on)
        self.tca.digital_write(VIBE, 1 if on else 0)

    def ir(self, *, on):
        if __debug__: logger.debug("Turning IR_LEDS=%s...", on)
        self.tca.digital_write(IR_LEDS, 1 if on else 0)

    def rgb(self, r, g, b):
        self.tca.digital_write(LED_RED, 0 if r else 1)
        self.tca.digital_write(LED_GREEN, 0 if g else 1)
        self.tca.digital_write(LED_BLUE, 0 if b else 1)

    # TODO: Storage API
    # def store(self, message):
    #     key = str(self.current_store_index)
    #     self.nvs.set_blob(key, message.encode())
    #     self.current_store_index += 1
    #     if self.current_store_index >= self.STORE_SIZE:
    #         self.current_store_index = 0
    #     self.nvs.set_i8("unPhoneStoreIdx", self.current_store_index)
    #     self.nvs.commit()
    def power_switch_is_on(self):
        return bool(self.tca.digital_read(POWER_SWITCH))

    def usb_power_connected(self):
        status = self.i2c.readfrom_mem(self.BM_I2CADD, self.BM_STATUS, 1)[0]
        connected = bool((status >> 2) & 1)
        if __debug__: logger.debug("USB power connected: %s", connected)
        return connected

    def _wake_on_power_switch(self):
        if __debug__: logger.debug("Configuring ESP32 wake on power switch...")
        wake_pin = machine.Pin(POWER_SWITCH, machine.Pin.IN)
        esp32.wake_on_ext0(pin=wake_pin, level=esp32.WAKEUP_ALL_LOW)

    def set_shipping(self, *, enable):
        if __debug__: logger.debug("Setting shipping mode to: %s", enable)
        wdt = self.i2c.readfrom_mem(self.BM_I2CADD, self.BM_WATCHDOG, 1)[0]
        opcon = self.i2c.readfrom_mem(self.BM_I2CADD, self.BM_OPCON, 1)[0]
        if enable:
            if __debug__: logger.debug("Asks BM chip to powering down and shutting off USB power")
            wdt = wdt & ~(1 << 5) & ~(1 << 4)
            opcon = opcon | (1 << 5)
        else:
            if __debug__: logger.debug("Asks BM chip to power up and enable USB power")
            wdt = (wdt & ~(1 << 5)) | (1 << 4)
            opcon = opcon & ~(1 << 5)
        self.i2c.writeto_mem(self.BM_I2CADD, self.BM_WATCHDOG, bytes([wdt]))
        self.i2c.writeto_mem(self.BM_I2CADD, self.BM_OPCON, bytes([opcon]))

    def turn_peripherals_off(self):
        if __debug__: logger.debug("Turning off peripherals...")
        self.expander_power(on=False)
        self.backlight(on=False)
        self.ir(on=False)
        self.rgb(0, 0, 0)

    def turn_off(self):
        if __debug__: logger.debug("turning unPhone off...")
        self.turn_peripherals_off()
        if not self.usb_power_connected():
            if __debug__: logger.debug("switch is off, power is OFF: going to shipping mode")
            self.set_shipping(enable=True)
        else:
            if __debug__: logger.debug("switch is off, but power is ON: going to deep sleep")
            self._wake_on_power_switch()
            machine.deepsleep(60000)

    def check_power_switch(self):
        if not self.power_switch_is_on():
            if __debug__: logger.debug("Power switch is OFF, initiating shutdown sequence...")
            self.turn_off()

    def reset(self):
        if __debug__: logger.debug("Resetting unPhone TCA9555 to default state...")

        # Setup pins:
        self.tca.pin_mode(EXPANDER_POWER, machine.Pin.OUT)
        self.tca.pin_mode(VIBE, machine.Pin.OUT)
        self.tca.pin_mode(BUTTON_LEFT, machine.Pin.IN)
        self.tca.pin_mode(BUTTON_MIDDLE, machine.Pin.IN)
        self.tca.pin_mode(BUTTON_RIGHT, machine.Pin.IN)
        self.tca.pin_mode(IR_LEDS, machine.Pin.OUT)
        self.tca.pin_mode(LED_RED, machine.Pin.OUT)
        self.tca.pin_mode(LED_GREEN, machine.Pin.OUT)
        self.tca.pin_mode(LED_BLUE, machine.Pin.OUT)

        # Initialise unPhone hardware to default state:
        self.backlight(on=True)
        self.expander_power(on=True)
        self.vibe(on=False)
        self.ir(on=False)

        # Mute devices on the SPI bus by deselecting them:
        for pin in [LCD_CS, TOUCH_CS, LORA_CS, SD_CS]:
            machine.Pin(pin, machine.Pin.OUT, value=1)

    # Short delay to help things settle
        time.sleep_ms(200)

        # Turn RGB LED blue to indicate reset is done:
        self.rgb(0, 0, 1)


def recover_i2c():
    if __debug__: logger.debug("try to recover I2C bus in case it's locked up...")
    scl = machine.Pin(SCL, machine.Pin.OUT)
    sda = machine.Pin(SDA, machine.Pin.OUT)
    sda.value(1)

    for _ in range(10):
        scl.value(1)
        time.sleep_us(5)
        scl.value(0)
        time.sleep_us(5)

    # STOP signal (SDA from low to high while SCL is high)
    sda.value(0)
    time.sleep_us(5)
    scl.value(1)
    time.sleep_us(2)
    sda.value(1)
    time.sleep_us(2)

    time.sleep_ms(200)


try:
    recover_i2c()
    if __debug__: logger.debug("init i2c Bus with: scl=%s, sda=%s...", SCL, SDA)
    i2c_bus = i2c.I2C.Bus(
        host=I2C_BUS, scl=SCL, sda=SDA, freq=I2C_FREQ, use_locks=False
        # debug=True,
    )
except Exception as e:
    sys.print_exception(e)
    logger.error("Attempting hard reset in 3sec...")
    time.sleep(3)
    machine.reset()
else:
    if __debug__: logger.debug("Scanning I2C bus for devices...")
    for dev in i2c_bus.scan():
        if __debug__: logger.debug("Found I2C device at address: %s ($%#02X)", dev, dev)

    # Typical output here is:
    # Found I2C device at address: 38 ($0x26) -> TCA9555 IO expansion chip
    # Found I2C device at address: 106 ($0x6A) -> Touchscreen controller
    # Found I2C device at address: 107 ($0x6B) -> Power management unit (PMU/BMU)
    unphone = UnPhone(i2c=i2c_bus)


# Manually set MISO pin to input with pull-up to avoid it floating and causing issues on the SPI bus,
# since it's shared between display and touch controller:
Pin(MISO, Pin.IN, Pin.PULL_UP)


if __debug__: logger.debug("shared SPI bus initialization")
time.sleep_ms(200)
try:
    spi_bus = machine.SPI.Bus(host=SPI_HOST, sck=SCK, mosi=MOSI, miso=MISO)
except Exception as e:
    sys.print_exception(e)
    logger.error("Attempting hard reset in 3sec...")
    time.sleep(3)
    machine.reset()


if __debug__: logger.debug("HX8357D() display initialization")
try:
    display_bus = lcd_bus.SPIBus(
        spi_bus=spi_bus,
        freq=SPI_LCD_FREQ,
        dc=LCD_DC,
        cs=LCD_CS,
    )
    mpos.ui.main_display = hx8357d.HX8357D(
        data_bus=display_bus,
        display_width=TFT_WIDTH,
        display_height=TFT_HEIGHT,
        color_space=lv.COLOR_FORMAT.RGB565,
        color_byte_order=hx8357d.BYTE_ORDER_BGR,
        rgb565_byte_swap=True,
        reset_pin=LCD_RESET,
        reset_state=hx8357d.STATE_LOW,
        backlight_pin=LCD_BACKLIGHT,
        backlight_on_state=hx8357d.STATE_PWM,
    )
except Exception as e:
    sys.print_exception(e)
    logger.error("Attempting hard reset in 3sec...")
    time.sleep(3)
    machine.reset()


if __debug__: logger.debug("display.init()")
mpos.ui.main_display.init()

if __debug__: logger.debug("XPT2046() touch controller initialization")
time.sleep_ms(200)
startup_rotation = lv.DISPLAY_ROTATION._0
try:
    touch_dev = machine.SPI.Device(
        spi_bus=spi_bus,
        freq=SPI_TOUCH_FREQ,
        cs=TOUCH_CS,
    )
except Exception as e:
    sys.print_exception(e)
    logger.error("Attempting hard reset in 3sec...")
    time.sleep(3)
    machine.reset()
else:
    if __debug__: logger.debug("init touch...")
    touch_input_dev = XPT2046(
        device=touch_dev,
        lcd_cs=LCD_CS,
        touch_cs=TOUCH_CS,
        display_width=TFT_WIDTH,
        display_height=TFT_HEIGHT,
        startup_rotation=startup_rotation,
    )
    if __debug__: logger.debug("touch_input_dev.is_calibrated=%s", touch_input_dev.is_calibrated)
    #     touch_input_dev.calibrate()
    # else:
    # FIXME: Persistent calibration data is not working yet?
    # if touch_input_dev.is_calibrated:
    InputManager.register_indev(touch_input_dev)


if __debug__: logger.debug("display.set_rotation() initialization")
mpos.ui.main_display.set_rotation(
    startup_rotation
)


if __debug__: logger.debug("button initialization...")
button_left = Pin(BUTTON_LEFT, Pin.IN, Pin.PULL_UP)
button_middle = Pin(BUTTON_MIDDLE, Pin.IN, Pin.PULL_UP)
button_right = Pin(BUTTON_RIGHT, Pin.IN, Pin.PULL_UP)


REPEAT_INITIAL_DELAY_MS = 300
REPEAT_RATE_MS = 100
next_repeat = None
last_power_switch = None
next_check = time.time() + 1


def input_callback(indev, data):
    global next_repeat, last_power_switch, next_check

    current_key = None

    if button_left.value() == 0:
        current_key = lv.KEY.ESC
    elif button_middle.value() == 0:
        current_key = lv.KEY.NEXT
    elif button_right.value() == 0:
        current_key = lv.KEY.ENTER

    else:
        if data.key:
        # No buttons pressed
            data.key = 0
            data.state = lv.INDEV_STATE.RELEASED
            next_repeat = None

        if time.time() > next_check:
            # Check power switch state and update backlight accordingly
            unphone.check_power_switch()
            next_check = time.time() + 1

        return

    # A key is currently pressed
    current_time = time.ticks_ms()
    repeat = current_time > next_repeat if next_repeat else False
    if repeat or current_key != data.key:
        if __debug__: logger.debug("Key %s pressed repeat=%s", current_key, repeat)

        data.key = current_key
        data.state = lv.INDEV_STATE.PRESSED

        if current_key == lv.KEY.ESC:
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


group = lv.group_get_default()

# Create and set up the input device
indev = lv.indev_create()
indev.set_type(lv.INDEV_TYPE.KEYPAD)
indev.set_read_cb(input_callback)
indev.set_group(
    group
)
disp = lv.display_get_default()
indev.set_display(disp)
indev.enable(True)
InputManager.register_indev(indev)

unphone.rgb(0, 1, 0)

if __debug__: logger.debug("init finished")
