import struct

from micropython import const
from machine import I2C, UART

from .device import Device

# registers
_COMM_REG_KEY_REPORT = const(0x03)
_COMM_REG_CONFIG = const(0x0B)
_COMM_REG_BACKLIGHT = const(0x0C)
_COMM2024_REG_RGB_LED = const(0x0E)
_COMM2024_REG_RED_LED = const(0x11)

_COMM2024_I2CADDR_DEFAULT = const(0x38)
_COMM2026_I2CADDR_DEFAULT = const(0x39)


class Communicator2026(Device):
    """Fri3d Badge 2026 expander MCU."""

    def __init__(
        self,
        i2c_bus: I2C,
        uart_bus: UART = None,
        address: int = _COMM2026_I2CADDR_DEFAULT,
    ):
        """Read from a 2026 communicator"""
        Device.__init__(self, i2c_bus, address)
        self.use_uart = False
        self.write_idx = 0
        self.data_ready = False
        if uart_bus:
            self.use_uart = True
            self.uart = uart_bus.init(115200, bits=8, parity=None, stop=1)
            self._rx_buf = bytearray(8)
            self._rx_mv = memoryview(self._rx_buf)
            self.uart.irq(handler=self.uart_handler, trigger=UART.IRQ_RX)

    def uart_handler(self, uart):
        """Interrupt handler for incoming UART data"""
        while uart.any() and not self.data_ready:
            # Calculate how much space is left
            space_left = 8 - self.write_idx

            # Read directly into the slice of the memoryview
            # readinto returns the number of bytes actually read
            num_read = uart.readinto(self._rx_mv[self.write_idx :], space_left)

            if num_read:
                self.write_idx += num_read

            if self.write_idx >= 8:
                self.data_ready = True

    @property
    def key_report(self) -> tuple[int, int, int, int, int, int, int, int, int]:
        """return the key report read using I2C or UART"""
        ret = None
        if self.use_uart and self.data_ready:
            # Process the data (raw_buffer now contains the 8 bytes)
            ret = tuple(self._rx_buf)
            self.write_idx = 0
            self.data_ready = False
        else:
            ret = self._read("BBBBBBBB", _COMM_REG_KEY_REPORT, 8)
        return ret

    @property
    def configuration(self) -> int:
        """get the configuration byte"""
        return self._read("B", _COMM_REG_CONFIG, 1)[0]

    @configuration.setter
    def configuration(self, value: int):
        """Set the configuration byte"""
        self._write(_COMM_REG_CONFIG, struct.pack("B", value))

    @property
    def backlight(self) -> int:
        """Get the backlight value (0-100)"""
        return self._read("<H", _COMM_REG_BACKLIGHT, 2)[0]

    @backlight.setter
    def backlight(self, value: int):
        """Set the backlight value (0-100)"""
        if value >= 0 and value <= 100:
            self.i2c.writeto_mem(
                self.address, _COMM_REG_BACKLIGHT, struct.pack("<H", value), addrsize=8
            )


class Communicator2024(Communicator2026):
    def __init__(
        self,
        i2c_bus: I2C,
        uart_bus: UART = None,
        address: int = _COMM2024_I2CADDR_DEFAULT,
    ):
        """Read from a 2024 communicator"""
        Communicator2026.__init__(self, i2c_bus, uart_bus, address)

    @property
    def rgb_led(self) -> tuple[int, int, int]:
        """Get the LANA module RGB LED"""
        return self._read("BBB", _COMM2024_REG_RGB_LED, 3)

    @rgb_led.setter
    def rgb_led(self, value: tuple[int, int, int]):
        """Set the LANA module RGB LED"""
        self._write(_COMM2024_REG_RGB_LED, struct.pack("BBB", *value))

    @property
    def red_led(self) -> int:
        """Get the CAPS LED"""
        return self._read("B", _COMM2024_REG_RED_LED, 1)[0]

    @red_led.setter
    def red_led(self, value: int):
        """Set the CAPS LED"""
        if value >= 0 and value <= 0xFF:
            self._write(_COMM2024_REG_RED_LED, struct.pack("B", value))
