# Copyright (c) 2024 - 2025 Kevin G. Schlosser

from micropython import const  # NOQA
import pointer_framework
import machine  # NOQA


# Register of the current mode
_DEV_MODE_REG = const(0x00)

# ** Possible modes as of FT6X36_DEV_MODE_REG **
_DEV_MODE_WORKING = const(0x00)
_CTRL = const(0x86)


# Status register: stores number of active touch points (0, 1, 2)
_TD_STAT_REG = const(0x02)
_P1_XH = const(0x03)
_P1_XL = const(0x04)

_P1_YH = const(0x05)
_P1_YL = const(0x06)

_MSB_MASK = const(0x0F)
_LSB_MASK = const(0xFF)

# Report rate in Active mode
_PERIOD_ACTIVE_REG = const(0x88)


_VENDID = const(0x11)
_CHIPID_REG = const(0xA3)

_FIRMWARE_ID_REG = const(0xA6)
_RELEASECODE_REG = const(0xAF)
_PANEL_ID_REG = const(0xA8)

_G_MODE = const(0xA4)

_MAX_TOUCH_POINTS = const(2)
_TOUCH_POINT_SIZE = const(6)


def parse_touch_points(buf, count, factors):
    points = []
    for index in range(count):
        offset = 1 + index * _TOUCH_POINT_SIZE
        x = ((buf[offset] & 0x0F) << 8) | buf[offset + 1]
        y = ((buf[offset + 2] & 0x0F) << 8) | buf[offset + 3]
        if factors is not None:
            x = round(x / factors[0])
            y = round(y / factors[1])
        points.append((index, x, y))
    return points


class FocalTechTouch(pointer_framework.PointerDriver):

    def __init__(
        self,
        device,
        touch_cal,
        startup_rotation,  # NOQA
        debug,
        factors,
        *chip_ids
    ):  # NOQA
        self._tx_buf = bytearray(5)
        self._tx_mv = memoryview(self._tx_buf)
        self._rx_buf = bytearray(1 + _MAX_TOUCH_POINTS * _TOUCH_POINT_SIZE)
        self._rx_mv = memoryview(self._rx_buf)

        self._device = device
        self._factors = factors
        self._touch_points = []
        self._multi_touch_active = False

        self._read_reg(_PANEL_ID_REG)
        print("Touch Device ID: 0x%02x" % self._rx_buf[0])
        ven_id = self._rx_buf[0]  # NOQA

        self._read_reg(_CHIPID_REG)
        print("Touch Chip ID: 0x%02x" % self._rx_buf[0])
        chip_id = self._rx_buf[0]

        self._read_reg(_DEV_MODE_REG)
        print("Touch Device mode: 0x%02x" % self._rx_buf[0])

        self._read_reg(_FIRMWARE_ID_REG)
        print("Touch Firmware ID: 0x%02x" % self._rx_buf[0])

        self._read_reg(_RELEASECODE_REG)
        print("Touch Release code: 0x%02x" % self._rx_buf[0])

        if chip_id not in chip_ids:
            raise RuntimeError(
                f'IC is not compatable with the {self.__class__.__name__} driver'  # NOQA
            )

        self._write_reg(_DEV_MODE_REG, _DEV_MODE_WORKING)
        self._write_reg(_PERIOD_ACTIVE_REG, 0x0E)
        self._write_reg(_G_MODE, 0x00)

        # This is needed so the TS doesn't go to sleep
        self._write_reg(_CTRL, 0x00)

        super().__init__(
            touch_cal=touch_cal, startup_rotation=startup_rotation, debug=debug
        )

    def _get_coords(self):
        self._tx_buf[0] = _TD_STAT_REG
        try:
            self._device.write_readinto(self._tx_mv[:1], self._rx_mv)
        except OSError:
            return None

        touch_pnt_cnt = self._rx_buf[0] & 0x0F
        if touch_pnt_cnt > _MAX_TOUCH_POINTS:
            touch_pnt_cnt = _MAX_TOUCH_POINTS

        if touch_pnt_cnt:
            self._touch_points = parse_touch_points(
                self._rx_buf, touch_pnt_cnt, self._factors
            )
        else:
            self._touch_points = []

        if len(self._touch_points) >= 2:
            if not self._multi_touch_active:
                self._multi_touch_active = True
                self._indev_drv.wait_release()
            return None

        if self._multi_touch_active:
            if not self._touch_points:
                self._multi_touch_active = False
            return None

        if not self._touch_points:
            return None

        return self.PRESSED, self._touch_points[0][1], self._touch_points[0][2]

    def get_touches(self):
        touches = []
        for point_id, x, y in self._touch_points:
            logical_x, logical_y = self._calc_coords(x, y)
            touches.append((point_id, logical_x, logical_y))
        return touches

    def get_touch_count(self):
        return len(self._touch_points)

    def _read_reg(self, reg):
        self._tx_buf[0] = reg
        self._rx_buf[0] = 0x00

        self._device.write_readinto(self._tx_mv[:1], self._rx_mv[:1])

    def _write_reg(self, reg, value):
        self._tx_buf[0] = reg
        self._tx_buf[1] = value
        self._device.write(self._tx_mv[:2])
