print("squixl.py initialization")
"""
Hardware initialization for the SQUiXL device by "Unexpected Maker"
https://unexpectedmaker.com/shop.html#!/SQUiXL/p/743870537

https://github.com/UnexpectedMaker/SQUiXL-DevOS
https://github.com/UnexpectedMaker/SQUiXL-DevOS/blob/main/platformio/src/squixl.h

https://github.com/UnexpectedMaker/SQUiXL
https://github.com/UnexpectedMaker/SQUiXL/blob/main/examples/micropython/lib/squixl.py
https://github.com/UnexpectedMaker/SQUiXL/blob/main/esphome/readme.md

* ESP32-S3 - 32Bit Dual Core 240MHz
* ST7701S - 4 Inch 480x480 RGB Display
* GT911 - Capacitive Touch controller
* LCA9555 IO expander (register-compatible with the TCA9555)
* TMUX1574RSVR - IO MUX
* MAX98357A - I2S Audio Amplifier (8 Ohm, 2W Speaker)
* DRV2605L - Haptic feedback motor
* RV-3028-C7 - I2C Low Power RTC
* MAX1704X - I2C Battery Fuel Gauge

Before you can install MicroPython, you need to erase the Flash on your SQUiXL.

Power it up and put it into download mode by following these steps:

    Press and hold the [BOOT] button
    Press and release the [RESET] button
    Release the [BOOT] button

Now the board is in download mode and the native USB will have enumerated as a serial device.

The SQUiXL display uses an ST7701S controller with a standard ESP32-S3 RGB parallel bus for pixel
data. However, the display's SPI init lines (CS, CLK, MOSI, Reset) are wired through an LCA9555
IO expander over I2C instead of native GPIO.

This component handles that by bit-banging the SPI init sequence through the IO expander during
startup, then handing off to ESPHome's standard RGB display driver for all pixel operations.

The GT911 capacitive touch controller's reset pin is also on the IO expander (pin 5).
This component handles the GT911 reset with the correct INT pin state for I2C address selection.

The LCA9555 is register-compatible with the TCA9555.


Original author: https://github.com/jedie
"""

"""
| ESP32-S3 | GENERAl IO    |
| -------- | ------------- |
| IO0      | BOOT          |
| IO1      | I2C SDA       |
| IO2      | I2C SCL       |
| IO3      | Touch IC INT  |
| IO40     | Backlight PWM |
| IO41     | IOMUX 1       |
| IO42     | IOMUX 2       |
| IO43     | FG Interrupt  |
| IO44     | RTC Interrupt |
| IO45     | IOMUX 3       |
| IO46     | IOMUX 4       |


| IO Expander |           |
| ----------- | --------- |
| IO0  | Backlight Enable |
| I01  | LCD Reset        |
| IO2  | LCD Data         |
| IO3  | LCD SCK          |
| IO4  | LCD CS           |
| IO5  | Touch IC Reset   |
| IO7  | uSD Card Detect  |
| IO8  | IOMUX SEL        |
| IO9  | IOMUX Enable     |
| IO10 | Haptics Enable   |
| IO11 | VBUS Sense       |

| IOMUX | FUNC 1  | FUNC 2    |
| ----- | ------- | --------  |
| IO1   | SD MISO | I2S SD    |
| IO2   | SD CS   | I2S LRCLK |
| IO3   | SD CLK  | I2S DATA  |
| IO4   | SD MOSI | I2S BCLK  |

| RGB Peripheral |       |
| -------------- | ----- |
| ESP32-S3       | FUNC  |
| IO4            | R5    |
| IO5            | R4    |
| IO6            | R3    |
| IO7            | R2    |
| IO8            | R1    |
| IO9            | G5    |
| IO10           | G4    |
| IO11           | G3    |
| IO12           | G2    |
| IO13           | G1    |
| IO14           | G0    |
| IO15           | B5    |
| IO16           | B4    |
| IO17           | B3    |
| IO18           | B2    |
| IO21           | B1    |
| IO38           | DE    |
| IO39           | PCLK  |
| IO47           | VSYNC |
| IO48           | HSYNC |
"""

import sys
import time

for i in range(2, 0, -1):
    print(f"squixl.py starting in {i}...")
    time.sleep(1)

import i2c
import lcd_bus
import lvgl as lv
import machine
import mpos.ui
from drivers.display.st7701s.st7701s import ST7701S
from drivers.io_expander.tca9555 import TCA9555
from micropython import const

# S3 IO
SPI_HOST = const(0)
I2C_BUS = const(0)
I2C_FREQ = const(400_000)
SDA = const(1)
SCL = const(2)

DE = const(38)
PCLK = const(39)
BL_PWM = const(40)
VSYNC = const(47)
HSYNC = const(48)

# IOconst( MUX)
IOMUX_OFF = const(0)
IOMUX_SD = const(1)
IOMUX_I2S = const(2)

IOMUX_D1 = const(41)
IOMUX_D2 = const(42)
IOMUX_D3 = const(45)
IOMUX_D4 = const(46)

# GT911 touch pins:
TP_I2C_IRQ = const(3)
TP_I2C_RESET = const(5)

# ======= AUDIO CONFIGURATION =======
I2S_ID = 0
I2S_BUFFER_LENGTH_IN_BYTES = 2000
SAMPLE_SIZE_IN_BITS = 16
# FORMAT = I2S.MONO  # only MONO supported in this example
SAMPLE_RATE_IN_HZ = 22_050
# ======= AUDIO CONFIGURATION =======

# IOMUX default state, which is off
current_iomux_state = IOMUX_OFF

# Data pins in R0–R4, G0–G5, B0–B4 order
RGB_IO = [
    # B0–B4
    21, 18, 17, 16, 15,
    # G0–G5
    14, 13, 12, 11, 10, 9,
    # R0–R4
    8, 7, 6, 5, 4,
]

# Macro for the delay value
LCD_DELAY = 0xFF


# LCD and AUDIO vars
lcd = None
audio_out = None

# BACKLIGHT control - wil be functional soon
# back_light = PWM(BL_PWM, freq=6000, duty_u16=8192)
# back_light.duty_u16(32768)


try:
    print(f"squixl.py init i2c Bus with: scl={SCL}, sda={SDA}...")
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
    # Found I2C device at address: 32 ($0X20) - TCA9555 IO Expander
    # Found I2C device at address: 54 ($0X36)
    # Found I2C device at address: 82 ($0X52)
    # Found I2C device at address: 90 ($0X5A)
    # Found I2C device at address: 93 ($0X5D)


# # Create an instance of the MAX17048 class
# max17048 = MAX17048(i2c)
#


class SQUiXL:
    TCA9555_I2C_DEV_ID = const(32)  # 0x20 - TI TCA9555's I²C addr

    # Expander pins (0-15)
    BL_EN = const(0)  # Backlight Enable
    LCD_RST = const(1)  # LCD Reset

    MOSI = const(2)  # CD SPI Data
    CLK = const(3)  # CD SPI Clock
    CS = const(4)  # CD SPI CS

    TP_RST = const(5)  # Touch IC Reset
    SOFT_PWR = const(6)  # SD Card Detect
    MUX_SEL = const(8)  # IOMUX Select
    MUX_EN = const(9)  # IOMUX Enable
    HAPTICS_EN = const(10)  # Haptics Enable
    VBUS_SENSE = const(11)  # VBUS Sense
    SD_DETECT = const(15)

    def __init__(self, i2c: i2c.I2C.Bus):
        self.i2c = i2c
        self.tca = TCA9555(self.i2c, dev_id=self.TCA9555_I2C_DEV_ID)

        self.lcd_reset()
        self.set_lcd_backlight(on=True)

        print("Screen soft power EN")
        self.tca.pin_mode(self.SOFT_PWR, machine.Pin.OUT)

        print("5V presense sense IO")
        self.tca.pin_mode(self.VBUS_SENSE, machine.Pin.IN)

        print("IO MUX - EN is Active LOW, so start it off")
        self.tca.pin_mode(self.MUX_EN, machine.Pin.OUT)

        print("IO MUX - Set default to I2S - LOW is SD")
        self.tca.pin_mode(self.MUX_SEL, machine.Pin.OUT)

        print("Haptic EN")
        self.tca.pin_mode(self.HAPTICS_EN, machine.Pin.OUT)

    def set_params(self, cmd, params=None):
        """
        Send a command and optional data bytes to the display via bit-banged SPI over the IO expander.
        :param cmd: Command byte to send
        :param params: Optional list/tuple of data bytes to send after the command
        """
        print(f"set_params: cmd=0x{cmd:02X}", end=" ")
        if params:
            print("params:", " ".join(f"{b:02X}" for b in params))
        else:
            print("no params")

        # Start transaction
        self.tca.pin_mode(self.CS, machine.Pin.PULL_DOWN)
        # DC bit = 0 for command
        self.tca.pin_mode(self.CLK, machine.Pin.PULL_DOWN)
        self.tca.pin_mode(self.MOSI, 0)
        self.tca.pin_mode(self.CLK, machine.Pin.PULL_UP)
        # Send 8-bit command
        for bit in range(7, -1, -1):
            self.tca.pin_mode(self.CLK, machine.Pin.PULL_DOWN)
            self.tca.pin_mode(self.MOSI, (cmd >> bit) & 1)
            self.tca.pin_mode(self.CLK, machine.Pin.PULL_UP)
        # Send data bytes if any
        if params:
            for data_byte in params:
                # DC bit = 1 for data
                self.tca.pin_mode(self.CLK, machine.Pin.PULL_DOWN)
                self.tca.pin_mode(self.MOSI, 1)
                self.tca.pin_mode(self.CLK, machine.Pin.PULL_UP)
                for bit in range(7, -1, -1):
                    self.tca.pin_mode(self.CLK, machine.Pin.PULL_DOWN)
                    self.tca.pin_mode(self.MOSI, (data_byte >> bit) & 1)
                    self.tca.pin_mode(self.CLK, machine.Pin.PULL_UP)
        # End transaction
        self.tca.pin_mode(self.CS, machine.Pin.PULL_UP)

    def get_vbus_present(self):
        print("Detect if VBUS (5V) power source is present:", end=" ")
        # return self.tca.read(VBUS_SENSE) == 1
        raw_value = self.tca.digital_read(self.VBUS_SENSE)
        print(f"{raw_value=}")
        return raw_value == 1

    def set_lcd_backlight(self, *, on: bool):
        """
        Enable or disable the LCD backlight via IO expander BL_EN pin.
        :param enable: True to turn on, False to turn off
        """
        self.tca.pin_mode(self.BL_EN, machine.Pin.OUT)
        print(f"Setting LCD backlight {'ON' if on else 'OFF'} (BL_EN={self.BL_EN})")
        self.tca.digital_write(self.BL_EN, 1 if on else 0)

    def lcd_reset(self):
        print("Resetting LCD...")
        self.tca.pin_mode(self.LCD_RST, machine.Pin.OUT)

        self.tca.digital_write(self.LCD_RST, 0)  # Assert reset
        time.sleep_ms(100)  # Hold reset for 100ms
        self.tca.digital_write(self.LCD_RST, 1)  # Deassert reset
        time.sleep_ms(100)  # Wait for LCD to come out of reset


print("Create instance of the LCA9555 IO Expander...")
squixl = SQUiXL(i2c=i2c_bus)
squixl.set_lcd_backlight(on=False)
time.sleep(0.5)
squixl.set_lcd_backlight(on=True)


# TODO: Initialise the GT911 touch IC
# touch = GT911(i2c, irq_pin=TP_I2C_IRQ, reset_pin=TP_I2C_RESET, ioex=ioex)

# TODO: Initialise the DRV2605 haptic engine
# drv = DRV2605(i2c)


try:
    print("squixl.py RGB parallel bus display initialization")
    display_bus = lcd_bus.RGBBus(
        hsync=HSYNC,
        vsync=VSYNC,
        de=DE,
        pclk=PCLK,
        data0=RGB_IO[0],
        data1=RGB_IO[1],
        data2=RGB_IO[2],
        data3=RGB_IO[3],
        data4=RGB_IO[4],
        data5=RGB_IO[5],
        data6=RGB_IO[6],
        data7=RGB_IO[7],
        data8=RGB_IO[8],
        data9=RGB_IO[9],
        data10=RGB_IO[10],
        data11=RGB_IO[11],
        data12=RGB_IO[12],
        data13=RGB_IO[13],
        data14=RGB_IO[14],
        data15=RGB_IO[15],
        freq=6_000_000,  # 6 MHz
        hsync_front_porch=50,
        hsync_back_porch=10,
        hsync_pulse_width=8,
        hsync_idle_low=False,
        vsync_front_porch=8,
        vsync_back_porch=8,
        vsync_pulse_width=3,
        vsync_idle_low=False,
        de_idle_high=False,  # ???
        pclk_idle_high=False,  # ???
        pclk_active_low=False,  # ???
        rgb565_dither=False,
    )
    print("squixl.py ST7701S() display initialization")
    mpos.ui.main_display = ST7701S(
        data_bus=display_bus,
        display_width=480,
        display_height=480,
        set_params_func=squixl.set_params,
    )
except Exception as e:
    sys.print_exception(e)
    print("Attempting hard reset in 3sec...")
    time.sleep(3)
    machine.reset()


print("squixl.py display.init()")
mpos.ui.main_display.init()

time.sleep_ms(200)  # Short delay to help things settle
startup_rotation = lv.DISPLAY_ROTATION._0
print("squixl.py display.set_rotation() initialization")
mpos.ui.main_display.set_rotation(
    startup_rotation
)  # must be done after initializing display and creating the touch drivers, to ensure proper handling

print("squixl.py lv.init() initialization")
lv.init()

group = lv.group_create()
group.set_default()

# Create and set up the input device
indev = lv.indev_create()
indev.set_type(lv.INDEV_TYPE.KEYPAD)
# indev.set_read_cb(input_callback)
indev.set_group(
    group
)  # is this needed? maybe better to move the default group creation to main.py so it's available everywhere...
disp = lv.display_get_default()  # NOQA
indev.set_display(disp)  # different from display
indev.enable(True)  # NOQA
# InputManager.register_indev(indev)


# CHnage teh state of the IOMUX from Off, to I2S or uSD
def set_iomux(state=IOMUX_OFF):
    """Set the state of the IOMUX - for I2S Amp or SD Card or OFF"""
    global current_iomux_state
    global audio_out

    if current_iomux_state == state:
        return

    if current_iomux_state == IOMUX_I2S:
        audio_out.deinit()

    # IO MUX - Set default to I2S - machine.Pin.PULL_DOWN is SD

    if state == IOMUX_OFF:
        self.tca.pin_mode(self.MUX_EN, machine.Pin.PULL_UP)
        print("SQUiXL IOMUX is OFF")
    elif state == IOMUX_SD:
        self.tca.pin_mode(self.MUX_EN, machine.Pin.PULL_DOWN)
        self.tca.pin_mode(self.MUX_SEL, machine.Pin.PULL_DOWN)
        print("SQUiXL IOMUX is uSD")
    elif state == IOMUX_I2S:
        self.tca.pin_mode(self.MUX_EN, machine.Pin.PULL_DOWN)
        self.tca.pin_mode(self.MUX_SEL, machine.Pin.PULL_UP)

        sd_mode = machine.Pin(IOMUX_D1, machine.Pin.OUT)
        sd_mode.value(1)

        audio_out = I2S(
            1,
            sck=machine.Pin(IOMUX_D4),
            ws=machine.Pin(IOMUX_D2),
            sd=machine.Pin(IOMUX_D3),
            mode=I2S.TX,
            bits=SAMPLE_SIZE_IN_BITS,
            format=FORMAT,
            rate=SAMPLE_RATE_IN_HZ,
            ibuf=I2S_BUFFER_LENGTH_IN_BYTES,
        )
        print("SQUiXL IOMUX is I2S")

    current_iomux_state = state


# General Helper Functions


# Battery voltage
def get_bat_voltage():
    """Read the battery voltage from the fuel gauge"""
    voltage = max17048.cell_voltage
    print(f"Bat Voltage: {voltage}V")
    return voltage


# Battery charge state
def get_state_of_charge():
    """Read the battery state of charge from the fuel gauge"""
    soc = max17048.state_of_charge
    print(f"State of Charge: {soc}%")
    return soc


print(f"{squixl.get_vbus_present()=}")


print("squixl.py initialization complete")
