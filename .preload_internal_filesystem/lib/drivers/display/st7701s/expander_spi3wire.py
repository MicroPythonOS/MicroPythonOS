# 3-wire (9-bit) SPI for the ST7701S register init, bit-banged over the TCA9555
# IO expander. Implements the lvgl_micropython rgb_display_framework spi_3wire
# contract: init(cmd_bits, param_bits), tx_param(cmd, params=None), deinit().
# Pin ids are TCA9555 expander pins WITH the 0x40 marker bit.


class ExpanderSpi3Wire:
    def __init__(self, tca, cs_pin, clk_pin, mosi_pin):
        self._tca = tca
        self._cs = cs_pin
        self._clk = clk_pin
        self._mosi = mosi_pin
        self._cmd_bits = 8
        self._param_bits = 8

    def init(self, cmd_bits, param_bits):
        self._cmd_bits = cmd_bits
        self._param_bits = param_bits
        # idle: CS deasserted (high), CLK low
        self._tca.digital_write(self._cs, 1)
        self._tca.digital_write(self._clk, 0)
        self._tca.digital_write(self._mosi, 0)

    def _shift(self, value, nbits):
        for i in range(nbits - 1, -1, -1):  # MSB first
            self._tca.digital_write(self._clk, 0)
            self._tca.digital_write(self._mosi, (value >> i) & 1)
            self._tca.digital_write(self._clk, 1)  # panel samples on rising edge

    def tx_param(self, cmd, params=None):
        self._tca.digital_write(self._cs, 0)  # assert (active low)
        # command: DC=0 then 8 command bits
        self._tca.digital_write(self._clk, 0)
        self._tca.digital_write(self._mosi, 0)  # DC bit = 0 (command)
        self._tca.digital_write(self._clk, 1)
        self._shift(cmd, self._cmd_bits)
        if params:
            for b in params:  # DC=1 then 8 data bits per byte
                self._tca.digital_write(self._clk, 0)
                self._tca.digital_write(self._mosi, 1)  # DC bit = 1 (data)
                self._tca.digital_write(self._clk, 1)
                self._shift(b, self._param_bits)
        self._tca.digital_write(self._cs, 1)  # deassert

    def deinit(self):
        pass
