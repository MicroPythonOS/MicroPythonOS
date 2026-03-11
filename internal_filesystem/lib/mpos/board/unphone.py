print("unphone.py initialization")
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
I2C_FREQ = const(100_000)  # rates > 100k used to trigger an unPhoneTCA bug...?

LCD_CS = const(48)  # Chip select control pin
LCD_DC = const(47)  # Data Command control pin
LCD_RESET = const(46)

# FIXME: Two backlights? One on the TCA9555 expander, one directly controlled by the ESP32?
LCD_BACKLIGHT = const(2)  # 0x02
BACKLIGHT = const(0x42)

TFT_WIDTH = const(320)
TFT_HEIGHT = const(480)

TOUCH_I2C_ADDR = const(106)  # 0x6a - Touchscreen controller
TOUCH_REGBITS = const(8)
TOUCH_CS = const(38)  # Chip select pin (T_CS) of touch screen

# 2,5Mhz used in extras/port-lvgl/lib9/TFT_eSPI_files/Setup15_HX8357D.h
SPI_TOUCH_FREQ = const(2_500_000)
# SPI_TOUCH_FREQ = const(500_000)
# SPI_TOUCH_FREQ = const(100_000)

EXPANDER_POWER = const(0x40)
LED_GREEN = const(0x49)
LED_BLUE = const(0x4D)  # 13 | 0x40
LED_RED = const(13)

# Power management (known variously as PMU, BMU or just BM):
BM_I2C_ADDR = const(107)  # 0x6b

LORA_CS = const(44)
LORA_RESET = const(42)
SD_CS = const(43)
VIBE = const(0x47)
IR_LEDS = const(12)
USB_VSENSE = const(78)  # 14 | 0x40

POWER_SWITCH = const(18)
BUTTON_LEFT = const(45)
BUTTON_MIDDLE = const(0)
BUTTON_RIGHT = const(21)


print("unphone.py turn on red LED")
machine.Pin(LED_RED, machine.Pin.OUT).on()
time.sleep(1)
print("unphone.py init...")


class UnPhoneTCA:
    """
    unPhone spin 9 - TCA9555 IO expansion chip
    """

    I2C_DEV_ID = const(38)  # 0x26 - TI TCA9555's I²C addr

    # Register addresses
    REG_INPUT = const(0x00)
    REG_OUTPUT = const(0x02)
    REG_CONFIG = const(0x06)

    def __init__(self, i2c_bus: i2c.I2C.Bus):
        self.tca_dev = i2c.I2C.Device(bus=i2c_bus, dev_id=self.I2C_DEV_ID)
        self.directions = 0xFFFF  # All inputs by default
        self.output_states = 0x0000  # All low by default

        # Set IO expander initially as all inputs
        self._write_word(0x06, self.directions)

        # Read current directions and states
        self.directions = self._read_word(0x06)
        self.output_states = self._read_word(0x02)

    def _write_word(self, reg, value):
        print(f"Writing to TCA9555: reg={reg:#02x}, value={value:#04x}")
        self.tca_dev.write(bytes([reg, value & 0xFF, (value >> 8) & 0xFF]))

    def _read_word(self, reg):
        self.tca_dev.write(bytes([reg]))
        data = self.tca_dev.read(2)
        return struct.unpack("<H", data)[0]

    def pin_mode(self, pin, mode):
        if pin & 0x40:  # Pins with 0x40 bit set are controlled by TCA9555
            pin &= 0xBF  # Mask out high bit
            if mode == machine.Pin.OUT:
                self.directions &= ~(1 << pin)
            else:
                self.directions |= 1 << pin
            self._write_word(self.REG_OUTPUT, self.directions)
        else:
            # Handle standard ESP32 pin
            machine.Pin(pin, mode)

    def digital_write(self, pin, value):
        if pin & 0x40:  # Pins with 0x40 bit set are controlled by TCA9555
            pin &= 0xBF
            if value:
                self.output_states |= 1 << pin
            else:
                self.output_states &= ~(1 << pin)
            self._write_word(self.REG_OUTPUT, self.output_states)

            # Ensure pin is set to output
            self.directions &= ~(1 << pin)
            self._write_word(self.REG_CONFIG, self.directions)
        else:
            # Handle standard ESP32 pin
            p = machine.Pin(pin, machine.Pin.OUT)
            p.value(value)

    def digital_read(self, pin):
        if pin & 0x40:  # Pins with 0x40 bit set are controlled by TCA9555
            pin &= 0xBF
            # Ensure pin is set to input
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
        print(f"Turning Expander power {on=}...")
        self.tca.digital_write(EXPANDER_POWER, 1 if on else 0)

    def backlight(self, *, on):
        print(f"Turning LCD backlight {on=}...")
        self.tca.digital_write(BACKLIGHT, 1 if on else 0)

    def vibe(self, *, on):
        print(f"Turning VIBE {on=}...")
        self.tca.digital_write(VIBE, 1 if on else 0)

    def ir(self, *, on):
        print(f"Turning IR_LEDS {on=}...")
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
        connected = bool((status >> 2) & 1)  # Bit 2 indicates USB connection
        print(f"USB power connected: {connected}")
        return connected

    def _wake_on_power_switch(self):
        print("Configuring ESP32 wake on power switch...")
        wake_pin = machine.Pin(POWER_SWITCH, machine.Pin.IN)
        esp32.wake_on_ext0(pin=wake_pin, level=esp32.WAKEUP_ALL_LOW)

    def set_shipping(self, *, enable):
        print(f"Setting shipping mode to: {enable=}")
        wdt = self.i2c.readfrom_mem(self.BM_I2CADD, self.BM_WATCHDOG, 1)[0]
        opcon = self.i2c.readfrom_mem(self.BM_I2CADD, self.BM_OPCON, 1)[0]
        if enable:
            print("Asks BM chip to powering down and shutting off USB power")
            wdt = wdt & ~(1 << 5) & ~(1 << 4)  # Clear bits 5 and 4
            opcon = opcon | (1 << 5)  # Set bit 5
        else:
            print("Asks BM chip to power up and enable USB power")
            wdt = (wdt & ~(1 << 5)) | (1 << 4)  # Clear 5, Set 4
            opcon = opcon & ~(1 << 5)  # Clear bit 5
        self.i2c.writeto_mem(self.BM_I2CADD, self.BM_WATCHDOG, bytes([wdt]))
        self.i2c.writeto_mem(self.BM_I2CADD, self.BM_OPCON, bytes([opcon]))

    def turn_peripherals_off(self):
        print("Turning off peripherals...")
        self.expander_power(on=False)
        self.backlight(on=False)
        self.ir(on=False)
        self.rgb(0, 0, 0)

    def turn_off(self):
        print("turning unPhone off...")
        self.turn_peripherals_off()
        if not self.usb_power_connected():
            print("switch is off, power is OFF: going to shipping mode")
            self.set_shipping(enable=True)
        else:
            print("switch is off, but power is ON: going to deep sleep")
            self._wake_on_power_switch()
            machine.deepsleep(60000)  # Deep sleep

    def check_power_switch(self):
        if not self.power_switch_is_on():
            print("Power switch is OFF, initiating shutdown sequence...")
            self.turn_off()

    def reset(self):
        print("Resetting unPhone TCA9555 to default state...")

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

        time.sleep_ms(200)  # Short delay to help things settle

        # Turn RGB LED blue to indicate reset is done:
        self.rgb(0, 0, 1)


def recover_i2c():
    """
    NOTE: only do this in setup **BEFORE** Wire.begin!
    from: https://gitlab.com/hamishcunningham/unphonelibrary/-/blob/main/unPhone.cpp#L220
    """
    print("try to recover I2C bus in case it's locked up...")
    scl = machine.Pin(SCL, machine.Pin.OUT)
    sda = machine.Pin(SDA, machine.Pin.OUT)
    sda.value(1)

    for _ in range(10):  # 9th cycle acts as NACK
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

    # Short delay to help things settle
    time.sleep_ms(200)


try:
    recover_i2c()
    print(f"unphone.py init i2c Bus with: scl={SCL}, sda={SDA}...")
    i2c_bus = i2c.I2C.Bus(
        host=I2C_BUS, scl=SCL, sda=SDA, freq=I2C_FREQ, use_locks=False
    )
except Exception as e:
    sys.print_exception(e)
    print("Attempting hard reset in 3sec...")
    time.sleep(3)
    machine.reset()
else:
    print("Scanning I2C bus for devices...")
    for dev in i2c_bus.scan():
        print(f"Found I2C device at address: {dev} (${dev:#02X})")
    # Typical output here is:
    # Found I2C device at address: 38 ($0x26) -> TCA9555 IO expansion chip
    # Found I2C device at address: 106 ($0x6A) -> Touchscreen controller
    # Found I2C device at address: 107 ($0x6B) -> Power management unit (PMU/BMU)

    unphone = UnPhone(i2c=i2c_bus)


# Manually set MISO pin to input with pull-up to avoid it floating and causing issues on the SPI bus,
# since it's shared between display and touch controller:
Pin(MISO, Pin.IN, Pin.PULL_UP)


print("unphone.py shared SPI bus initialization")
time.sleep_ms(200)  # Short delay to help things settle
try:
    spi_bus = machine.SPI.Bus(host=SPI_HOST, sck=SCK, mosi=MOSI, miso=MISO)
except Exception as e:
    sys.print_exception(e)
    print("Attempting hard reset in 3sec...")
    time.sleep(3)
    machine.reset()


print("unphone.py HX8357D() display initialization")
try:
    display_bus = lcd_bus.SPIBus(
        spi_bus=spi_bus,  # Use **the same** SPI bus hx8357d display
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
    print("Attempting hard reset in 3sec...")
    time.sleep(3)
    machine.reset()


print("unphone.py display.init()")
mpos.ui.main_display.init()

print("unphone.py XPT2046() touch controller initialization")
time.sleep_ms(200)  # Short delay to help things settle
startup_rotation = lv.DISPLAY_ROTATION._0
try:
    touch_dev = machine.SPI.Device(
        spi_bus=spi_bus,  # Use **the same** SPI bus for xpt2046 touch
        freq=SPI_TOUCH_FREQ,
        cs=TOUCH_CS,
    )
except Exception as e:
    sys.print_exception(e)
    print("Attempting hard reset in 3sec...")
    time.sleep(3)
    machine.reset()
else:
    print(f"unphone.py init touch...")
    touch_input_dev = XPT2046(
        device=touch_dev,
        lcd_cs=LCD_CS,
        touch_cs=TOUCH_CS,
        display_width=TFT_WIDTH,
        display_height=TFT_HEIGHT,
        startup_rotation=startup_rotation,
        # debug=True,
    )
    print(f"{touch_input_dev.is_calibrated=}")
    # FIXME: Persistent calibration data is not working yet?
    # if touch_input_dev.is_calibrated:
    #     print('Touch input is already calibrated, skipping calibration step.')
    # else:
    #     print("Starting touch calibration...")
    #     touch_input_dev.calibrate()
    InputManager.register_indev(touch_input_dev)


print("unphone.py display.set_rotation() initialization")
mpos.ui.main_display.set_rotation(
    startup_rotation
)  # must be done after initializing display and creating the touch drivers, to ensure proper handling


print("unphone.py button initialization...")
button_left = Pin(BUTTON_LEFT, Pin.IN, Pin.PULL_UP)
button_middle = Pin(BUTTON_MIDDLE, Pin.IN, Pin.PULL_UP)
button_right = Pin(BUTTON_RIGHT, Pin.IN, Pin.PULL_UP)


REPEAT_INITIAL_DELAY_MS = 300  # Delay before first repeat
REPEAT_RATE_MS = 100  # Interval between repeats
next_repeat = None  # Used for auto-repeat key handling
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
        # No buttons pressed

        if data.key:  # A key was previously pressed and now released
            # print(f"Key {data.key=} released")
            data.key = 0
            data.state = lv.INDEV_STATE.RELEASED
            next_repeat = None

        if time.time() > next_check:
            # Check power switch state and update backlight accordingly
            unphone.check_power_switch()
            next_check = time.time() + 1  # Check every second

        return

    # A key is currently pressed

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

unphone.rgb(0, 1, 0)  # Green to indicate init is done

print("\nunphone.py init finished\n")
