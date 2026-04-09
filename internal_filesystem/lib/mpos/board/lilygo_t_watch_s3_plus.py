# Manufacturer's website at https://lilygo.cc/products/t-watch-s3-plus

print("lilygo_t_watch_s3_plus.py initialization")

def init_pmu(m_i2c):
    print("Initializing AXP2101 PMU")
    from drivers.power.AXP2101 import AXP2101
    pmu = AXP2101(m_i2c, addr=0x34)
    # Set the minimum common working voltage of the PMU VBUS input, below this value will turn off the PMU
    pmu.setVbusVoltageLimit(AXP2101.XPOWERS_AXP2101_VBUS_VOL_LIM_4V36);
    # Set the maximum current of the PMU VBUS input, higher than this value will turn off the PMU
    pmu.setVbusCurrentLimit(AXP2101.XPOWERS_AXP2101_VBUS_CUR_LIM_900MA);
    # Set VSY off voltage as 2600mV , Adjustment range 2600mV ~ 3300mV
    pmu.setSysPowerDownVoltage(2600);
    # Display backlight
    pmu.setALDO2Voltage(3300)
    pmu.enableALDO2()
    # Display chip
    pmu.setALDO3Voltage(3300)
    pmu.enableALDO3()
    # LoRa radio (might be better to only power this on if LoRa is used)
    pmu.setALDO4Voltage(3300)
    pmu.enableALDO4()
    # Vibrator
    pmu.setBLDO2Voltage(3300)
    pmu.enableBLDO2()
    # GPS (not implemented yet)
    #pmu.setDC3Voltage(3300);    # Earlier versions use DC3 (without BOOT button and RST)
    #pmu.enableDC3();    # Earlier versions use DC3 (without BOOT button and RST)
    #pmu.setBLDO1Voltage(3300);  # The version with BOOT button and RST on the back cover
    #pmu.enableBLDO1();  # The version with BOOT button and RST on the back cover
    # RTC backup battery:
    pmu.setButtonBatteryChargeVoltage(3300)
    pmu.enableButtonBatteryCharge()
    # Speaker
    pmu.enableDLDO1()
    # Others
    pmu.setPowerKeyPressOffTime(AXP2101.XPOWERS_POWEROFF_4S)
    pmu.setPowerKeyPressOnTime(AXP2101.XPOWERS_POWERON_512MS)
    pmu.enableBattDetection()
    pmu.enableVbusVoltageMeasure()
    pmu.enableBattVoltageMeasure()
    pmu.enableSystemVoltageMeasure()
    pmu.enableTemperatureMeasure()
    # Disable unused:
    pmu.disableDC2()
    pmu.disableDC4()
    pmu.disableDC5()
    pmu.disableALDO1()
    pmu.disableCPUSLDO()
    pmu.disableDLDO2()
    # PMU interrupts
    pmu.disableIRQ(AXP2101.XPOWERS_AXP2101_ALL_IRQ);
    # Enable the required interrupt function
    pmu.enableIRQ(
        AXP2101.XPOWERS_AXP2101_BAT_INSERT_IRQ    | AXP2101.XPOWERS_AXP2101_BAT_REMOVE_IRQ      |   # BATTERY
        AXP2101.XPOWERS_AXP2101_VBUS_INSERT_IRQ   | AXP2101.XPOWERS_AXP2101_VBUS_REMOVE_IRQ     |   # VBUS
        AXP2101.XPOWERS_AXP2101_PKEY_SHORT_IRQ    | AXP2101.XPOWERS_AXP2101_PKEY_LONG_IRQ       |   # POWER KEY
        AXP2101.XPOWERS_AXP2101_BAT_CHG_DONE_IRQ  | AXP2101.XPOWERS_AXP2101_BAT_CHG_START_IRQ       # CHARGE
    )
    # Clear all interrupt flags
    pmu.clearIrqStatus()
    # Set the precharge charging current
    pmu.setPrechargeCurr(AXP2101.XPOWERS_AXP2101_PRECHARGE_50MA)
    # It is recommended to charge at less than 130mA
    pmu.setChargerConstantCurr(AXP2101.XPOWERS_AXP2101_CHG_CUR_125MA)
    # Set stop charging termination current
    pmu.setChargerTerminationCurr(AXP2101.XPOWERS_AXP2101_CHG_ITERM_25MA)
    # T-Watch-S3 uses a high-voltage(4.35V) battery by default but a bit less to increase battery life
    pmu.setChargeTargetVoltage(AXP2101.XPOWERS_AXP2101_CHG_VOL_4V2)
    mpos.pmu = pmu
    print("Initializing AXP2101 PMU completed.")


import mpos
from machine import I2C, Pin, SPI
import micropython
import time

PMU_INT_PIN = const(21)
_PMU_IRQ_SCHEDULED = False

m_i2c = I2C(1, sda=Pin(10), scl=Pin(11), freq=400000)

try:
    init_pmu(m_i2c)
except Exception as e:
    print(f"Exception while initializing PMU: {e}")


def _pmu_irq_task(_arg):
    global _PMU_IRQ_SCHEDULED
    _PMU_IRQ_SCHEDULED = False
    status = mpos.pmu.getIrqStatus()
    print("PMU interrupt: status=0x{0:06X}".format(status))
    if mpos.pmu.isPekeyShortPressIrq():
        print("PMU interrupt: PEKEY short press")
        if mpos.pmu.isEnableALDO2():
            mpos.pmu.disableALDO2()
        else:
            mpos.pmu.enableALDO2()
    if mpos.pmu.isPekeyLongPressIrq():
        print("PMU interrupt: PEKEY long press")
    mpos.pmu.clearIrqStatus()


def _handle_pmu_irq(_pin):
    global _PMU_IRQ_SCHEDULED
    if _PMU_IRQ_SCHEDULED:
        return
    _PMU_IRQ_SCHEDULED = True
    try:
        micropython.schedule(_pmu_irq_task, 0)
    except Exception:
        _PMU_IRQ_SCHEDULED = False

pmu_int = Pin(PMU_INT_PIN, Pin.IN, Pin.PULL_UP)
pmu_int.irq(trigger=Pin.IRQ_FALLING, handler=_handle_pmu_irq)


print("DRV2605L vibrator test")
DRV2605L_ADDR = 0x5A
m_i2c.writeto_mem(DRV2605L_ADDR, 0x01, bytes([0x00])) # reg 0x01 = mode (0x00 = internal trigger)
m_i2c.writeto_mem(DRV2605L_ADDR, 0x03, bytes([0x00])) # reg 0x03 = waveform sequence slot 1 (0 = Library A)
m_i2c.writeto_mem(DRV2605L_ADDR, 0x04, bytes([12])) # Triple Click - 100%
m_i2c.writeto_mem(DRV2605L_ADDR, 0x05, bytes([89])) # Transition Ramp Up Long Sharp 2 – 0 to 100%
m_i2c.writeto_mem(DRV2605L_ADDR, 0x0C, bytes([1])) # reg 0x0C = GO (1 = start, 0 = stop)


print("BMA423 IMU test")
import drivers.imu_sensor.bma423.bma423 as bma423
sensor = bma423.BMA423(m_i2c, address=0x19)
time.sleep_ms(250) # some sleep is needed before reading values
print("temperature: ", sensor.get_temperature())
print("steps: ", sensor.get_steps())
print("(x,y,z): ", sensor.get_xyz())


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
touch_i2c_bus = i2c.I2C.Bus(host=0, sda=39, scl=40, freq=400000, use_locks=False)
touch_dev = i2c.I2C.Device(bus=touch_i2c_bus, dev_id=ft6x36.I2C_ADDR, reg_bits=ft6x36.BITS)
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


# TODO:
# - battery
# - real IMU driver (instead of proof-of-concept above)
# - GPS

print("lilygo_t_watch_s3_plus.py finished")
