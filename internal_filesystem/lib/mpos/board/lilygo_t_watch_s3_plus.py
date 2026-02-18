print("lilygo_t_watch_s3_plus.py initialization")
# Manufacturer's website at https://lilygo.cc/products/t-watch-s3-plus
import lcd_bus
import machine
import i2c

import lvgl as lv
import task_handler

import drivers.display.st7789 as st7789

import mpos.ui

spi_bus = machine.SPI.Bus(
    host=2,
    mosi=13,
    sck=18
)
display_bus = lcd_bus.SPIBus(
    spi_bus=spi_bus,
    freq=40000000,
    dc=38,
    cs=12,
)

_BUFFER_SIZE = const(28800)
fb1 = display_bus.allocate_framebuffer(_BUFFER_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)
fb2 = display_bus.allocate_framebuffer(_BUFFER_SIZE, lcd_bus.MEMORY_INTERNAL | lcd_bus.MEMORY_DMA)

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
)
mpos.ui.main_display.init()
mpos.ui.main_display.set_power(True)
mpos.ui.main_display.set_backlight(100)

# TODO:
# Touch handling:
#import drivers.indev.cst816s as cst816s
#i2c_bus = i2c.I2C.Bus(host=0, scl=40, sda=39, freq=400000, use_locks=False)
#touch_dev = i2c.I2C.Device(bus=i2c_bus, dev_id=0x15, reg_bits=8)
#indev=cst816s.CST816S(touch_dev)

lv.init()

# TODO:
# - battery
# - IMU

print("lilygo_t_watch_s3_plus.py finished")
