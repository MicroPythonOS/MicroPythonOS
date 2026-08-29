import i2c
from micropython import const


class PCA9554:
    """PCA9554 / TCA9554 8-bit I2C IO expansion chip.

    Same register layout across the PCA9554/TCA9554/PCA9554A family:
    input port, output port, polarity inversion, configuration.
    Used e.g. on the Waveshare ESP32-S3-Touch-LCD-3.5, where the LCD
    reset and chip-select lines are wired to expander pins EXIO1/EXIO2.
    """

    REG_INPUT = const(0x00)
    REG_OUTPUT = const(0x01)
    REG_POLARITY = const(0x02)
    REG_CONFIG = const(0x03)

    def __init__(self, i2c_bus: i2c.I2C.Bus, dev_id: int):
        self.dev = i2c.I2C.Device(bus=i2c_bus, dev_id=dev_id, reg_bits=8)
        self.directions = 0xFF     # all inputs by default (chip reset state)
        self.output_states = 0x00

    def _write_reg(self, reg, value):
        self.dev.write_mem(reg, bytes([value & 0xFF]))

    def _read_reg(self, reg):
        buf = bytearray(1)
        self.dev.read_mem(reg, buf=buf)
        return buf[0]

    def set_output(self, pin, value):
        """Configure pin (0-7) as output and drive it high (True) or low."""
        if value:
            self.output_states |= (1 << pin)
        else:
            self.output_states &= ~(1 << pin)
        self._write_reg(self.REG_OUTPUT, self.output_states)
        self.directions &= ~(1 << pin)  # 0 = output
        self._write_reg(self.REG_CONFIG, self.directions)

    def get_input(self, pin):
        """Read pin (0-7); pin must be configured as input (the default)."""
        return bool(self._read_reg(self.REG_INPUT) & (1 << pin))
