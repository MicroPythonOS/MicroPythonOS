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
    pmu.setDLDO1Voltage(3300) # even 500mV doesn't seem to cause issues, but Imax=300mA is << 1.6A capability of MAX98357
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
        #AXP2101.XPOWERS_AXP2101_BAT_INSERT_IRQ    | AXP2101.XPOWERS_AXP2101_BAT_REMOVE_IRQ      |   # BATTERY is not removable
        #AXP2101.XPOWERS_AXP2101_VBUS_INSERT_IRQ   | AXP2101.XPOWERS_AXP2101_VBUS_REMOVE_IRQ     |   # VBUS don't think this will be used
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
    # T-Watch-S3 uses a high-voltage(4.35V) battery by default but let's use a bit less (4.2V) to increase battery life
    pmu.setChargeTargetVoltage(AXP2101.XPOWERS_AXP2101_CHG_VOL_4V2)
    # Quick and dirty patch of BatteryManager to use the PMU:
    BatteryManager.read_raw_adc =  lambda *args: 0
    BatteryManager.has_battery = lambda *args: True
    BatteryManager.get_battery_percentage = pmu.getBatteryPercent
    BatteryManager.read_battery_voltage = lambda *args: pmu.getBattVoltage() / 1000
    BatteryManager.pmu = pmu # make the PMU object accessible just in case
    print("Initializing AXP2101 PMU completed.")


import mpos
from machine import I2C, Pin, SPI
import micropython
import time

m_i2c = I2C(1, sda=Pin(10), scl=Pin(11), freq=400000)

from mpos import BatteryManager

try:
    init_pmu(m_i2c)
except Exception as e:
    print(f"Exception while initializing PMU: {e}")

async def pmu_irq_watchdog():
    # Workaround for IRQ's that don't always get cleared (race condition?)
    pmu = BatteryManager.pmu
    while True:
        await TaskManager.sleep(3)          # check every 3 seconds
        if pmu_int.value() == 0:        # IRQ pin is still LOW → stuck!
            print("PMU IRQ line is stuck low - running recovery...")
            for _ in range(10):
                pmu.clearIrqStatus()
                await TaskManager.sleep_ms(10)
            print("PMU IRQ recovery completed")

def _pmu_irq_task(_arg):
    pmu = BatteryManager.pmu
    try:
        status = pmu.getIrqStatus()
        print(f"PMU interrupt: status=0x{status:06X}")
        if status == 0:
            print("PMU: spurious interrupt (status already cleared)")
            return
        if pmu.isPekeyShortPressIrq():
            print("PMU interrupt: PEKEY short press")
            if pmu.isEnableALDO2():
                pmu.disableALDO2() # backlight
                pmu.disableALDO3() # touch chip
                # Would be good to put the ESP32 in a sleep state, turn off wifi etc...
            else:
                pmu.enableALDO3() # touch chip (takes about 1 second to become operational)
                pmu.enableALDO2() # backlight
        if pmu.isPekeyLongPressIrq():
            print("PMU interrupt: PEKEY long press")
    except Exception as e:
        print(f"Exception in PMU IRQ task: {e}")
    finally:
        # clear interrupt, can take multiple tries
        attempts = 0
        while pmu.getIrqStatus() != 0 and attempts < 5:   # safety limit
            attempts += 1
            pmu.clearIrqStatus()

def _handle_pmu_irq(_pin):
    try:
        micropython.schedule(_pmu_irq_task, 0)
    except Exception as e:
        print(f"Exception when scheduling PMU button press handler: {e}")

pmu_int = Pin(21, Pin.IN, Pin.PULL_UP)
pmu_int.irq(trigger=Pin.IRQ_FALLING, handler=_handle_pmu_irq)

from mpos import TaskManager
TaskManager.create_task(pmu_irq_watchdog())



print("DRV2605L vibrator test")
DRV2605L_ADDR = 0x5A
m_i2c.writeto_mem(DRV2605L_ADDR, 0x01, bytes([0x00])) # reg 0x01 = mode (0x00 = internal trigger)
m_i2c.writeto_mem(DRV2605L_ADDR, 0x03, bytes([0x00])) # reg 0x03 = waveform sequence slot 1 (0 = Library A)
m_i2c.writeto_mem(DRV2605L_ADDR, 0x04, bytes([12])) # Triple Click - 100%
m_i2c.writeto_mem(DRV2605L_ADDR, 0x05, bytes([89])) # Transition Ramp Up Long Sharp 2 – 0 to 100%
m_i2c.writeto_mem(DRV2605L_ADDR, 0x0C, bytes([1])) # reg 0x0C = GO (1 = start, 0 = stop)


print("BMA423 IMU init")
from mpos import SensorManager
SensorManager.init(m_i2c, address=0x19, mounted_position=SensorManager.FACING_EARTH)


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
AudioManager.add(
    AudioManager.Output(
        name="Speaker",
        kind="i2s",
        i2s_pins=i2s_output_pins,
    )
)
pdm_input_pins = {
    'sck_in': 44,   # SCLK - Serial Clock for microphone input
    'sd_in': 47,    # DIN - Serial Data IN (microphone)
}
AudioManager.add(
    AudioManager.Input(
        name="Microphone",
        kind="pdm",
        pdm_pins=pdm_input_pins,
    )
)

# RTC
import drivers.rtc.pcf8563 as pcf8563
rtc = pcf8563.PCF8563(m_i2c)
dt = rtc.datetime() # Get datetime tuple from PCF8563: (year, month, day, wday, hour, min, sec)
print("Datetime from RTC chip:", dt)
# machine.RTC expects 8-tuple: (year, month, day, weekday, hour, minute, second, subsecond) so need to set subsecond
rtc_tuple = (dt[0], dt[1], dt[2], dt[3], dt[4], dt[5], dt[6], 0)
from machine import RTC
RTC().datetime(rtc_tuple)
from mpos import TimeZone
TimeZone.rtc = rtc
# Would be good to also do this:
# rtc.setClockOutput(SensorPCF8563::CLK_DISABLE);   //Disable clock output to conserve backup battery power

# TODO:
# - GPS

print("lilygo_t_watch_s3_plus.py finished")
