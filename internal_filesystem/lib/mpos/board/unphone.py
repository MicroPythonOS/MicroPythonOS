print("unphone.py initialization")

# Hardware initialization for the unPhone 9
# https://unphone.net/
# https://gitlab.com/hamishcunningham/unphonelibrary/-/blob/main/unPhone.h
#
# other references:
# https://www.espboards.dev/esp32/unphone9/
# https://github.com/espressif/arduino-esp32/blob/master/variants/unphone9/pins_arduino.h
# https://github.com/meshtastic/device-ui/blob/master/include/graphics/LGFX/LGFX_UNPHONE.h
#
# Original author: https://github.com/jedie

import sys
import time

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

SPI_HOST = const(1)
LCD_SPI_FREQ = const(20_000_000)

I2C_BUS = const(0)
I2C_FREQ = const(100_000)

LCD_DC = const(47)
LCD_CS = const(48)
LCD_BACKLIGHT = const(2)  # 0x02
LCD_RESET = const(46)

TFT_WIDTH = const(320)
TFT_HEIGHT = const(480)

TOUCH_I2C_ADDR = const(106)  # 0x6a - Touchscreen controller
TOUCH_REGBITS = const(8)
TOUCH_CS = const(38)
TOUCH_SPI_FREQ = const(500_000)

# Power management (known variously as PMU, BMU or just BM):
BM_I2C_ADDR = const(107)  # 0x6b

LORA_CS = const(44)
LORA_RESET = const(42)
SD_CS = const(43)


POWER_SWITCH = const(18)
BUTTON_LEFT = const(45)
BUTTON_MIDDLE = const(0)
BUTTON_RIGHT = const(21)


print(f"unphone.py init i2c Bus with: scl={SCL}, sda={SDA}...")
try:
    i2c_bus = i2c.I2C.Bus(host=I2C_BUS, scl=SCL, sda=SDA, freq=I2C_FREQ, use_locks=True)
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


class UnPhoneTCA:
    """
    unPhone spin 9 - TCA9555 IO expansion chip
    """

    TCA_I2C_ADDR = const(38)  # 0x26 - TI TCA9555's I²C addr

    # TCA9555-controlled pins (spin 9)
    BACKLIGHT = const(66)  # 0x42
    EXPANDER_POWER = const(64)  # 0x40
    VIBE = const(71)  # 0x47
    USB_VSENSE = const(78)  # 0x4e

    IR_LED = const(12)  # 0x0c

    # Register addresses
    REG_INPUT = const(0)
    REG_OUTPUT = const(2)
    REG_CONFIG = const(6)

    def __init__(self, i2c_bus):
        self.tca_dev = i2c.I2C.Device(bus=i2c_bus, dev_id=self.TCA_I2C_ADDR)
        self.directions = 0xFFFF  # all inputs initially
        self.output_states = 0x0000
        self.init_expander()
        self.reset()

    def init_expander(self):
        self.write_reg_word(self.REG_CONFIG, 0xFFFF)  # all inputs
        self.directions = self.read_reg_word(self.REG_CONFIG)
        self.output_states = self.read_reg_word(self.REG_OUTPUT)

    def write_reg_word(self, reg, value):
        print(f"Writing to TCA9555: reg={reg:#02x}, value={value:#04x}")
        self.tca_dev.write(bytes([reg, value & 0xFF, (value >> 8) & 0xFF]))

    def read_reg_word(self, reg):
        self.tca_dev.write(bytes([reg]))
        data = self.tca_dev.read(2)
        return data[0] | (data[1] << 8)

    def pinMode(self, pin, mode):
        if pin & 0x40:
            pin &= 0b10111111
            if mode == "output":
                self.directions &= ~(1 << pin)
            else:
                self.directions |= 1 << pin
            self.write_reg_word(self.REG_CONFIG, self.directions)
        else:
            pass  # handle non-expander pins if needed

    def digitalWrite(self, pin, value):
        if pin & 0x40:
            pin &= 0b10111111
            if value:
                self.output_states |= 1 << pin
            else:
                self.output_states &= ~(1 << pin)
            self.write_reg_word(self.REG_OUTPUT, self.output_states)
            # Removed direction update here; pinMode should handle direction
        else:
            pass  # handle non-expander pins if needed

    def digitalRead(self, pin):
        if pin & 0x40:
            pin &= 0b10111111
            self.directions |= 1 << pin
            self.write_reg_word(self.REG_CONFIG, self.directions)
            inputs = self.read_reg_word(self.REG_INPUT)
            return 1 if (inputs & (1 << pin)) else 0
        else:
            pass  # handle non-expander pins if needed

    def backlight_on(self):
        print("Turning LDC backlight ON...")
        self.pinMode(self.BACKLIGHT, "output")
        self.digitalWrite(self.BACKLIGHT, 1)

    def backlight_off(self):
        print("Turning LCD backlight OFF...")
        self.pinMode(self.BACKLIGHT, "output")
        self.digitalWrite(self.BACKLIGHT, 0)

    def reset(self):
        print("Resetting unPhone TCA9555 to default state...")

        self.backlight_on()

        print("VIBE off")
        self.pinMode(self.VIBE, "output")
        self.digitalWrite(self.VIBE, 0)

        print("IR LED off")
        self.pinMode(self.IR_LED, "output")
        self.digitalWrite(self.IR_LED, 0)

        print("Expander power on")
        self.pinMode(self.EXPANDER_POWER, "output")
        self.digitalWrite(self.EXPANDER_POWER, 1)

        print("USB_VSENSE off")
        self.pinMode(self.USB_VSENSE, "output")
        self.digitalWrite(self.USB_VSENSE, 0)


power_switch = Pin(POWER_SWITCH, Pin.IN, Pin.PULL_UP)
tca = UnPhoneTCA(i2c_bus)


print("unphone.py machine.SPI.Bus() initialization")
try:
    spi_bus = machine.SPI.Bus(host=SPI_HOST, mosi=MOSI, sck=SCK)
except Exception as e:
    sys.print_exception(e)
    print("Attempting hard reset in 3sec...")
    time.sleep(3)
    machine.reset()


print("unphone.py lcd_bus.SPIBus() initialization")
try:
    display_bus = lcd_bus.SPIBus(
        spi_bus=spi_bus, freq=LCD_SPI_FREQ, dc=LCD_DC, cs=LCD_CS
    )
except Exception as e:
    sys.print_exception(e)
    print("Attempting hard reset in 3sec...")
    time.sleep(3)
    machine.reset()


print("unphone.py hx8357d.HX8357D() initialization")
try:
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
        # backlight_on_state=hx8357d.STATE_HIGH,
    )
except Exception as e:
    sys.print_exception(e)
    print("Attempting hard reset in 3sec...")
    time.sleep(3)
    machine.reset()


print("unphone.py display.init()")
mpos.ui.main_display.init()
mpos.ui.main_display.set_power(True)
mpos.ui.main_display.set_backlight(100)


print("unphone.py touch SPI bus initialization")
try:
    touch_dev = machine.SPI.Device(spi_bus=spi_bus, freq=TOUCH_SPI_FREQ, cs=TOUCH_CS)
except Exception as e:
    sys.print_exception(e)
    print("Attempting hard reset in 3sec...")
    time.sleep(3)
    machine.reset()

print(f"unphone.py init touch...")
touch_input_dev = XPT2046(
    device=touch_dev,
    spi_cs_touch=TOUCH_CS,
    touch_cal=None,
    # display_width=TFT_WIDTH,
    # display_height=TFT_HEIGHT,
)
# TODO:
# if not touch_input_dev.is_calibrated:
#     touch_input_dev.calibrate()
print(f"{touch_input_dev._cal=}")
# TODO: InputManager.register_indev(touch_input_dev)


print("unphone.py lv.init() initialization")
lv.init()
mpos.ui.main_display.set_rotation(
    lv.DISPLAY_ROTATION._270
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

        # Check power switch state and update backlight accordingly
        switch_value = power_switch.value()
        if switch_value != last_power_switch:
            last_power_switch = switch_value
            print(f"Changed: {switch_value=}")
            if switch_value == 1:
                print("Power switch is ON")
                tca.backlight_on()
            else:
                print("Power switch is OFF !")
                tca.backlight_off()

        if time.time() > next_check:
            next_check = time.time() + 1
            if result := touch_input_dev._get_coords():
                print(f"Touch: {result}")

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

print("unphone.py finished")
