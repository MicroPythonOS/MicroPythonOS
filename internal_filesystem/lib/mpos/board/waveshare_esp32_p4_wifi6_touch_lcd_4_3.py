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
# The panel is natively portrait (480 wide, 800 high) and the ST7701 cannot
# swap rows and columns on the video interface, so the landscape UI (800x480,
# like the other MicroPythonOS boards) is produced by the P4's PPA (pixel
# processing accelerator): LVGL renders landscape, the DSI bus rotates each
# finished update into the panel's back buffer. LCD_ROTATION picks which
# way is up (270 is upright in the enclosure, 90 is upside down); 0 would
# give the native portrait.

import time

import i2c
import lcd_bus
import lvgl as lv
import machine
import mpos.ui
from drivers.display.st7701_dsi import ST7701_DSI
import drivers.indev.gt911 as gt911
from mpos import InputManager

LCD_WIDTH = 480      # panel (physical) size
LCD_HEIGHT = 800
LCD_ROTATION = 270   # 270 or 90: landscape (which way is up; 90 is upside down in the enclosure), 0: native portrait
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
    rotation=LCD_ROTATION,
)

# Two screen-sized LVGL buffers (landscape); the panel's own two portrait
# frame buffers are managed by the bus (see drivers.display.st7701_dsi).
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
    rotation={0: lv.DISPLAY_ROTATION._0, 90: lv.DISPLAY_ROTATION._90,
              180: lv.DISPLAY_ROTATION._180, 270: lv.DISPLAY_ROTATION._270}[LCD_ROTATION],
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
# so the controller is polled at whichever address its strap selected. It
# reports panel (portrait) coordinates; LVGL maps them to the rotated UI.
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

# === AUDIO (ES8311 codec -> onboard power amplifier -> speaker connector) ===
# I2S pins and the amplifier enable from Waveshare's BSP: MCLK=13, BCLK=12,
# LRCK=10, ESP32->codec (playback)=9, codec->ESP32=11, PA enable GPIO53
# (active high). Codec control is I2C @0x18 on the shared bus. The
# microphones go through a separate ES7210 ADC (I2C @0x40, same I2S bus),
# which MicroPythonOS has no driver for yet, so only playback is wired up.
PA_ENABLE = 53
_es8311 = None
try:
    import drivers.codec.es8311 as es8311_drv

    class _CodecI2C:
        """Adapt the lcd_bus i2c wrapper to the machine.I2C-style API the
        ES8311 driver expects (writeto_mem/readfrom_mem_into)."""

        def __init__(self, bus, dev_id):
            self._dev = i2c.I2C.Device(bus=bus, dev_id=dev_id, reg_bits=8)

        def writeto_mem(self, addr, reg, data):
            self._dev.write_mem(reg, data)

        def readfrom_mem_into(self, addr, reg, buf):
            self._dev.read_mem(reg, buf=buf)

    _es8311 = es8311_drv.ES8311(_CodecI2C(i2c_bus, es8311_drv.I2C_ADDR))
    # Same starting point as the ESP32-S3-Touch-LCD-3.5 (76% was the loudest
    # clean setting through its speaker); this board's amplifier still needs
    # an ear on it.
    _es8311.set_dac_volume(76)
except Exception as e:
    logger.error("ES8311 init failed: %s" % (e))

# Amplifier off at boot; enabled only around playback to keep it quiet.
_pa_enable = machine.Pin(PA_ENABLE, machine.Pin.OUT, value=0)


def _audio_on_open():
    """Called after MCLK starts and before I2S init: amplifier on, DAC unmuted."""
    _pa_enable.value(1)
    if _es8311:
        time.sleep_ms(10)         # let the amplifier settle before unmuting
        _es8311.dac_mute(False)


def _audio_on_close():
    """Called before I2S deinit: soft-mute the DAC, then amplifier off, to suppress pops."""
    if _es8311:
        _es8311.dac_mute(True)
        time.sleep_ms(20)
    _pa_enable.value(0)


if _es8311:
    from mpos import AudioManager

    AudioManager.add(
        AudioManager.Output(
            name="Speaker",
            kind="i2s",
            channels=1,
            i2s_pins={
                'mck': 13,  # MCLK - 256 x sample_rate during playback
                'sck': 12,  # BCLK
                'ws':  10,  # LRCK
                'sd':  9,   # I2S TX (ESP32-P4 -> ES8311 DAC)
            },
            on_open=_audio_on_open,
            on_close=_audio_on_close,
            # Like the other ES8311 boards this one clicks on every MCLK/I2S
            # restart; once the opt-in warm output (PR #301) lands, add
            # warm_ms=30000 here so back-to-back clips stay silent.
        )
    )

if __debug__: logger.debug("waveshare_esp32_p4_wifi6_touch_lcd_4_3.py finished")
