import logging

logger = logging.getLogger(__name__)

if __debug__: logger.debug("unihiker_k10.py initialization")

# Hardware initialization for DFRobot UniHiker K10 (ESP32-S3)
# Product page: https://www.dfrobot.com/product-2676.html
# Display: ILI9341 2.0" TFT 240x320 SPI
# IO expander: XL9535 (I2C 0x20) — controls backlight and buttons
# No touchscreen; two physical buttons (BTN_A and BTN_B)

import time
import neopixel

import drivers.display.ili9341 as ili9341
import lcd_bus
import lvgl as lv
import machine
import mpos.ui
from machine import I2C, Pin
from micropython import const
from mpos import InputManager
from mpos.board.unihiker_k10_input import (
    K10ButtonInput,
    create_expander_i2c,
    initialize_camera_with_recovery,
    is_direct_navigation_target,
)
from mpos.ui.focus import enable_focus_borders

# ── Display SPI pins ────────────────────────────────────────────────────────
# K10 uses FSPI (SPI2, host=1) with CLK on GPIO12 (IO_MUX fast path)
SPI_BUS  = const(1)
SPI_FREQ = const(40000000)
LCD_SCLK = const(12)
LCD_MOSI = const(21)
LCD_DC   = const(13)
LCD_CS   = const(14)

TFT_WIDTH  = const(240)
TFT_HEIGHT = const(320)

# ── XL9535 I2C IO expander ──────────────────────────────────────────────────
# Controls backlight (P0.0) and reads buttons (P0.2 BTN_B, P1.4 BTN_A)
# All buttons are active-low with internal pull-ups on the expander
I2C_SDA = const(47)
I2C_SCL = const(48)
XL9535_ADDR = const(0x20)

# XL9535 register addresses
XL9535_IN0  = const(0x00)  # Input  Port 0 (read)
XL9535_IN1  = const(0x01)  # Input  Port 1 (read)
XL9535_OUT0 = const(0x02)  # Output Port 0 (write)
XL9535_OUT1 = const(0x03)  # Output Port 1 (write)
XL9535_CFG0 = const(0x06)  # Config Port 0 (0=output, 1=input)
XL9535_CFG1 = const(0x07)  # Config Port 1 (0=output, 1=input)

# Pin assignments within the expander
BL_BIT      = const(0x01)  # P0.0: backlight output  (active-high)
CAM_RST_BIT = const(0x02)  # P0.1: Camera_RST output (active-low; HIGH = running)
BTNB_BIT    = const(0x04)  # P0.2: BTN_B input       (active-low)
BTNA_BIT    = const(0x10)  # P1.4: BTN_A input       (active-low)

# ── XL9535 init: backlight ON, configure button pins as inputs ───────────────
if __debug__: logger.debug("unihiker_k10.py: initializing XL9535 I2C expander")
_i2c = None  # guarded: _keypad_read_cb catches AttributeError if init fails
try:
    _i2c = create_expander_i2c(I2C, Pin, I2C_SDA, I2C_SCL)
    if __debug__: logger.debug("unihiker_k10.py: XL9535 OK, backlight ON")
except Exception as e:
    logger.error("unihiker_k10.py: XL9535 init failed: %s", e)

# ── SPI display bus ──────────────────────────────────────────────────────────
if __debug__: logger.debug("unihiker_k10.py: initializing SPI bus")
try:
    spi_bus = machine.SPI.Bus(host=SPI_BUS, mosi=LCD_MOSI, sck=LCD_SCLK)
except Exception as e:
    logger.error("unihiker_k10.py: SPI bus init failed: %s", e)
    time.sleep(3)
    machine.reset()

display_bus = lcd_bus.SPIBus(
    spi_bus=spi_bus,
    freq=SPI_FREQ,
    dc=LCD_DC,
    cs=LCD_CS,
)

# 45 scan lines × 240 px × 2 bytes (RGB565) — matches freenove/waveshare pattern
_BUFFER_SIZE = const(240 * 45 * 2)
fb1 = display_bus.allocate_framebuffer(_BUFFER_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)
fb2 = display_bus.allocate_framebuffer(_BUFFER_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)

# ── ILI9341 display ──────────────────────────────────────────────────────────
if __debug__: logger.debug("unihiker_k10.py: initializing ILI9341 display")
mpos.ui.main_display = ili9341.ILI9341(
    data_bus=display_bus,
    frame_buffer1=fb1,
    frame_buffer2=fb2,
    display_width=TFT_WIDTH,
    display_height=TFT_HEIGHT,
    color_space=lv.COLOR_FORMAT.RGB565,
    color_byte_order=ili9341.BYTE_ORDER_BGR,
    # The K10 panel expects swapped RGB565 bytes on its SPI bus.
    rgb565_byte_swap=True,
)
# Type 2 = standard ILI9341 alternative init sequence (used by most SPI panels)
mpos.ui.main_display.init(2)
# The LCD is mounted upside down relative to the K10 enclosure orientation.
mpos.ui.main_display.set_rotation(lv.DISPLAY_ROTATION._180)
mpos.ui.main_display.set_power(True)
# Note: backlight is controlled via XL9535, not a GPIO pin — already turned on above

# ── Button input (keypad indev) ───────────────────────────────────────────────
# BTN_B: NEXT — cycles through focusable items; an open dropdown uses tap/hold for next/previous
# BTN_A: ENTER — selects / confirms the focused item; holding it cancels an open dropdown or goes back
_last_key = None
_button_input = K10ButtonInput(ticks_diff=time.ticks_diff)


def _keypad_read_cb(indev, data):
    global _last_key

    try:
        p0 = _i2c.readfrom_mem(XL9535_ADDR, XL9535_IN0, 1)[0]
        p1 = _i2c.readfrom_mem(XL9535_ADDR, XL9535_IN1, 1)[0]
        btn_a = not bool(p1 & BTNA_BIT)  # P1.4, active-low
        btn_b = not bool(p0 & BTNB_BIT)  # P0.2, active-low
    except Exception:
        current_key = _button_input.cancel()
        data.key = {
            "next": lv.KEY.NEXT,
            "right": lv.KEY.RIGHT,
            "left": lv.KEY.LEFT,
            "esc": lv.KEY.ESC,
        }.get(current_key, _last_key or lv.KEY.ENTER)
        data.state = lv.INDEV_STATE.RELEASED
        _last_key = None
        return

    focusgroup = lv.group_get_default()
    focused = focusgroup.get_focused() if focusgroup else None
    keyboard_focused = isinstance(focused, lv.keyboard) or isinstance(focused, lv.buttonmatrix)
    dropdown_open = isinstance(focused, lv.dropdown)
    if dropdown_open:
        try:
            dropdown_open = focused.is_open()
        except Exception:
            dropdown_open = False
    direct_navigation_focused = is_direct_navigation_target(
        focused, lv.keyboard, lv.buttonmatrix, lv.dropdown
    )
    if keyboard_focused:
        focused.add_state(lv.STATE.FOCUS_KEY)
    action, pressed, back = _button_input.update(
        btn_a,
        btn_b,
        time.ticks_ms(),
        direct_navigation_focused,
        dropdown_open,
    )

    if back:
        mpos.ui.back_screen()
    if action in ("next", "right", "left") and pressed:
        enable_focus_borders()

    current_key = {
        "enter": lv.KEY.ENTER,
        "next": lv.KEY.NEXT,
        "right": lv.KEY.RIGHT,
        "left": lv.KEY.LEFT,
        "esc": lv.KEY.ESC,
    }.get(action)
    if current_key is None:
        data.key = _last_key if _last_key else lv.KEY.ENTER
        data.state = lv.INDEV_STATE.RELEASED
        _last_key = None
        return

    data.key = current_key
    data.state = lv.INDEV_STATE.PRESSED if pressed else lv.INDEV_STATE.RELEASED
    _last_key = current_key if pressed else None


indev = lv.indev_create()
indev.set_type(lv.INDEV_TYPE.KEYPAD)
indev.set_read_cb(_keypad_read_cb)
indev.set_group(lv.group_get_default())
indev.set_display(lv.display_get_default())
indev.enable(True)
InputManager.register_indev(indev)

# ── SPI3 (TF card slot + GT30L24A1W font chip) ───────────────────────────────
# CS3=GPIO38, MISO3=GPIO42 (R19 10K pull-up). SCLK3=GPIO2 (R20 10K pull-up).
# Font chip CS# is NPN-inverted from CS3: CS3=HIGH → font chip selected.
SPI3_CS   = const(38)
SPI3_MISO = const(42)
SPI3_MOSI = const(1)
SPI3_SCLK = const(2)

# ── I2S / Audio ───────────────────────────────────────────────────────────────
# ES7243E microphone ADC (I2C ~0x15 depending on AD pin strapping).
# NS4168 mono speaker amplifier (I2S only, no I2C).
I2S_MCLK     = const(3)   # master clock output → ES7243E MCLK
I2S_BCLK     = const(40)  # bit clock (shared ES7243E + NS4168)
I2S_LRCK     = const(41)  # LR frame sync (shared)
I2S_SDO      = const(39)  # mic data IN  (ES7243E SDOUT → ESP32)
I2S_SDI      = const(45)  # speaker data OUT (ESP32 → NS4168 SDATA)
ES7243E_ADDR = const(0x10)  # base address; AD2 pull-up → likely 0x15 in practice

# ── GC2145 DVP Camera ─────────────────────────────────────────────────────────
# SCCB (I2C config) shares the GPIO47/48 bus.  Camera_RST is on XL9535 P0.1.
# Camera_PWDN is hardwired LOW in hardware (camera always powered).
CAM_VSYNC = const(4)
CAM_HREF  = const(5)
CAM_XCLK  = const(7)
CAM_PCLK  = const(17)
# Data bus D2-D9 (GC2145 uses D2..D9; listed LSB→MSB for Camera() data_pins arg)
CAM_D2    = const(8)
CAM_D3    = const(10)
CAM_D4    = const(11)
CAM_D5    = const(9)
CAM_D6    = const(18)
CAM_D7    = const(16)
CAM_D8    = const(15)
CAM_D9    = const(6)
GC2145_ADDR = const(0x3C)  # SCCB 7-bit address


def _camera_reset():
    # Pulse Camera_RST LOW via XL9535 P0.1 (active-low reset for GC2145)
    if _i2c is None:
        return
    try:
        _out = _i2c.readfrom_mem(XL9535_ADDR, XL9535_OUT0, 1)[0]
        _i2c.writeto_mem(XL9535_ADDR, XL9535_OUT0, bytes([_out & ~CAM_RST_BIT]))
        time.sleep_ms(10)
        _i2c.writeto_mem(XL9535_ADDR, XL9535_OUT0, bytes([_out | CAM_RST_BIT]))
        time.sleep_ms(10)
    except Exception as e:
        logger.error("unihiker_k10: camera_reset failed: %s", e)


def _restore_expander_i2c():
    # Camera SCCB shares GPIO47/48 and leaves the keypad expander bus unusable.
    global _i2c
    try:
        _i2c = create_expander_i2c(I2C, Pin, I2C_SDA, I2C_SCL)
    except Exception as e:
        _i2c = None
        logger.error("unihiker_k10: XL9535 restore failed: %s", e)


from mpos import CameraManager


def init_cam(width, height, colormode):
    from camera import Camera, GrabMode, PixelFormat
    _restore_expander_i2c()
    _camera_reset()
    frame_size = CameraManager.resolution_to_framesize(width, height)

    def create_camera():
        return Camera(
            data_pins=[CAM_D2, CAM_D3, CAM_D4, CAM_D5,
                       CAM_D6, CAM_D7, CAM_D8, CAM_D9],
            vsync_pin=CAM_VSYNC,
            href_pin=CAM_HREF,
            sda_pin=I2C_SDA,
            scl_pin=I2C_SCL,
            pclk_pin=CAM_PCLK,
            xclk_pin=CAM_XCLK,
            xclk_freq=20_000_000,
            powerdown_pin=-1,
            reset_pin=-1,
            pixel_format=PixelFormat.RGB565 if colormode else PixelFormat.GRAYSCALE,
            frame_size=frame_size,
            grab_mode=GrabMode.LATEST,
            fb_count=1,
        )

    def log_init_failure(attempt, error):
        if attempt < 2:
            logger.error("unihiker_k10: init_cam attempt %d failed: %s", attempt, error)
        else:
            logger.error("unihiker_k10: init_cam failed after 3 attempts: %s", error)

    return initialize_camera_with_recovery(
        create_camera,
        log_init_failure,
        _restore_expander_i2c,
    )


def deinit_cam(cam):
    try:
        cam.deinit()
    except Exception as e:
        logger.error("unihiker_k10: deinit_cam: %s", e)
    # SCCB leaves GPIO47/48 in an indeterminate state; brief pause lets I2C settle
    time.sleep_ms(20)
    _restore_expander_i2c()
    _camera_reset()


def capture_cam(cam, colormode):
    return cam.capture()


def apply_cam_settings(cam, prefs):
    # GC2145 settings support; use generic OV helper as fallback
    try:
        result = CameraManager.ov_apply_camera_settings(cam, prefs)
    except Exception:
        result = None
    _restore_expander_i2c()
    return result


CameraManager.add_camera(CameraManager.Camera(
    lens_facing=CameraManager.CameraCharacteristics.LENS_FACING_FRONT,
    name="GC2145",
    vendor="Galaxycore",
    init=init_cam,
    deinit=deinit_cam,
    capture=capture_cam,
    apply_settings=apply_cam_settings,
    # GC2145 frames are byte-swapped; the physical camera orientation needs vflip.
    rgb565_byte_swap=True,
    default_vflip=True,
))

# ── On-board sensors (SC7A20H · LTR303ALS · AHT20) + RGB LEDs ────────────────
# Shares I2C(0) on GPIO47/48 with XL9535. The LVGL keypad poller reads XL9535
# every ~20ms; always bracket sensor access with task_handler.disable/enable.

SENSOR_I2C_FREQ = const(400_000)

# SC7A20H triaxial accelerometer (0x19)
SC7A20H_ADDR      = const(0x19)
SC7A20H_WHO_AM_I  = const(0x0F)
SC7A20H_CTRL1     = const(0x20)
SC7A20H_CTRL4     = const(0x23)
SC7A20H_STATUS    = const(0x27)
SC7A20H_OUT_XL    = const(0x28)
SC7A20H_CTRL1_VAL = const(0x57)   # 100 Hz ODR, all axes
SC7A20H_CTRL4_VAL = const(0x88)   # BDU=1, HR=1, FS=00 (2 G)
SC7A20H_AUTO_INC  = const(0x80)

# LTR303ALS ambient light sensor (0x29)
LTR303_ADDR         = const(0x29)
LTR303_CONTR        = const(0x80)
LTR303_PART_ID      = const(0x86)
LTR303_MANUF_ID     = const(0x87)
LTR303_CH1_0        = const(0x88)
LTR303_CH1_1        = const(0x89)
LTR303_CH0_0        = const(0x8A)
LTR303_CH0_1        = const(0x8B)
LTR303_CONTR_ACTIVE = const(0x01)   # active mode, gain=1×

# AHT20 temperature + humidity (0x38)
AHT20_ADDR     = const(0x38)
AHT20_CMD_INIT = b'\xBE\x08\x00'
AHT20_CMD_TRIG = b'\xAC\x33\x00'
AHT20_CAL_BIT  = const(0x08)
AHT20_BUSY_BIT = const(0x80)

# RGB LEDs: 3× WS2812 NeoPixel on GPIO46
RGB_PIN   = const(46)
RGB_COUNT = const(3)

_accel_ok = False


def get_sensor_i2c():
    return I2C(0, scl=Pin(I2C_SCL), sda=Pin(I2C_SDA), freq=SENSOR_I2C_FREQ)


def get_rgb():
    return neopixel.NeoPixel(Pin(RGB_PIN), RGB_COUNT)


def init_sensors(i2c):
    # SC7A20H needs ~70 ms (7/ODR at 100 Hz) before first read_accel().
    # LTR303ALS needs ~100 ms (one integration period) before first read_light().
    _init_sc7a20h(i2c)
    _init_ltr303(i2c)
    _init_aht20(i2c)


def read_accel(i2c):
    # Returns (x_mg, y_mg, z_mg). 12-bit HR mode, 1 mg/LSB at 2 G.
    if not _accel_ok:
        return (0, 0, 0)
    try:
        deadline = time.ticks_add(time.ticks_ms(), 20)
        while True:
            if i2c.readfrom_mem(SC7A20H_ADDR, SC7A20H_STATUS, 1)[0] & 0x08:
                break
            if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
                logger.error("unihiker_k10: SC7A20H ZYXDA timeout")
                return (0, 0, 0)
            time.sleep_ms(1)
        raw = i2c.readfrom_mem(SC7A20H_ADDR, SC7A20H_OUT_XL | SC7A20H_AUTO_INC, 6)
        x = _s16(raw[0], raw[1]) >> 4
        y = _s16(raw[2], raw[3]) >> 4
        z = _s16(raw[4], raw[5]) >> 4
        return (x, y, z)
    except Exception as e:
        logger.error("unihiker_k10: read_accel failed: %s", e)
        return (0, 0, 0)


def read_light(i2c):
    # Returns (ch0_ir, ch1_vis) raw counts. Requires ≥100 ms after init_sensors().
    try:
        ch1_lo = i2c.readfrom_mem(LTR303_ADDR, LTR303_CH1_0, 1)[0]
        ch1_hi = i2c.readfrom_mem(LTR303_ADDR, LTR303_CH1_1, 1)[0]
        ch0_lo = i2c.readfrom_mem(LTR303_ADDR, LTR303_CH0_0, 1)[0]
        ch0_hi = i2c.readfrom_mem(LTR303_ADDR, LTR303_CH0_1, 1)[0]
        return ((ch0_hi << 8) | ch0_lo, (ch1_hi << 8) | ch1_lo)
    except Exception as e:
        logger.error("unihiker_k10: read_light failed: %s", e)
        return (0, 0)


def read_env(i2c):
    # Returns (temp_c, humidity_pct). Triggers a fresh measurement each call.
    try:
        i2c.writeto(AHT20_ADDR, AHT20_CMD_TRIG)
        deadline = time.ticks_add(time.ticks_ms(), 100)
        while True:
            time.sleep_ms(10)
            if not (i2c.readfrom(AHT20_ADDR, 1)[0] & AHT20_BUSY_BIT):
                break
            if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
                logger.error("unihiker_k10: AHT20 measurement timeout")
                return (0.0, 0.0)
        d = i2c.readfrom(AHT20_ADDR, 7)
        hum_raw  = (d[1] << 12) | (d[2] << 4) | (d[3] >> 4)
        temp_raw = ((d[3] & 0x0F) << 16) | (d[4] << 8) | d[5]
        return (temp_raw * 200 / 1048576 - 50, hum_raw * 100 / 1048576)
    except Exception as e:
        logger.error("unihiker_k10: read_env failed: %s", e)
        return (0.0, 0.0)


def _init_sc7a20h(i2c):
    global _accel_ok
    if __debug__: logger.debug("unihiker_k10: init SC7A20H")
    try:
        who = i2c.readfrom_mem(SC7A20H_ADDR, SC7A20H_WHO_AM_I, 1)[0]
        if who != 0x11:
            logger.error("unihiker_k10: SC7A20H WHO_AM_I=0x%02X (expected 0x11)", who)
            return
        i2c.writeto_mem(SC7A20H_ADDR, SC7A20H_CTRL4, bytes([SC7A20H_CTRL4_VAL]))
        i2c.writeto_mem(SC7A20H_ADDR, SC7A20H_CTRL1, bytes([SC7A20H_CTRL1_VAL]))
        time.sleep_ms(100)   # 7/ODR turn-on time at 100 Hz
        _accel_ok = True
        if __debug__: logger.debug("unihiker_k10: SC7A20H OK")
    except Exception as e:
        logger.error("unihiker_k10: SC7A20H init failed: %s", e)


def _init_ltr303(i2c):
    if __debug__: logger.debug("unihiker_k10: init LTR303ALS")
    try:
        part  = i2c.readfrom_mem(LTR303_ADDR, LTR303_PART_ID,  1)[0]
        manuf = i2c.readfrom_mem(LTR303_ADDR, LTR303_MANUF_ID, 1)[0]
        if part != 0xA0 or manuf != 0x05:
            logger.error("unihiker_k10: LTR303 ID mismatch PART=0x%02X MANUF=0x%02X", part, manuf)
            return
        i2c.writeto_mem(LTR303_ADDR, LTR303_CONTR, bytes([LTR303_CONTR_ACTIVE]))
        if __debug__: logger.debug("unihiker_k10: LTR303ALS OK")
    except Exception as e:
        logger.error("unihiker_k10: LTR303ALS init failed: %s", e)


def _init_aht20(i2c):
    if __debug__: logger.debug("unihiker_k10: init AHT20")
    try:
        status = i2c.readfrom(AHT20_ADDR, 1)[0]
        if not (status & AHT20_CAL_BIT):
            i2c.writeto(AHT20_ADDR, AHT20_CMD_INIT)
            time.sleep_ms(10)
            status = i2c.readfrom(AHT20_ADDR, 1)[0]
            if not (status & AHT20_CAL_BIT):
                logger.error("unihiker_k10: AHT20 calibration failed, status=0x%02X", status)
                return
        if __debug__: logger.debug("unihiker_k10: AHT20 OK")
    except Exception as e:
        logger.error("unihiker_k10: AHT20 init failed: %s", e)


def _s16(lo, hi):
    v = (hi << 8) | lo
    return v - 0x10000 if v >= 0x8000 else v


if __debug__: logger.debug("unihiker_k10.py finished")
