import logging

logger = logging.getLogger(__name__)

if __debug__: logger.debug("squixl.py initialization")
"""
Hardware initialization for the SQUiXL device by "Unexpected Maker"
https://squixl.io

https://github.com/UnexpectedMaker/SQUiXL-DevOS
https://github.com/UnexpectedMaker/SQUiXL-DevOS/blob/main/platformio/src/squixl.h

https://github.com/UnexpectedMaker/SQUiXL
https://github.com/UnexpectedMaker/SQUiXL/blob/main/examples/micropython/lib/squixl.py
https://github.com/UnexpectedMaker/SQUiXL/blob/main/esphome/readme.md

* ESP32-S3 - 32Bit Dual Core 240MHz
* ST7701S - 4 Inch 480x480 RGB Display
* GT911 - Capacitive Touch controller
* LCA9555 IO expander (register-compatible with the TCA9555)
* TMUX1574RSVR - IO MUX
* MAX98357A - I2S Audio Amplifier (8 Ohm, 2W Speaker)
* DRV2605L - Haptic feedback motor
* RV-3028-C7 - I2C Low Power RTC
* MAX1704X - I2C Battery Fuel Gauge

Before you can install MicroPython, you need to erase the Flash on your SQUiXL.

Power it up and put it into download mode by following these steps:

    Press and hold the [BOOT] button
    Press and release the [RESET] button
    Release the [BOOT] button

Now the board is in download mode and the native USB will have enumerated as a serial device.

The SQUiXL display uses an ST7701S controller with a standard ESP32-S3 RGB parallel bus for pixel
data. However, the display's SPI init lines (CS, CLK, MOSI, Reset) are wired through an LCA9555
IO expander over I2C instead of native GPIO.

This component handles that by bit-banging the SPI init sequence through the IO expander during
startup, then handing off to the RGB display driver for all pixel operations.

The GT911 capacitive touch controller's reset pin is also on the IO expander (pin 5).
This component handles the GT911 reset with the correct INT pin state for I2C address selection.

The LCA9555 is register-compatible with the TCA9555.


Original author: https://github.com/jedie
"""

"""
| ESP32-S3 | GENERAl IO    |
| -------- | ------------- |
| IO0      | BOOT          |
| IO1      | I2C SDA       |
| IO2      | I2C SCL       |
| IO3      | Touch IC INT  |
| IO40     | Backlight PWM |
| IO41     | IOMUX 1       |
| IO42     | IOMUX 2       |
| IO43     | FG Interrupt  |
| IO44     | RTC Interrupt |
| IO45     | IOMUX 3       |
| IO46     | IOMUX 4       |


| IO Expander |           |
| ----------- | --------- |
| IO0  | Backlight Enable |
| I01  | LCD Reset        |
| IO2  | LCD Data         |
| IO3  | LCD SCK          |
| IO4  | LCD CS           |
| IO5  | Touch IC Reset   |
| IO7  | uSD Card Detect  |
| IO8  | IOMUX SEL        |
| IO9  | IOMUX Enable     |
| IO10 | Haptics Enable   |
| IO11 | VBUS Sense       |

| IOMUX | FUNC 1  | FUNC 2    |
| ----- | ------- | --------  |
| IO1   | SD MISO | I2S SD    |
| IO2   | SD CS   | I2S LRCLK |
| IO3   | SD CLK  | I2S DATA  |
| IO4   | SD MOSI | I2S BCLK  |

| RGB Peripheral |       |
| -------------- | ----- |
| ESP32-S3       | FUNC  |
| IO4            | R5    |
| IO5            | R4    |
| IO6            | R3    |
| IO7            | R2    |
| IO8            | R1    |
| IO9            | G5    |
| IO10           | G4    |
| IO11           | G3    |
| IO12           | G2    |
| IO13           | G1    |
| IO14           | G0    |
| IO15           | B5    |
| IO16           | B4    |
| IO17           | B3    |
| IO18           | B2    |
| IO21           | B1    |
| IO38           | DE    |
| IO39           | PCLK  |
| IO47           | VSYNC |
| IO48           | HSYNC |
"""

import os
import sys
import time

import drivers.haptic.drv2605 as drv2605
import drivers.indev.gt911 as gt911
import drivers.power.max17048 as max17048
import drivers.rtc.rv3028 as rv3028
import i2c
import lcd_bus
import lvgl as lv
import machine
import mpos.sdcard
import mpos.ui
from drivers.display.st7701s import ST7701S
from drivers.display.st7701s.expander_spi3wire import ExpanderSpi3Wire
from drivers.io_expander.tca9555 import TCA9555, TCA9555Pin
from micropython import const
from mpos import (
    AudioManager,
    BatteryManager,
    InputManager,
    SensorManager,
    SharedPreferences,
    TimeZone,
)

I2C_HOST = const(0)
I2C_SDA = const(1)
I2C_SCL = const(2)
I2C_FREQ_HZ = const(400_000)
I2S_SCK_PIN = const(46)
I2S_WS_PIN = const(42)
I2S_SD_PIN = const(45)

TOUCH_INTERRUPT_PIN = const(3)  # GT911 interrupt (native GPIO)

LCD_BUS_DE = const(38)
LCD_BUS_PCLK = const(39)
LCD_BUS_VSYNC = const(47)
LCD_BUS_HSYNC = const(48)
LCD_BUS_FREQ_HZ = const(6_500_000)
LCD_WIDTH = const(480)
LCD_HEIGHT = const(480)

BACKLIGHT_PWM_PIN = const(40)  # backlight PWM (active-low: 0 duty = full bright)
BACKLIGHT_PWM_FREQ_HZ = const(20_000)
BACKLIGHT_PWM_DUTY_MAX = const(65535)
BACKLIGHT_MIN_PERCENT = const(0)
BACKLIGHT_MAX_PERCENT = const(100)
BACKLIGHT_FULL_BRIGHT_DUTY = const(0)

RGB_PCLK_FREQ_HZ = const(6500000)
HSYNC_BACK_PORCH = const(2)
HSYNC_FRONT_PORCH = const(2)
HSYNC_PULSE_WIDTH = const(1)
VSYNC_BACK_PORCH = const(8)
VSYNC_FRONT_PORCH = const(20)
VSYNC_PULSE_WIDTH = const(2)

SD_SPI_HOST = const(2)
SD_SCK_PIN = const(45)
SD_MOSI_PIN = const(46)
SD_MISO_PIN = const(41)
SD_CS_PIN = const(42)

# TCA9555 expander
TCA9555_ADDR = const(0x20)
TCA_EXP = const(0x40)  # 0x40 marker -> routed to the expander
TCA_BL_EN = const(TCA_EXP | 0)
TCA_LCD_RST = const(TCA_EXP | 1)
TCA_LCD_MOSI = const(TCA_EXP | 2)
TCA_LCD_CLK = const(TCA_EXP | 3)
TCA_LCD_CS = const(TCA_EXP | 4)
TCA_TOUCH_RESET_PIN = const(TCA_EXP | 5)

TCA_SD_DETECT = const(TCA_EXP | 7)  # uSD card-detect (board pin table: IO7)
TCA_MUX_SEL = const(TCA_EXP | 8)  # IOMUX select: HIGH=I2S, LOW=SD
TCA_MUX_EN = const(TCA_EXP | 9)  # IOMUX enable (active-low)
TCA_HAPTICS_EN = const(TCA_EXP | 10)  # haptic motor supply enable
TCA_VBUS_SENSE = const(TCA_EXP | 11)  # USB VBUS present (input)

# native GPIO
FG_INT = const(43)  # MAX17048 alert (active-low)
RTC_INT = const(44)  # RV-3028 interrupt (active-low)
BOOT_BTN = const(0)  # BOOT strapping pin, usable as a runtime input

# TMUX1574 IO-MUX: SD and I2S share GPIO41/42/45/46 (mutually exclusive)
IOMUX_OFF = const(0)
IOMUX_SD = const(1)
IOMUX_I2S = const(2)

AMP_SD = const(41)  # MAX98357A SD_MODE (mux D1): drive HIGH to un-mute the amp


# RGB data GPIOs in LVGL RGB565 bit order: data0=B-LSB .. data15=R-MSB
# i.e. B0..B4, G0..G5, R0..R4 by GPIO. This is not DevOS's UM_GFX data_gpio
# scramble, which matches UM_GFX's own framebuffer packing, not LVGL's standard RGB565.
RGB_DATA = (21, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4)

# 1) I2C bus (shared: expander @0x20, GT911, RTC, fuel-gauge)
try:
    i2c_bus = i2c.I2C.Bus(
        host=I2C_HOST,
        scl=I2C_SCL,
        sda=I2C_SDA,
        freq=I2C_FREQ_HZ,
        use_locks=False,
    )
except Exception as e:
    logger.error("squixl.py I2C bus init failed:")
    sys.print_exception(e)
    if __debug__: logger.debug("Attempting hard reset in 3sec...")
    time.sleep(3)
    machine.reset()

tca = TCA9555(i2c_bus, dev_id=TCA9555_ADDR)

# 2) LCD hardware reset (expander) + backlight enable (expander) + PWM (GPIO40, active-low)
tca.digital_write(TCA_LCD_RST, 0)
time.sleep_ms(20)
tca.digital_write(TCA_LCD_RST, 1)
time.sleep_ms(120)
tca.digital_write(TCA_BL_EN, 1)

# 3) 3-wire SPI init channel over the expander
spi_3wire = ExpanderSpi3Wire(
    tca, cs_pin=TCA_LCD_CS, clk_pin=TCA_LCD_CLK, mosi_pin=TCA_LCD_MOSI
)


# 4) RGB pixel bus, all 16 data pins in RGB565 bit order, DevOS timings, 6.5 MHz pclk
display_bus = lcd_bus.RGBBus(
    hsync=LCD_BUS_HSYNC,
    vsync=LCD_BUS_VSYNC,
    de=LCD_BUS_DE,
    pclk=LCD_BUS_PCLK,
    data0=RGB_DATA[0],
    data1=RGB_DATA[1],
    data2=RGB_DATA[2],
    data3=RGB_DATA[3],
    data4=RGB_DATA[4],
    data5=RGB_DATA[5],
    data6=RGB_DATA[6],
    data7=RGB_DATA[7],
    data8=RGB_DATA[8],
    data9=RGB_DATA[9],
    data10=RGB_DATA[10],
    data11=RGB_DATA[11],
    data12=RGB_DATA[12],
    data13=RGB_DATA[13],
    data14=RGB_DATA[14],
    data15=RGB_DATA[15],
    freq=LCD_BUS_FREQ_HZ,
    hsync_back_porch=const(2),
    hsync_front_porch=const(2),
    hsync_pulse_width=const(1),
    vsync_back_porch=const(8),
    vsync_front_porch=const(20),
    vsync_pulse_width=const(2),
    hsync_idle_low=False,
    vsync_idle_low=False,
    de_idle_high=False,
    pclk_active_low=True,
)

# Two FULL-size framebuffers in PSRAM -> FULL double-buffered render mode so LVGL
# draws to a back buffer and swaps on vsync (tear-free). Without this the framework
# auto-allocates a 1/10-screen PARTIAL buffer, which tears on full-screen animations.
_FB_SIZE = const(LCD_WIDTH * LCD_HEIGHT * 2)  # 2 Bytes per RGB565 pixel
frame_buffer1 = display_bus.allocate_framebuffer(
    _FB_SIZE, lcd_bus.MEMORY_SPIRAM | lcd_bus.MEMORY_DMA
)
frame_buffer2 = display_bus.allocate_framebuffer(
    _FB_SIZE, lcd_bus.MEMORY_SPIRAM | lcd_bus.MEMORY_DMA
)

# 5) Driver: register-init (via spi_3wire) runs BEFORE the RGB bus (_init_bus=False)
mpos.ui.main_display = ST7701S(
    data_bus=display_bus,
    spi_3wire=spi_3wire,
    frame_buffer1=frame_buffer1,
    frame_buffer2=frame_buffer2,
    display_width=LCD_WIDTH,
    display_height=LCD_HEIGHT,
    color_space=lv.COLOR_FORMAT.RGB565,  # 16 data lines map to RGB565. Panel-specific, adjust if the image looks wrong
    color_byte_order=ST7701S.BYTE_ORDER_RGB,
    rgb565_byte_swap=False,  # panel-specific, set True if R and B are swapped
    bus_shared_pins=False,  # 3-wire lines are on the expander, independent
)  # triggers lv.init()
mpos.ui.main_display.init()  # spi_3wire.init -> _spi_3wire_init -> _init_bus

# full brightness at boot
backlight_pwm = machine.PWM(  # 0 duty = full bright (active-low)
    machine.Pin(BACKLIGHT_PWM_PIN),
    freq=BACKLIGHT_PWM_FREQ_HZ,
    duty_u16=BACKLIGHT_FULL_BRIGHT_DUTY,
)
mpos.ui.main_display.set_backlight(100)

# This panel needs color inversion ON: without it every color renders as its
# complement. The init seq sends INVON then a trailing INVOFF, so re-enable it here.
mpos.ui.main_display.set_color_inversion(True)

# 6) GT911 touch (reset on expander, interrupt on native GPIO3)
try:
    touch_dev = i2c.I2C.Device(bus=i2c_bus, dev_id=gt911.I2C_ADDR, reg_bits=gt911.BITS)
    indev = gt911.GT911(
        touch_dev,
        reset_pin=TCA9555Pin(
            tca, TCA_TOUCH_RESET_PIN
        ),  # duck-typed expander pin (callable)
        interrupt_pin=TOUCH_INTERRUPT_PIN,  # native GPIO int (required by driver)
        startup_rotation=lv.DISPLAY_ROTATION._0,
    )
    InputManager.register_indev(indev)
except Exception as e:
    logger.error("squixl.py touch init failed:")
    sys.print_exception(e)
    if __debug__: logger.debug("Attempting hard reset in 3sec...")
    time.sleep(3)
    machine.reset()

# 7) rotation AFTER init + touch creation
mpos.ui.main_display.set_rotation(lv.DISPLAY_ROTATION._0)

# Onboard peripherals: haptic, battery gauge, RTC, VBUS, BOOT button.
#
# Every I2C chip shares `i2c_bus` (the i2c.I2C.Bus created above for the expander
# and touch). i2c.I2C.Bus wraps machine.I2C and exposes readfrom_mem/writeto_mem,
# which is all these drivers need. Do NOT open a second machine.I2C on controller 0:
# it re-installs the IDF driver and kills the live expander/touch/backlight.


# haptic (DRV2605L @ 0x5A)
tca.digital_write(TCA_HAPTICS_EN, 1)  # power the haptic motor (expander P10)
time.sleep_ms(10)
try:
    haptic = drv2605.DRV2605(i2c_bus)  # i2c.I2C.Bus -> machine.I2C-style mem API
    haptic.sequence[0] = drv2605.Effect(1)  # 1 = strong click (default)

    def vibrate(effect=1):
        haptic.sequence[0] = drv2605.Effect(effect)
        haptic.play()
except Exception as e:
    logger.error("squixl: haptic init failed:", e)
    haptic = None

    def vibrate(effect=1):
        pass


# battery (MAX17048 @ 0x36) -> BatteryManager
try:
    gauge = max17048.MAX17048(i2c_bus)
    # BatteryManager methods are @staticmethod (called with no self) -> variadic lambdas
    BatteryManager.has_battery = lambda *a, **k: True
    BatteryManager.get_battery_percentage = lambda *a, **k: gauge.state_of_charge
    BatteryManager.read_battery_voltage = lambda *a, **k: gauge.cell_voltage
    BatteryManager.read_raw_adc = lambda *a, **k: 0
    BatteryManager.gauge = gauge
except Exception as e:
    logger.error("squixl: fuel gauge init failed:", e)
    gauge = None

# FG_INT (GPIO43) empty-battery alert
if gauge:
    try:
        gauge.set_empty_alert_threshold(10)  # alert at <=10% SOC
        gauge.clear_alert()
        _fg_int = machine.Pin(FG_INT, machine.Pin.IN, machine.Pin.PULL_UP)

        def _fg_alert(pin):  # Pin.irq is soft-scheduled -> I2C ok here
            try:
                pct = gauge.state_of_charge
                if __debug__: logger.debug("squixl: battery alert, SOC=%.0f%%" % pct)
                gauge.clear_alert()
                if pct <= 10 and haptic:
                    vibrate(1)
            except Exception as e:
                if __debug__: logger.debug("squixl: fg alert handler:", e)

        _fg_int.irq(trigger=machine.Pin.IRQ_FALLING, handler=_fg_alert)
    except Exception as e:
        logger.error("squixl: FG_INT setup failed:", e)

# RTC (RV-3028 @ 0x52) -> machine.RTC + TimeZone.rtc
try:
    rtc = rv3028.RV3028(i2c_bus)
    rtc.enable_backup()

    # machine.RTC().datetime() requires an 8-tuple (append subsec=0)
    dt = rtc.datetime()
    year, month, day, weekday, hour, minute, second = dt
    machine.RTC().datetime((year, month, day, weekday, hour, minute, second, 0))

    TimeZone.rtc = rtc  # OS NTP sync writes back via rtc.datetime()
except Exception as e:
    logger.error("squixl: RTC init failed:", e)
    rtc = None

# RTC_INT (GPIO44) daily alarm
_rtc_alarm_cb = None


def set_rtc_alarm(hour, minute, callback):
    global _rtc_alarm_cb
    if not rtc:
        return
    _rtc_alarm_cb = callback
    rtc.set_daily_alarm(hour, minute)
    rtc.enable_alarm_interrupt(True)


if rtc:
    try:
        _rtc_int = machine.Pin(RTC_INT, machine.Pin.IN, machine.Pin.PULL_UP)

        def _rtc_irq(pin):
            try:
                if rtc.alarm_fired():
                    rtc.clear_alarm()
                    if _rtc_alarm_cb:
                        _rtc_alarm_cb()
            except Exception as e:
                if __debug__: logger.debug("squixl: rtc irq:", e)

        _rtc_int.irq(trigger=machine.Pin.IRQ_FALLING, handler=_rtc_irq)
    except Exception as e:
        logger.error("squixl: RTC_INT setup failed:", e)


# VBUS sense (expander P11)


def vbus_present():
    return tca.digital_read(TCA_VBUS_SENSE) == 1


# BOOT button (GPIO0) as a KEYPAD indev (press -> ESC/back navigation)
_boot_btn = machine.Pin(BOOT_BTN, machine.Pin.IN, machine.Pin.PULL_UP)  # active-low
_boot_last = False


def _boot_read_cb(indev, data):
    global _boot_last
    data.continue_reading = False
    pressed = _boot_btn.value() == 0
    if pressed:
        data.state = lv.INDEV_STATE.PRESSED
        data.key = lv.KEY.ESC
        if not _boot_last:  # on the press edge: trigger back-nav (ESC alone doesn't)
            try:
                mpos.ui.back_screen()
            except Exception as e:
                if __debug__: logger.debug("squixl: boot back_screen:", e)
    else:
        data.state = lv.INDEV_STATE.RELEASED
    _boot_last = pressed


try:
    _kp = lv.indev_create()
    _kp.set_type(lv.INDEV_TYPE.KEYPAD)
    _kp.set_read_cb(_boot_read_cb)
    _kp.set_group(lv.group_get_default())
    _kp.set_display(lv.display_get_default())
    _kp.enable(True)
    InputManager.register_indev(_kp)
except Exception as e:
    logger.error("squixl: BOOT keypad init failed:", e)

# TMUX1574 IO-MUX
_iomux_state = IOMUX_OFF


def set_iomux(state):
    global _iomux_state
    if state == _iomux_state:
        return
    if state == IOMUX_OFF:
        tca.digital_write(TCA_MUX_EN, 1)  # active-low: HIGH disables the mux
    elif state == IOMUX_SD:
        tca.digital_write(TCA_MUX_SEL, 0)  # LOW selects SD
        tca.digital_write(TCA_MUX_EN, 0)
    elif state == IOMUX_I2S:
        tca.digital_write(TCA_MUX_SEL, 1)  # HIGH selects I2S
        tca.digital_write(TCA_MUX_EN, 0)
    _iomux_state = state


# SD card (SPI on the mux SD-side: SCK45 MISO41 MOSI46, CS42)
_sd_spi = None


def card_present():
    try:
        return (
            tca.digital_read(TCA_SD_DETECT) == 0
        )  # active-low when a card is inserted
    except Exception:
        return False


def _sd_mount():
    try:
        os.mount(mpos.sdcard.get()._sdcard, "/sdcard")  # plain mount, never auto-format
    except Exception as e:
        if __debug__: logger.debug("squixl: sd mount:", e)


def sd_init():
    # Boot bring-up: mux to SD, create the SPI bus, register the card with mpos.sdcard
    # (which owns the manager singleton), and mount it.
    global _sd_spi
    set_iomux(IOMUX_SD)
    _sd_spi = machine.SPI.Bus(
        host=SD_SPI_HOST,
        sck=SD_SCK_PIN,
        mosi=SD_MOSI_PIN,
        miso=SD_MISO_PIN,
    )
    mpos.sdcard.init(spi_bus=_sd_spi, cs_pin=SD_CS_PIN)
    _sd_mount()


try:
    sd_init()  # resting state: SD owns the shared pins
except Exception as e:
    logger.error("squixl: sd_init failed:", e)

# audio (MAX98357A on I2S: sck46 ws42 sd45) + SD<->I2S mux arbiter
#
# SD and I2S share GPIO41/42/45/46 through the TMUX1574 and cannot be live at once, so audio
# borrows the pins via the AudioManager Output's on_open/on_close hooks:
#   on_open  (before machine.I2S() binds the pins): release SD -> mux to I2S -> un-mute amp
#   on_close (before I2S.deinit()):                  mute amp -> mux back to SD
#
# LIMITATION: SD is NOT auto-restored after audio. Once I2S has run, the SD card will not
# re-detect when the freed SPI host is re-initialized. This is an ESP32-S3 SPI/I2S GDMA
# interaction that is not fixable in board code. No-DMA breaks SD block reads, a GPIO pad
# reset does not help, and the host number is irrelevant. A fresh host init survives I2S but
# a re-init does not. So after playing audio, /sdcard stays unmounted until the next reboot.
# Workloads that need both SD and audio should treat them as mutually exclusive across a
# reboot. If a future MicroPython/IDF fix lets the SPI re-init survive I2S, restoring SD
# becomes a few lines in on_close: re-create the SPI.Bus + SDCard and remount.


def _audio_acquire():  # AudioManager Output.on_open
    try:
        os.umount("/sdcard")
    except Exception:
        pass
    try:
        mgr = mpos.sdcard.get()
        if mgr and mgr._sdcard:
            mgr._sdcard.deinit()  # frees the SPI bus + releases the shared pins
    except Exception as e:
        if __debug__: logger.debug("squixl: audio acquire:", e)
    set_iomux(IOMUX_I2S)  # before machine.I2S() binds 46/42/45
    machine.Pin(AMP_SD, machine.Pin.OUT).value(1)


def _audio_release():  # AudioManager Output.on_close (fires before I2S.deinit())
    try:
        machine.Pin(AMP_SD, machine.Pin.OUT).value(0)  # mute the amp
    except Exception:
        pass
    set_iomux(IOMUX_SD)  # restore the mux (SD stays unmounted, see above)


try:
    speaker_output = AudioManager.add(
        AudioManager.Output(
            name="speaker",
            kind="i2s",
            i2s_pins={"sck": I2S_SCK_PIN, "ws": I2S_WS_PIN, "sd": I2S_SD_PIN},
            on_open=_audio_acquire,
            on_close=_audio_release,
        )
    )
except Exception as e:
    logger.error("squixl: audio output init failed:", e)
    speaker_output = None

# SOC temperature (ESP32-S3 internal) -> top-bar temperature readout
# Without a registered temp sensor the top bar shows a hardcoded "42°C" placeholder. This
# registers the MCU/SOC sensor (esp32.mcu_temperature()). No IMU on this board, so pass None.


try:
    SensorManager.init(None)
except Exception as e:
    logger.error("squixl: sensor init failed:", e)


# opt-in haptic touch feedback (generic InputManager hook, reads the Settings pref live)
def _haptic_feedback_cb(event=None):
    try:
        if (
            haptic
            and SharedPreferences("com.micropythonos.settings").get_string(
                "haptic_feedback", "off"
            )
            == "on"
        ):
            vibrate(1)
    except Exception:
        pass


InputManager.set_touch_feedback_cb(_haptic_feedback_cb)

if __debug__: logger.debug("squixl.py finished")
