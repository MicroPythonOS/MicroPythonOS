print("lilygo_t_watch_s3_plus.py initialization")
# Manufacturer's website at https://lilygo.cc/products/t-watch-s3-plus
from machine import I2C, Pin, SPI

try:
    # Doesn't work with the new split Bus/Device Hardware SPI driver and drivers.lora.sx1262 yet
    # so use the original drivers.lora.micropySX126X.sx1262 that's patched to fallback to Software SPI
    #lora_spi_bus = SPI.Bus(host=1,mosi=1,miso=4,sck=3)
    #lora_spi_device = SPI.Device(spi_bus=lora_spi_bus, freq=500000, cs=-1, polarity=0, phase=0, firstbit=SPI.Device.MSB, bits=8)
    pass
except Exception as e:
    import sys
    sys.print_exception(e)
else:
    from drivers.lora.micropySX126X.sx1262 import SX1262
    sx = SX1262(spi_bus=1, clk=3, mosi=1, miso=4, cs=5, irq=9, rst=8, gpio=7)
    import mpos
    mpos.sx = sx

spi_bus = SPI.Bus(host=2,mosi=13,sck=18)

import lcd_bus
display_bus = lcd_bus.SPIBus(
    spi_bus=spi_bus,
    freq=40000000,
    dc=38,
    cs=12,
)

_BUFFER_SIZE = const(28800)
fb1 = display_bus.allocate_framebuffer(_BUFFER_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)
fb2 = display_bus.allocate_framebuffer(_BUFFER_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)

import drivers.display.st7789 as st7789
import mpos.ui
import lvgl as lv
mpos.ui.main_display = st7789.ST7789(
    data_bus=display_bus,
    frame_buffer1=fb1,
    frame_buffer2=fb2,
    display_width=240,
    display_height=240,
    color_space=lv.COLOR_FORMAT.RGB565,
    color_byte_order=st7789.BYTE_ORDER_BGR,
    rgb565_byte_swap=True,
    backlight_pin=45,
    backlight_on_state=st7789.STATE_PWM,
    offset_y=80
) # triggers lv.init()
mpos.ui.main_display.init()
mpos.ui.main_display.set_power(True)
mpos.ui.main_display.set_backlight(100)

import i2c
import drivers.indev.ft6x36 as ft6x36
i2c_bus = i2c.I2C.Bus(host=0, sda=39, scl=40, freq=400000, use_locks=False)
touch_dev = i2c.I2C.Device(bus=i2c_bus, dev_id=ft6x36.I2C_ADDR, reg_bits=ft6x36.BITS)
import pointer_framework
indev = ft6x36.FT6x36(touch_dev, startup_rotation=pointer_framework.lv.DISPLAY_ROTATION._180)
from mpos import InputManager
InputManager.register_indev(indev)

mpos.ui.main_display.set_rotation(lv.DISPLAY_ROTATION._180)

# Audio:
from mpos import AudioManager
i2s_output_pins = {
    'ws': 15,       # Word Select / LRCLK shared between DAC and mic (mandatory)
    'sck': 48,      # SCLK or BCLK - Bit Clock for DAC output (mandatory)
    'sd': 46,       # Serial Data OUT (speaker/DAC)
}
speaker_output = AudioManager.add(
    AudioManager.Output(
        name="speaker",
        kind="i2s",
        i2s_pins=i2s_output_pins,
    )
)

i2s_input_pins = {
    'ws': 15,       # Word Select / LRCLK shared between DAC and mic (mandatory)
    'sck_in': 44,   # SCLK - Serial Clock for microphone input
    'sd_in': 47,    # DIN - Serial Data IN (microphone)
}
mic_input = AudioManager.add(
    AudioManager.Input(
        name="mic",
        kind="i2s",
        i2s_pins=i2s_input_pins,
    )
)

# Vibrator test

# One strong & fairly long buzz (repeat as needed)
i2c = I2C(1, sda=Pin(10), scl=Pin(11), freq=400000)

def write_reg(reg, val):
    i2c.writeto_mem(0x5A, reg, bytes([val]))

write_reg(0x01, 0x00)                # internal trigger
write_reg(0x03, 0)                   # Library A
write_reg(0x04, 47)                  # Strong Buzz 100%
write_reg(0x0C, 1)                   # GO
import time
time.sleep(1)                        # ~0.8s strong buzz
write_reg(0x0C, 0)                   # stop (optional)

# IMU:
import drivers.imu_sensor.bma423.bma423 as bma423
sensor = bma423.BMA423(i2c, address=0x19)
time.sleep_ms(500) # some sleep is needed before reading values
print("temperature: ", sensor.get_temperature())
print("steps: ", sensor.get_steps())
print("(x,y,z): ", sensor.get_xyz())

# TODO:
# - battery
# - real IMU driver (instead of proof-of-concept above)
# - GPS
# - LoRa

print("lilygo_t_watch_s3_plus.py finished")
