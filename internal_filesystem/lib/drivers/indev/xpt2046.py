# Copyright (c) 2024 - 2025 Kevin G. Schlosser

import lvgl as lv  # NOQA
from micropython import const  # NOQA
import micropython  # NOQA
import machine  # NOQA
import pointer_framework
import time


_CMD_X_READ = const(0xD0)  # 12 bit resolution
_CMD_Y_READ = const(0x90)  # 12 bit resolution
_CMD_Z1_READ = const(0xB0)
_CMD_Z2_READ = const(0xC0)
_MIN_RAW_COORD = const(10)
_MAX_RAW_COORD = const(4090)


class XPT2046(pointer_framework.PointerDriver):
    touch_threshold = 400
    confidence = 5
    margin = 50

    def __init__(
        self,
        device: machine.SPI.Bus,
        display_width: int,
        display_height: int,
        lcd_cs: int,
        touch_cs: int,
        touch_cal=None,
        startup_rotation=lv.DISPLAY_ROTATION._0,
        debug=False,
    ):
        self._device = device  # machine.SPI.Bus() instance, shared with display
        self._debug = debug

        self.lcd_cs = machine.Pin(lcd_cs, machine.Pin.OUT, value=0)
        self.touch_cs = machine.Pin(touch_cs, machine.Pin.OUT, value=1)

        self._width = display_width
        self._height = display_height

        self._tx_buf = bytearray(3)
        self._tx_mv = memoryview(self._tx_buf)

        self._rx_buf = bytearray(3)
        self._rx_mv = memoryview(self._rx_buf)

        self.__confidence = max(min(self.confidence, 25), 3)
        self.__points = [[0, 0] for _ in range(self.__confidence)]

        margin = max(min(self.margin, 100), 1)
        self.__margin = margin * margin

        super().__init__(
            touch_cal=touch_cal, startup_rotation=startup_rotation, debug=debug
        )

    def _read_reg(self, reg, num_bytes):
        self._tx_buf[0] = reg
        self._device.write_readinto(self._tx_mv[:num_bytes], self._rx_mv[:num_bytes])
        return ((self._rx_buf[1] << 8) | self._rx_buf[2]) >> 3

    def _get_coords(self):
        try:
            self.lcd_cs.value(1)  # deselect LCD to avoid conflicts
            self.touch_cs.value(0)  # select touch chip

            z1 = self._read_reg(_CMD_Z1_READ, 3)
            z2 = self._read_reg(_CMD_Z2_READ, 3)
            z = z1 + ((_MAX_RAW_COORD + 6) - z2)
            if z < self.touch_threshold:
                return None  # Not touched

            points = self.__points
            count = 0
            end_time = time.ticks_us() + 5000
            while time.ticks_us() < end_time:
                if count == self.__confidence:
                    break

                raw_x = self._read_reg(_CMD_X_READ, 3)
                if raw_x < _MIN_RAW_COORD:
                    continue

                raw_y = self._read_reg(_CMD_Y_READ, 3)
                if raw_y > _MAX_RAW_COORD:
                    continue

                # put in buff
                points[count][0] = raw_x
                points[count][1] = raw_y
                count += 1

        finally:
            self.touch_cs.value(1)  # deselect touch chip
            self.lcd_cs.value(0)  # select LCD

        if not count:
            return None  # Not touched

        meanx = sum([points[i][0] for i in range(count)]) // count
        meany = sum([points[i][1] for i in range(count)]) // count
        dev = (
            sum(
                [
                    (points[i][0] - meanx) ** 2 + (points[i][1] - meany) ** 2
                    for i in range(count)
                ]
            )
            / count
        )
        if dev >= self.__margin:
            return None  # Not touched

        x = pointer_framework.remap(
            meanx, _MIN_RAW_COORD, _MAX_RAW_COORD, 0, self._orig_width
        )
        y = pointer_framework.remap(
            meany, _MIN_RAW_COORD, _MAX_RAW_COORD, 0, self._orig_height
        )
        if self._debug:
            print(
                f"{self.__class__.__name__}_TP_DATA({count=} {meanx=} {meany=} {z1=} {z2=} {z=})"
            )  # NOQA
        return self.PRESSED, x, y
