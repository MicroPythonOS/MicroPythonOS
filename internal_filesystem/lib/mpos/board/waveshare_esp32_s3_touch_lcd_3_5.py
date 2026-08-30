import logging

logger = logging.getLogger(__name__)

if __debug__: logger.debug("waveshare_esp32_s3_touch_lcd_3_5.py initialization")
# Hardware initialization for the Waveshare ESP32-S3-Touch-LCD-3.5:
# 3.5" 320x480 IPS (ST7796 over SPI), FT6336 capacitive touch, QMI8658 IMU,
# PCF85063 RTC, AXP2101 power management, ES8311 audio codec, TF card slot,
# camera connector (OV5640/OV2640 supported but NOT included with the board).
#
# Manufacturer's wiki: https://www.waveshare.com/wiki/ESP32-S3-Touch-LCD-3.5
# Schematic: https://files.waveshare.com/wiki/ESP32-S3-Touch-LCD-3.5/ESP32-S3-Touch-LCD-3.5-Schematic.pdf
#
# Unlike the ESP32-S3-Touch-LCD-2, the LCD's reset and chip-select lines are
# NOT on ESP32 GPIOs: they sit behind a PCA9554 I2C IO expander (EXIO1 = LCD
# reset, EXIO2 = LCD chip select). Since the display is the only device on
# the SPI bus, CS is simply driven low once at init and left there, and the
# SPI bus is created without a CS pin.

import time

import drivers.display.st7796 as st7796
import drivers.indev.ft6x36 as ft6x36
import i2c
import lcd_bus
import lvgl as lv
import machine
import mpos.ui
from drivers.io_expander.pca9554 import PCA9554
from mpos import InputManager

# Pin configuration (from the Waveshare demo code / schematic)
SPI_BUS = 2
SPI_FREQ = 40000000
LCD_SCLK = 5
LCD_MOSI = 1
LCD_MISO = 2
LCD_DC = 3
LCD_BL = 6

I2C_SDA = 8
I2C_SCL = 7

EXPANDER_ADDR = 0x20   # PCA9554
EXIO_LCD_RESET = 1     # EXIO1
EXIO_LCD_CS = 2        # EXIO2

TOUCH_ADDR = 0x38      # FT6336
PMU_ADDR = 0x34        # AXP2101
IMU_ADDR = 0x6B        # QMI8658

# Shared I2C bus: PCA9554 expander, FT6336 touch, AXP2101 PMU, QMI8658 IMU,
# PCF85063 RTC (0x51), ES8311 codec.
i2c_bus = i2c.I2C.Bus(host=0, scl=I2C_SCL, sda=I2C_SDA, freq=400000, use_locks=False)

# Bring the LCD out of reset and assert its chip select via the expander,
# BEFORE initializing the display controller over SPI.
expander = PCA9554(i2c_bus, EXPANDER_ADDR)
expander.set_output(EXIO_LCD_CS, False)    # CS low = selected (sole SPI device)
expander.set_output(EXIO_LCD_RESET, False) # pulse reset
time.sleep_ms(10)
expander.set_output(EXIO_LCD_RESET, True)
time.sleep_ms(120)                         # ST7796 needs ~120ms after reset

if __debug__: logger.debug("waveshare_esp32_s3_touch_lcd_3_5.py machine.SPI.Bus() initialization")
try:
    spi_bus = machine.SPI.Bus(host=SPI_BUS, mosi=LCD_MOSI, miso=LCD_MISO, sck=LCD_SCLK)
except Exception as e:
    logger.error("Error initializing SPI bus: %s" % (e))
    if __debug__: logger.debug("Attempting hard reset in 3sec...")
    time.sleep(3)
    machine.reset()

display_bus = lcd_bus.SPIBus(
    spi_bus=spi_bus,
    freq=SPI_FREQ,
    dc=LCD_DC,
    cs=-1,  # chip select is on the PCA9554 expander, held low above
)

# 320*480*2 = 307200 bytes full frame; use a DMA-capable strip like the
# LCD-2 board does (320*45*2=28800 there). 320*48*2=30720 is a round strip
# of 1/10th of this taller panel; tune once hardware timing is measured.
_BUFFER_SIZE = const(320 * 48 * 2)  # 30720
fb1 = display_bus.allocate_framebuffer(_BUFFER_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)
fb2 = display_bus.allocate_framebuffer(_BUFFER_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)

mpos.ui.main_display = st7796.ST7796(
    data_bus=display_bus,
    frame_buffer1=fb1,
    frame_buffer2=fb2,
    display_width=320,
    display_height=480,
    color_space=lv.COLOR_FORMAT.RGB565,
    color_byte_order=st7796.BYTE_ORDER_BGR,
    rgb565_byte_swap=True,
    backlight_pin=LCD_BL,
    backlight_on_state=st7796.STATE_PWM,
)  # triggers lv.init()
mpos.ui.main_display.init()
mpos.ui.main_display.set_power(True)
mpos.ui.main_display.set_backlight(100)

# Touch handling:
touch_dev = i2c.I2C.Device(bus=i2c_bus, dev_id=TOUCH_ADDR, reg_bits=8)
indev = ft6x36.FT6x36(touch_dev)
InputManager.register_indev(indev)

# Landscape, like the other MPOS boards; must be done after initializing the
# display and creating the touch driver so both agree on the orientation.
mpos.ui.main_display.set_rotation(lv.DISPLAY_ROTATION._90)

# === POWER MANAGEMENT (AXP2101) ===
# Battery charge/percentage via the PMU instead of a raw ADC pin.
# Same approach as lilygo_t_watch_s3_plus.
try:
    from drivers.power.AXP2101 import AXP2101

    from mpos import BatteryManager
    pmu = AXP2101(i2c_bus, addr=PMU_ADDR)
    BatteryManager.read_raw_adc = lambda *args: 0
    BatteryManager.has_battery = lambda *args: True
    BatteryManager.get_battery_percentage = pmu.getBatteryPercent
except Exception as e:
    logger.error("AXP2101 init failed: %s" % (e))

# === SENSOR HARDWARE ===
# QMI8658 IMU on the shared I2C bus. Mounted position needs on-hardware
# verification; FACING_EARTH matches the LCD-2 which uses the same IMU.
from mpos import SensorManager

SensorManager.init(i2c_bus, address=IMU_ADDR, mounted_position=SensorManager.FACING_EARTH)

# === AUDIO (ES8311 codec, onboard speaker connector + microphone) ===
# I2S pins from Waveshare's demo code (01_audio_out / 04_es8311_example):
# MCLK=12, BCLK=13, LRCK/WS=15, ESP32->codec (playback)=16, codec->ESP32
# (microphone)=14. Codec control is I2C @0x18 on the shared bus. The
# board has no separate speaker-amp enable pin in Waveshare's examples,
# so only the codec's DAC soft-mute is used for pop suppression.
_es8311 = None
try:
    import time as _time

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

    _es8311 = es8311_drv.ES8311(_CodecI2C(i2c_bus, 0x18))
    # 76% was picked by ear on real hardware: the driver's 85% default is
    # audibly distorted through the speaker connector, 70% is clean but
    # quiet, 76% is the loudest clean setting.
    _es8311.set_dac_volume(76)
except Exception as e:
    logger.error("ES8311 init failed: %s" % (e))


def _audio_on_open():
    """Called after MCLK starts and before I2S init: release DAC soft-mute."""
    if _es8311:
        _time.sleep_ms(10)
        _es8311.dac_mute(False)


def _audio_on_close():
    """Called before I2S deinit: soft-mute the DAC to suppress pops."""
    if _es8311:
        _es8311.dac_mute(True)
        _time.sleep_ms(20)


if _es8311:
    from mpos import AudioManager

    AudioManager.add(
        AudioManager.Output(
            name="Speaker",
            kind="i2s",
            channels=1,
            i2s_pins={
                'mck': 12,  # MCLK - 256 x sample_rate during playback
                'sck': 13,  # BCLK
                'ws':  15,  # LRCK
                'sd':  16,  # I2S TX (ESP32 -> ES8311 DAC)
            },
            on_open=_audio_on_open,
            on_close=_audio_on_close,
        )
    )

    AudioManager.add(
        AudioManager.Input(
            name="Microphone",
            kind="i2s",
            channels=1,
            i2s_pins={
                'mck':   12,
                'sck':   13,
                'ws':    15,
                'sd_in': 14,  # I2S RX (ES8311 ADC -> ESP32)
            },
            preferred_sample_rate=16000,
        )
    )

# === CAMERA ===
# The board has a camera connector (OV5640/OV2640 supported, none included).
# Pins from Waveshare's demo code (03_camera_web_server): the SCCB control
# bus shares the board's main I2C pins (sda=8/scl=7) with touch/codec/
# expander — Waveshare's own examples drive them together, and the sensor
# is auto-detected by the camera driver. PWDN/RESET are not wired (-1).
from mpos import CameraManager


def init_cam(width, height, colormode):
    toreturn = None
    try:
        from camera import Camera, GrabMode, PixelFormat

        frame_size = CameraManager.resolution_to_framesize(width, height)
        if __debug__: logger.debug("init_cam: FrameSize %s for %sx%s" % (frame_size, width, height))

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                cam = Camera(
                        data_pins=[45, 47, 48, 46, 42, 40, 39, 21],  # Y2..Y9
                        vsync_pin=17,
                        href_pin=18,
                        # SCCB shares the board's main I2C bus (sda=8/scl=7)
                        # with touch/codec/expander. Reuse the existing bus
                        # driver (port 0) instead of fighting it: concurrent
                        # touch polling otherwise garbles sensor config
                        # (wrong colors) and touch reads (dead buttons).
                        sda_pin=-1,
                        scl_pin=-1,
                        sccb_i2c_port=0,
                        pclk_pin=41,
                        xclk_pin=38,
                        xclk_freq=20000000,
                        powerdown_pin=-1,
                        reset_pin=-1,
                        pixel_format=PixelFormat.RGB565 if colormode else PixelFormat.GRAYSCALE,
                        frame_size=frame_size,
                        grab_mode=GrabMode.LATEST,
                        fb_count=1
                    )
                toreturn = cam
                break
            except Exception as e:
                if attempt < max_attempts - 1:
                    logger.error("init_cam attempt %s failed: %s, retrying..." % (attempt, e))
                else:
                    logger.error("init_cam final exception: %s" % (e))
                    break
    except Exception as e:
        logger.error("init_cam exception: %s" % (e))
    return toreturn


def deinit_cam(cam):
    cam.deinit()


def capture_cam(cam_obj, colormode):
    return cam_obj.capture()


def apply_cam_settings(cam_obj, prefs):
    return CameraManager.ov_apply_camera_settings(cam_obj, prefs)


CameraManager.add_camera(CameraManager.Camera(
    lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_BACK,
    name="Camera connector (OV5640/OV2640)",
    vendor="OmniVision",
    init=init_cam,
    deinit=deinit_cam,
    capture=capture_cam,
    apply_settings=apply_cam_settings,
    rotation_degrees=-90,  # tuned on hardware: preview needs 90 degrees clockwise correction
))

if __debug__: logger.debug("waveshare_esp32_s3_touch_lcd_3_5.py finished")
