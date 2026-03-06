# Copyright (c) 2024 - 2025 Kevin G. Schlosser

import time

import machine
import pointer_framework
from micropython import const

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

    def _read_reg(self, reg, num_bytes):
        self._tx_buf[0] = reg

        self.cs_pin.value(0)  # Select the device
        try:
            self._device.write_readinto(
                self._tx_mv[:num_bytes], self._rx_mv[:num_bytes]
            )
        finally:
            self.cs_pin.value(1)  # Deselect the device
        return ((self._rx_buf[1] << 8) | self._rx_buf[2]) >> 3

    def _write_reg(self, reg, value):
        self._tx_buf[0] = reg
        self._tx_buf[1] = value

        self.cs_pin.value(0)  # Select the device
        try:
            self._device.write(self._tx_mv[:2])
        finally:
            self.cs_pin.value(1)  # Deselect the device

    def __init__(
        self,
        device,
        spi_cs_touch,
        touch_cal=None,
        startup_rotation=pointer_framework.lv.DISPLAY_ROTATION._0,  # NOQA
        debug=False,
    ):
        self._device = device
        self.cs_pin = machine.Pin(spi_cs_touch, machine.Pin.OUT)
        self.cs_pin.value(1)  # Deselect the device
        self._debug = debug
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

        self.next_check = time.time() + 1

    def _get_coords(self):
        z1 = self._read_reg(_CMD_Z1_READ, 3)
        z2 = self._read_reg(_CMD_Z2_READ, 3)

        if time.time() > self.next_check:
            self.next_check = time.time() + 1
            x = self._read_reg(_CMD_X_READ, 3)
            y = self._read_reg(_CMD_Y_READ, 3)
            print(f"{z1=}, {z2=}, {x=}, {y=}")

        z = z1 + ((_MAX_RAW_COORD + 6) - z2)

        if z < self.touch_threshold:
            return None

        points = self.__points
        count = 0
        timeout = 5000
        start_time = time.ticks_us()  # NOQA
        while timeout > 0:
            if count == self.__confidence:
                break

            sample = self._get_raw()  # get a touch
            if sample is not None:
                points[count][0], points[count][1] = sample  # put in buff
                count += 1

            end_time = time.ticks_us()  # NOQA
            timeout -= time.ticks_diff(end_time, start_time)  # NOQA
            start_time = end_time

        if count:
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

            if dev <= self.__margin:
                x, y = self._normalize(meanx, meany)
                if self._debug:
                    print(
                        f"{self.__class__.__name__}_TP_DATA(x={meanx}, y={meany}, z={z})"
                    )  # NOQA
                return self.PRESSED, x, y

        return None

    def _normalize(self, x, y):
        x = pointer_framework.remap(
            x, _MIN_RAW_COORD, _MAX_RAW_COORD, 0, self._orig_width
        )
        y = pointer_framework.remap(
            y, _MIN_RAW_COORD, _MAX_RAW_COORD, 0, self._orig_height
        )

        return x, y

    def _get_raw(self):
        x = self._read_reg(_CMD_X_READ, 3)
        y = self._read_reg(_CMD_Y_READ, 3)
        if x > _MIN_RAW_COORD and y < _MAX_RAW_COORD:  # touch pressed?
            return x, y
        else:
            return None
