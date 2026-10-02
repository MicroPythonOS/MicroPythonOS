# ST7701 register setup for the Waveshare ESP32-P4-WIFI6-Touch-LCD-4.3 panel
# (480x800, 2-lane MIPI-DSI, RGB565). The bank/gamma/power/timing values are
# the vendor's, transcribed from vendor_specific_init_default in Waveshare's
# BSP (waveshare/esp32_p4_wifi6_touch_lcd_4_3 1.0.1, esp32_p4_wifi6_touch_lcd_4_3.c);
# the first three writes are the bank-0 MADCTL/COLMOD setup Espressif's
# esp_lcd_st7701 MIPI driver sends ahead of the vendor table.

import time

# (command, parameters or None, delay in ms after the command)
_SEQ = (
    (0xFF, b'\x77\x01\x00\x00\x00', 0),  # Command2 off: bank 0
    (0x36, b'\x00', 0),                  # MADCTL: RGB order, no mirroring
    (0x3A, b'\x55', 0),                  # COLMOD: 16 bits per pixel (RGB565)

    (0xFF, b'\x77\x01\x00\x00\x13', 0),  # Command2 BK3
    (0xEF, b'\x08', 0),

    (0xFF, b'\x77\x01\x00\x00\x10', 0),  # Command2 BK0
    (0xC0, b'\x63\x00', 0),              # display line setting
    (0xC1, b'\x0D\x02', 0),              # porch control
    (0xC2, b'\x17\x08', 0),              # inversion + frame rate
    (0xCC, b'\x10', 0),
    (0xB0, b'\x40\xC9\x94\x0E\x10\x05\x0B\x09\x08\x26\x04\x52\x10\x69\x6B\x69', 0),  # positive gamma
    (0xB1, b'\x40\xD2\x98\x0C\x92\x07\x09\x08\x07\x25\x02\x0E\x0C\x6E\x78\x55', 0),  # negative gamma

    (0xFF, b'\x77\x01\x00\x00\x11', 0),  # Command2 BK1
    (0xB0, b'\x5D', 0),                  # VOP amplitude
    (0xB1, b'\x4E', 0),                  # VCOM amplitude
    (0xB2, b'\x87', 0),                  # VGH
    (0xB3, b'\x80', 0),
    (0xB5, b'\x4E', 0),                  # VGL
    (0xB7, b'\x85', 0),                  # power control 1
    (0xB8, b'\x21', 0),                  # power control 2
    (0xB9, b'\x10\x1F', 0),
    (0xBB, b'\x03', 0),
    (0xBC, b'\x00', 0),
    (0xC1, b'\x78', 0),                  # source pre-drive timing
    (0xC2, b'\x78', 0),                  # source EQ2
    (0xD0, b'\x88', 0),                  # MIPI setting 1
    (0xE0, b'\x00\x3A\x02', 0),
    (0xE1, b'\x04\xA0\x00\xA0\x05\xA0\x00\xA0\x00\x40\x40', 0),
    (0xE2, b'\x30\x00\x40\x40\x32\xA0\x00\xA0\x00\xA0\x00\xA0\x00', 0),
    (0xE3, b'\x00\x00\x33\x33', 0),
    (0xE4, b'\x44\x44', 0),
    (0xE5, b'\x09\x2E\xA0\xA0\x0B\x30\xA0\xA0\x05\x2A\xA0\xA0\x07\x2C\xA0\xA0', 0),
    (0xE6, b'\x00\x00\x33\x33', 0),
    (0xE7, b'\x44\x44', 0),
    (0xE8, b'\x08\x2D\xA0\xA0\x0A\x2F\xA0\xA0\x04\x29\xA0\xA0\x06\x2B\xA0\xA0', 0),
    (0xEB, b'\x00\x00\x4E\x4E\x00\x00\x00', 0),
    (0xEC, b'\x08\x01', 0),
    (0xED, b'\xB0\x2B\x98\xA4\x56\x7F\xFF\xFF\xFF\xFF\xF7\x65\x4A\x89\xB2\x0B', 0),
    (0xEF, b'\x08\x08\x08\x45\x3F\x54', 0),

    (0xFF, b'\x77\x01\x00\x00\x00', 0),  # back to bank 0
    (0x11, None, 120),                   # SLPOUT, then the mandatory 120 ms
    (0x29, None, 0),                     # DISPON
)


def init(self):
    for cmd, params, delay in _SEQ:
        if params is None:
            self.set_params(cmd)
        else:
            self.set_params(cmd, params)
        if delay:
            time.sleep_ms(delay)  # NOQA
