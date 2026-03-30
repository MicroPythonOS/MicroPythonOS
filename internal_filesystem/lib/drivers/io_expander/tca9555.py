import struct

import i2c
import machine
from micropython import const


class TCA9555:
    """
    LCA9555 / TCA9555 IO expansion chip
    (LCA9555 is register-compatible with TCA9555)
    """

    # Register addresses
    REG_INPUT = const(0x00)
    REG_OUTPUT = const(0x02)
    REG_CONFIG = const(0x06)

    def __init__(self, i2c_bus: i2c.I2C.Bus, dev_id: int):
        self.tca_dev = i2c.I2C.Device(bus=i2c_bus, dev_id=dev_id)
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

    def digital_read(self, pin: int):
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


class TCA9555Pin:
    """
    Minimal Pin-like wrapper for TCA9555 IO expander pins.
    Provides value() and __call__() for compatibility with bit-bang drivers.
    """

    def __init__(self, tca: TCA9555, pin: int, mode=machine.Pin.OUT):
        self.tca = tca
        self.pin = pin
        self.tca.pin_mode(pin, mode)

    def value(self, v=None):
        if v is None:
            # No readback support for output-only pins
            return None
        self.tca.digital_write(self.pin, v)

    def __call__(self, v=None):
        return self.value(v)
