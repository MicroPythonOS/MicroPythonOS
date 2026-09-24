import logging

logger = logging.getLogger(__name__)

if __debug__: logger.debug("waveshare_esp32_p4_wifi6_touch_lcd_4_3.py initialization")
# Hardware initialization for the Waveshare ESP32-P4-WIFI6-Touch-LCD-4.3:
# ESP32-P4 (RISC-V) with an ESP32-C6 Wi-Fi 6 / BLE co-processor over SDIO
# (esp_hosted), 32 MB flash, 32 MB PSRAM, 4.3" 480x800 portrait IPS over
# 2-lane MIPI-DSI (ST7701), GT911 capacitive touch, ES8311 codec + ES7210
# microphone ADC, TF card slot (4-bit SDIO), MIPI-CSI camera connector,
# USB host port.
#
# Manufacturer's wiki: https://www.waveshare.com/wiki/ESP32-P4-WIFI6-Touch-LCD-4.3
# Pins, panel timings and the ST7701 register table come from Waveshare's
# ESP-IDF BSP (waveshare/esp32_p4_wifi6_touch_lcd_4_3 1.0.1).
#
# The panel is used in its native portrait orientation (480 wide, 800 high):
# the ST7701 cannot swap rows and columns for the video interface, and the
# enclosure's cable/button placement suits portrait.

import time

import i2c
import lcd_bus
import lvgl as lv
import machine
import mpos.ui
from drivers.display.st7701_dsi import ST7701_DSI
import drivers.indev.gt911 as gt911
from mpos import InputManager

LCD_WIDTH = 480
LCD_HEIGHT = 800
LCD_RST = 27
LCD_BL = 26          # backlight enable, PWM dimmable, ACTIVE LOW (the BSP drives its LEDC channel inverted)

I2C_SDA = 7
I2C_SCL = 8
I2C_FREQ = 400000

TOUCH_ADDRS = (0x5D, 0x14)   # GT911; the strap at reset picks one

# === BACKLIGHT ===
# Kept off (pin high) until the panel shows its first frame, so the boot does
# not flash a white screen.
_backlight = machine.PWM(machine.Pin(LCD_BL), freq=5000, duty_u16=65535)
_backlight_percent = 0


def _set_backlight(percent):
    global _backlight_percent
    percent = max(0, min(100, int(percent)))
    _backlight_percent = percent
    _backlight.duty_u16(65535 - percent * 65535 // 100)  # active low: 0% = pin high


def _get_backlight():
    return _backlight_percent


# === DISPLAY (ST7701 over MIPI-DSI) ===
# Video mode: the DPI DMA scans two screen-sized frame buffers (in PSRAM) out
# to the panel continuously, LVGL renders straight into them. The DSI PHY is
# powered by the P4's internal LDO channel 3.
display_bus = lcd_bus.DSIBus(
    bus_id=0,
    data_lanes=2,
    freq=500,             # lane bit rate, Mbps
    dpi_clock_freq=30,    # DPI pixel clock, MHz
    virtual_channel=0,
    hsync_back_porch=42,
    hsync_pulse_width=12,
    hsync_front_porch=42,
    vsync_back_porch=2,
    vsync_pulse_width=8,
    vsync_front_porch=60,
    phy_ldo_channel=3,
    phy_ldo_voltage_mv=2500,
)

_FB_SIZE = const(480 * 800 * 2)  # RGB565, whole screen: 768000 bytes
fb1 = display_bus.allocate_framebuffer(_FB_SIZE, lcd_bus.MEMORY_SPIRAM)
fb2 = display_bus.allocate_framebuffer(_FB_SIZE, lcd_bus.MEMORY_SPIRAM)

mpos.ui.main_display = ST7701_DSI(
    data_bus=display_bus,
    frame_buffer1=fb1,
    frame_buffer2=fb2,
    display_width=LCD_WIDTH,
    display_height=LCD_HEIGHT,
    reset_pin=LCD_RST,
    reset_state=ST7701_DSI.STATE_LOW,
    color_space=lv.COLOR_FORMAT.RGB565,
    color_byte_order=ST7701_DSI.BYTE_ORDER_RGB,
)  # triggers lv.init()
mpos.ui.main_display.init()
if __debug__: logger.debug("ST7701 panel ID: %s", mpos.ui.main_display.panel_id)

mpos.ui.main_display.set_backlight = _set_backlight
mpos.ui.main_display.get_backlight = _get_backlight

# Push a first frame now: the bus starts the DSI video stream on the first
# flush, and the backlight only goes on once the panel has something to show.
try:
    lv.refr_now(None)
except Exception as e:
    logger.error("initial refresh failed: %s" % (e))
mpos.ui.main_display.set_backlight(100)

# === TOUCH (GT911) ===
# Neither its reset nor its interrupt line is wired to the P4 on this board,
# so the controller is polled at whichever address its strap selected.
i2c_bus = i2c.I2C.Bus(host=0, scl=I2C_SCL, sda=I2C_SDA, freq=I2C_FREQ, use_locks=False)
try:
    present = i2c_bus.scan()
    touch_addr = next((a for a in TOUCH_ADDRS if a in present), None)
    if touch_addr is None:
        raise RuntimeError("GT911 not found on I2C (devices: %s)" % [hex(a) for a in present])
    touch_dev = i2c.I2C.Device(bus=i2c_bus, dev_id=touch_addr, reg_bits=gt911.BITS)
    indev = gt911.GT911(touch_dev)
    InputManager.register_indev(indev)
except Exception as e:
    logger.error("GT911 init failed: %s" % (e))

if __debug__: logger.debug("waveshare_esp32_p4_wifi6_touch_lcd_4_3.py finished")
