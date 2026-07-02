import struct

from micropython import const
from machine import I2C, UART

from .device import Device

# registers
_DJ_ADDON_REG_BUTTONS = const(0x03)
_DJ_ADDON_REG_ANALOG = const(0x04)
_DJ_ADDON_REG_LEFT_ENCODER = const(0x16)
_DJ_ADDON_REG_RIGHT_ENCODER = const(0x18)
_DJ_ADDON_REG_LEDS = const(0x1A)

_DJ_ADDON_BAUDRATE = const(115200)

_DJ_ADDON_I2CADDR_DEFAULT = const(0x3A)


class DJAddon(Device):
    """Fri3d Badge 2026 expander MCU."""

    def __init__(self, i2c_bus: I2C, uart_bus: UART = None, address: int = _DJ_ADDON_I2CADDR_DEFAULT):
        """Read from a sensor on the given I2C bus, at the given address."""
        Device.__init__(self, i2c_bus, address)
        self.use_uart = False
        self.write_idx = 0
        self.data_ready = False
        if uart_bus:
            self.use_uart = True
            self.uart = uart_bus
            self.uart.init(_DJ_ADDON_BAUDRATE, bits=8, parity=None, stop=1)
            self._rx_buf = bytearray(4)
            self._rx_mv = memoryview(self._rx_buf)
            self.uart.irq(handler=self.uart_handler, trigger=UART.IRQ_RX)

    def uart_handler(self, uart):
        """Interrupt handler for incoming UART data"""
        while uart.any() and not self.data_ready:
            # Calculate how much space is left
            space_left = 4 - self.write_idx

            # Read directly into the slice of the memoryview
            # readinto returns the number of bytes actually read
            num_read = uart.readinto(self._rx_mv[self.write_idx :], space_left)

            if num_read:
                self.write_idx += num_read

            if self.write_idx >= 4:
                self.data_ready = True

    @property
    def buttons(self) -> tuple[bool, bool, bool, bool, bool, bool, bool, bool]:
        buttons = self._read("B", _DJ_ADDON_REG_BUTTONS, 1)[0]
        return tuple([bool(int(digit)) for digit in "{:08b}".format(buttons)])

    @property
    def analog(self) -> tuple[int, int, int, int, int, int, int, int, int]:
        return self._read("<HHHHHHHHH", _DJ_ADDON_REG_ANALOG, 18)

    @property
    def left_encoder(self) -> int:
        return self._read("<H", _DJ_ADDON_REG_LEFT_ENCODER, 2)[0]

    @property
    def right_encoder(self) -> int:
        return self._read("<H", _DJ_ADDON_REG_RIGHT_ENCODER, 2)[0]

    def set_led(self, idx: int, r: int, g: int, b: int):
        self._write(_DJ_ADDON_REG_LEDS + (idx * 3), struct.pack("BBB", g, r, b))

    def send_midi(self, data: bytes):
        if self.use_uart and len(data) == 4:
            self.uart.write(data)
            self.uart.flush()
