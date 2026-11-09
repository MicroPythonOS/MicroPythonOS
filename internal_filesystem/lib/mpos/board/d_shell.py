import logging
import time

from machine import I2C, Pin, SoftI2C
import machine
import lcd_bus
import lvgl as lv
import i2c
import drivers.display.st7789v as st7789
import drivers.indev.gt911 as gt911
import mpos.ui
from mpos import AudioManager, InputManager, LightsManager, SensorManager


logger = logging.getLogger(__name__)
WIDTH = 240
HEIGHT = 320
BUFFER_SIZE = WIDTH * HEIGHT * 2 // 4

spi_bus = machine.SPI.Bus(host=1, sck=39, mosi=38)
display_bus = lcd_bus.SPIBus(spi_bus=spi_bus, freq=40000000, dc=45, cs=48)
fb1 = display_bus.allocate_framebuffer(BUFFER_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)
fb2 = display_bus.allocate_framebuffer(BUFFER_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)
display = st7789.ST7789V(
    data_bus=display_bus,
    display_width=WIDTH,
    display_height=HEIGHT,
    frame_buffer1=fb1,
    frame_buffer2=fb2,
    reset_pin=40,
    reset_state=st7789.STATE_LOW,
    backlight_pin=47,
    backlight_on_state=st7789.STATE_PWM,
    color_space=lv.COLOR_FORMAT.RGB565,
    color_byte_order=st7789.BYTE_ORDER_BGR,
    rgb565_byte_swap=True,
)
mpos.ui.main_display = display
display.init()
display.set_power(True)
display.set_backlight(100)

touch_reset = Pin(1, Pin.OUT, value=0)
touch_interrupt = Pin(2, Pin.OUT, value=0)
time.sleep_ms(20)
touch_reset.value(1)
time.sleep_ms(50)
touch_interrupt.init(Pin.IN)
time.sleep_ms(100)
touch_bus = i2c.I2C.Bus(host=0, scl=41, sda=42, freq=100000, use_locks=False, timeout=20000)
touch_device = i2c.I2C.Device(bus=touch_bus, dev_id=0x5D, reg_bits=16)
touch = None
try:
    product_id = bytearray(4)
    touch_device.write_readinto(b"\x81\x40", product_id)
    if bytes(product_id) != b"911\x00":
        raise OSError("Unexpected GT911 identity")
    touch = gt911.GT911(device=touch_device, startup_rotation=lv.DISPLAY_ROTATION._0, debug=False)
    InputManager.register_indev(touch)
except OSError as error:
    logger.warning("D-Shell touch unavailable: %s", error)
display.set_rotation(lv.DISPLAY_ROTATION._0)

key_up = Pin(9, Pin.IN, Pin.PULL_UP)
key_down = Pin(3, Pin.IN, Pin.PULL_UP)
_key_candidate = None
_key_stable = None
_key_changed_ms = 0
_last_key = lv.KEY.NEXT


def _read_keys(indev, data):
    global _key_candidate, _key_stable, _key_changed_ms, _last_key
    up = key_up.value() == 0
    down = key_down.value() == 0
    value = lv.KEY.ENTER if up and down else lv.KEY.PREV if up else lv.KEY.NEXT if down else None
    now = time.ticks_ms()
    if value != _key_candidate:
        _key_candidate = value
        _key_changed_ms = now
    if time.ticks_diff(now, _key_changed_ms) >= 20:
        _key_stable = _key_candidate
    if _key_stable is not None:
        _last_key = _key_stable
    data.key = _last_key
    data.state = lv.INDEV_STATE.PRESSED if _key_stable is not None else lv.INDEV_STATE.RELEASED


keypad = lv.indev_create()
keypad.set_type(lv.INDEV_TYPE.KEYPAD)
keypad.set_read_cb(_read_keys)
keypad.set_group(lv.group_get_default())
keypad.set_display(lv.display_get_default())
InputManager.register_indev(keypad)

sensor_i2c = SoftI2C(scl=Pin(21), sda=Pin(14), freq=100000, timeout=20000)
imu_i2c = I2C(1, scl=Pin(7), sda=Pin(6), freq=100000, timeout=20000)
imu_address = 0x6A
try:
    if imu_i2c.readfrom_mem(imu_address, 0, 1) != b"\x05":
        raise OSError("Unexpected QMI8658 identity")
    SensorManager.init(imu_i2c, address=imu_address, mounted_position=SensorManager.FACING_SKY)
except OSError as error:
    logger.warning("D-Shell IMU unavailable: %s", error)

try:
    LightsManager.init(46)
    LightsManager.set_led_num(8)
except Exception as error:
    logger.warning("D-Shell LEDs unavailable: %s", error)

amp_enable = Pin(15, Pin.OUT, value=0)
amp_gain = Pin(8, Pin.IN)


def _speaker_open():
    amp_enable.value(1)


def _speaker_close():
    amp_enable.value(0)


speaker = AudioManager.add(AudioManager.Output(
    name="D-Shell MAX98357A",
    kind="i2s",
    i2s_pins={"sck": 17, "ws": 18, "sd": 16},
    on_open=_speaker_open,
    on_close=_speaker_close,
))
buzzer = AudioManager.add(AudioManager.Output(name="D-Shell Buzzer", kind="buzzer", buzzer_pin=5))
logger.info("D-Shell N16R8 display, touch, input and audio initialized")
