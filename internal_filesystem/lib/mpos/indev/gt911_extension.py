# Copyright (c) 2024 - 2025 Kevin G. Schlosser

from micropython import const  # NOQA


_CONFIG_START_REG = const(0x8047)
_CONFIG_VERSION_POS = const(0x00)
_X_OUTPUT_MAX_LOW_POS = const(0x01)
_X_OUTPUT_MAX_HIGH_POS = const(0x02)
_Y_OUTPUT_MAX_LOW_POS = const(0x03)
_Y_OUTPUT_MAX_HIGH_POS = const(0x04)
# Touch Number 0x05
# Module_Switch1 0x06
# Module_Switch2 0x07
# Shake_Count 0x08
# Filter 0x09
# Large_Touch 0x0A
_NOISE_REDUCTION_POS = const(0x0B)
_TOUCH_PRESS_LEVEL_POS = const(0x0C)
_TOUCH_LEAVE_LEVEL_POS = const(0x0D)
# Low_Power_Control 0x0E
# Refresh_Rate 0x0F
# x_threshold 0x10
# y_threshold 0x11
# X_Speed_Limit 0x12
# y_Speed_Limit 0x13
_VER_SPACE_POS = const(0x14)  # const(0x805B)  # low 4 bits are bottom and hight is top
_HOR_SPACE_POS = const(0x15)  # const(0x805C)  # low 4 bits is right and high is left

_CONFIG_CHKSUM_REG = const(0x80FF)
_CONFIG_FRESH_REG = const(0x8100)
# 0-15 * 32


class GT911Extension(object):

    def _read_reg(self, reg, num_bytes=None, buf=None):
        self._tx_buf[0] = reg >> 8
        self._tx_buf[1] = reg & 0xFF
        if num_bytes is not None:
            self._i2c.write_readinto(self._tx_mv[:2], self._rx_mv[:num_bytes])
        else:
            self._i2c.write_readinto(self._tx_mv[:2], buf)

    def _write_reg(self, reg, value=None, buf=None):
        if value is not None:
            self._tx_buf[0] = value
            self._i2c.write_mem(reg, self._tx_mv[:1])
        elif buf is not None:
            self._i2c.write_mem(reg, buf)

    def __init__(self, indev, i2c):
        self._indev = indev
        self._i2c = i2c

        self._tx_buf = bytearray(3)
        self._tx_mv = memoryview(self._tx_buf)
        self._rx_buf = bytearray(6)
        self._rx_mv = memoryview(self._rx_buf)

        self._config_data = bytearray(_CONFIG_FRESH_REG - _CONFIG_START_REG + 1)
        self._config_mv = memoryview(self._config_data)

        self._read_reg(_CONFIG_START_REG, buf=self._config_mv[:-2])

    @property
    def width(self):
        return (
            (self._config_data[_X_OUTPUT_MAX_HIGH_POS] << 8) |
            self._config_data[_X_OUTPUT_MAX_LOW_POS]
        )

    @width.setter
    def width(self, value):
        self._config_data[_X_OUTPUT_MAX_LOW_POS] = value & 0xFF
        self._config_data[_X_OUTPUT_MAX_HIGH_POS] = (value >> 8) & 0xFF

    @property
    def height(self):
        return (
            (self._config_data[_Y_OUTPUT_MAX_HIGH_POS] << 8) |
            self._config_data[_Y_OUTPUT_MAX_LOW_POS]
        )

    @height.setter
    def height(self, value):
        self._config_data[_Y_OUTPUT_MAX_LOW_POS] = value & 0xFF
        self._config_data[_Y_OUTPUT_MAX_HIGH_POS] = (value >> 8) & 0xFF

    @property
    def noise_reduction(self):
        return self._config_data[_NOISE_REDUCTION_POS] & 0x0F

    @noise_reduction.setter
    def noise_reduction(self, value):
        upper_val = self._config_data[_NOISE_REDUCTION_POS] >> 4
        self._config_data[_NOISE_REDUCTION_POS + 2] = (upper_val << 4) | (value & 0x0F)

    @property
    def touch_press_level(self):
        return self._config_data[_TOUCH_PRESS_LEVEL_POS]

    @touch_press_level.setter
    def touch_press_level(self, value):
        self._config_data[_TOUCH_PRESS_LEVEL_POS] = value & 0xFF

    @property
    def touch_leave_level(self):
        return self._config_data[_TOUCH_LEAVE_LEVEL_POS]

    @touch_leave_level.setter
    def touch_leave_level(self, value):
        self._config_data[_TOUCH_LEAVE_LEVEL_POS] = value & 0xFF

    @property
    def pad_left(self):
        return self._config_data[_HOR_SPACE_POS] >> 4

    @pad_left.setter
    def pad_left(self, value):
        self._config_data[_HOR_SPACE_POS] = (value << 4) | self.pad_right

    @property
    def pad_right(self):
        return self._config_data[_HOR_SPACE_POS] & 0xF

    @pad_right.setter
    def pad_right(self, value):
        self._config_data[_HOR_SPACE_POS] = (self.pad_left << 4) | (value & 0xF)

    @property
    def pad_top(self):
        return self._config_data[_VER_SPACE_POS] >> 4

    @pad_top.setter
    def pad_top(self, value):
        self._config_data[_VER_SPACE_POS] = (value << 4) | self.pad_bottom

    @property
    def pad_bottom(self):
        return self._config_data[_VER_SPACE_POS] & 0xF

    @pad_bottom.setter
    def pad_bottom(self, value):
        self._config_data[_VER_SPACE_POS] = (self.pad_top << 4) | (value & 0xF)

    def save(self):
        # calculate the checksum
        self._config_data[-2] = ((~sum(self._config_data[:-2])) + 1) & 0xFF

        # set the flag to save the data the data
        self._config_data[-1] = 0x01  # _CONFIG_FRESH_REG

        # write all config data to the touch IC
        self._write_reg(_CONFIG_START_REG, buf=self._config_mv)

        self._indev.hw_reset()
