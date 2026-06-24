from micropython import const

import pointer_framework


I2C_ADDR = const(0x3B)

_TOUCH_CMD = bytes([
    0xB5, 0xAB, 0xA5, 0x5A,
    0x00, 0x00, 0x00, 0x0E,
    0x00, 0x00, 0x00
])


class AXS15231BTouch(pointer_framework.PointerDriver):

    def __init__(
        self,
        device,
        touch_cal=None,
        startup_rotation=pointer_framework.lv.DISPLAY_ROTATION._0,
        debug=False
    ):
        self._device = device
        self._tx_buf = bytearray(11)
        self._tx_mv = memoryview(self._tx_buf)
        self._rx_buf = bytearray(14)
        self._rx_mv = memoryview(self._rx_buf)

        super().__init__(
            touch_cal=touch_cal,
            startup_rotation=startup_rotation,
            debug=debug
        )

    def _get_coords(self):
        try:
            self._tx_mv[:] = _TOUCH_CMD
            self._device.write_readinto(self._tx_mv[:11], self._rx_mv[:14])
        except Exception:
            return None

        if self._buf[0] == 0xFF:
            return None
        num = self._buf[1]
        if num == 0 or num > 2:
            return None
        if self._buf[3] < 2 or self._buf[5] < 2:
            return None

        x = ((self._buf[2] & 0x0F) << 8) | self._buf[3]
        y = ((self._buf[4] & 0x0F) << 8) | self._buf[5]

        return self.PRESSED, x, y
