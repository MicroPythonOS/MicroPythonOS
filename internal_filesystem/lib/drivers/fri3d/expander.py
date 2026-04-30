import struct

import time

from micropython import const
from machine import I2C, Pin

from .device import Device

# registers
_EXPANDER_REG_INPUTS = const(0x04)
_EXPANDER_REG_ANALOG = const(0x06)
_EXPANDER_REG_LCD_BRIGHTNESS = const(0x12)
_EXPANDER_REG_DEBUG_LED = const(0x14)
_EXPANDER_REG_CONFIG = const(0x16)

_EXPANDER_I2CADDR_DEFAULT = const(0x50)


class Expander(Device):
    """Fri3d Badge 2026 expander MCU."""

    def __init__(
        self,
        i2c_bus: I2C,
        address: int = _EXPANDER_I2CADDR_DEFAULT,
        int_pin: Pin = None,
    ):
        """Read from a sensor on the given I2C bus, at the given address."""
        Device.__init__(self, i2c_bus, address)
        self.use_interrupt = False
        if int_pin:
            self.use_interrupt = True
            self._rx_buf = bytearray(2)
            self._rx_mv = memoryview(self._rx_buf)
            self.int_pin = int_pin
            self.i2c.readfrom_mem_into(self.address, _EXPANDER_REG_INPUTS, self._rx_mv)
            self.int_pin.irq(trigger=Pin.IRQ_RISING, handler=self.int_callback)

    def int_callback(self, p):
        self.i2c.readfrom_mem_into(self.address, _EXPANDER_REG_INPUTS, self._rx_mv)

    @property
    def analog(self) -> tuple[int, int, int, int, int, int]:
        """Read the analog inputs: ain1, ain0, battery_monitor, usb_monitor, joystick_y, joystick_x"""
        return self._read("<HHHHHH", _EXPANDER_REG_ANALOG, 12)

    @property
    def digital(
        self,
    ) -> tuple[bool, bool, bool, bool, bool, bool, bool, bool, bool, bool, bool, bool]:
        """Read the digital inputs: usb_plugged, joy_right, joy_left, joy_down, joy_up, button_menu, button_b, button_a, button_y, button_x, charger_standby, charger_charging"""
        if self.use_interrupt:
            inputs = struct.unpack("<H", self._rx_buf)[0]
        else:
            inputs = self._read("<H", _EXPANDER_REG_INPUTS, 2)[0]
        return tuple([bool(int(digit)) for digit in "{:016b}".format(inputs)[4:]])

    @property
    def lcd_brightness(self) -> int:
        """Read the LCD brightness state (0-100)"""
        return self._read("<H", _EXPANDER_REG_LCD_BRIGHTNESS, 2)[0]

    @lcd_brightness.setter
    def lcd_brightness(self, value: int):
        """Set the LCD brightness (0-100)"""
        if value >= 0 and value <= 100:
            self._write(_EXPANDER_REG_LCD_BRIGHTNESS, struct.pack("<H", value))

    @property
    def debug_led(self) -> int:
        """Read the Debug LED state (0-100)"""
        return self._read("<H", _EXPANDER_REG_DEBUG_LED, 2)[0]

    @debug_led.setter
    def debug_led(self, value: int):
        """Set the Debug LED (0-100)"""
        if value >= 0 and value <= 100:
            self._write(_EXPANDER_REG_DEBUG_LED, struct.pack("<H", value))

    @property
    def config(self) -> tuple[bool, bool, bool]:
        """Read the configuration bits: reboot, lcd_reset, aux_power"""
        config = self._read("B", _EXPANDER_REG_CONFIG, 1)[0]
        return tuple([bool(int(digit)) for digit in "{:08b}".format(config)[5:]])

    @config.setter
    def config(self, value: int):
        """set the configuration byte"""
        if value >= 0 and value <= 0xFF:
            self._write(_EXPANDER_REG_CONFIG, struct.pack("B", value))

    def install_firmware(self, filename: str, progress_cb):
        print("Installing latest CH32 firmware")
        try:
            self.config = 0x0B # trigger SWD enable
        except Exception as e:
            print(f"Expander SWD enable got exception, ignoring it: {e}") # could be normal, if the expander is empty
        time.sleep(0.2)
        from rvswd import RVSWD
        prog = RVSWD(39, 42)
        # optional check, already halts the MCU
        vendor = prog.read_vendor_bytes()
        if (vendor[1] & 0xffffff0f) != 0x03560601:
            print(f"CH32X035G8U6 not detected, vendor is {vendor} but continuing anyway")
        with open(filename, "rb") as f:
            fw = f.read()
        f.close()
        progress_margin_end = 21 # 21% left for sleep at the end
        if progress_cb:
            prog.x03x_program(
                fw,
                lambda msg, pct: progress_cb(
                    msg,
                    int((100 - progress_margin_end) * pct / 100),
                ),
            ) # throws exception if it fails
        else:
            prog.x03x_program(fw, None) # throws exception if it fails
        for pct in range(100 - progress_margin_end, 101):
            progress_cb("waiting for CH32 boot", pct)
            time.sleep(4 / progress_margin_end) # wait 4 seconds total
        print("Latest CH32 firmware installed.")

    def wait_for_normal_mode(self, min_uptime_ms: int = 1000, poll_ms: int = 10):
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < min_uptime_ms:
            time.sleep_ms(poll_ms)

    # Returns True if expander_i2c needs to be re-initialized
    def install_firmware_if_needed(
        self, filename: str, latest_version: tuple[int, int, int],
        progress_cb, success_cb, warning_cb, failure_cb) -> bool:
        # Check expander firmware version and if none or too low: install latest
        try:
            current_version = self.version
            print(f"Current_version of CH32 firmware: {current_version}")
        except Exception as e:
            print("Could not check CH32 firmware version, assuming 0.0.0")
            current_version = (0, 0, 0)
        if latest_version <= current_version:
            print(f"CH32 firmware {latest_version} <= {current_version} so not updating it")
            return False
        print(f"CH32 firmware {latest_version} > {current_version} so updating it")
        try:
            self.install_firmware(filename, progress_cb)
            success_cb()
        except Exception as e:
            failure_cb(e)
        return True # re-initialize expander_i2c, even if the install failed, just in case
