adc = None
have_adc=True

# This gets called by (the device-specific) boot*.py
def init_adc(pinnr):
    global adc
    try:
        from machine import ADC, Pin
        print("setting adc")
        adc = ADC(Pin(pinnr))
        print("adc set")
        # Set ADC to 11dB attenuation for 0–3.3V range (common for ESP32)
        adc.atten(ADC.ATTN_11DB)
    except Exception as e:
        print("Info: this platform has no ADC for measuring battery voltage")
        have_adc=False

import time

# ADC parameters
VREF = 3.3  # Reference voltage (3.3V for most boards, adjust if different)
ADC_MAX = 4095  # 12-bit ADC resolution
VOLTAGE_DIVIDER = 3  # (R1 + R2) / R2 = (200k + 100k) / 100k = 3

MIN_VOLTAGE = 3.7
MAX_VOLTAGE = 4.2

# On fri3d-2024, it's 2367 for full
# Battery voltage ranges from 3.15V (0%) to 4.15 (100%) as datasheet specifies
# 3.0 +/- 0.1V (discharge cut-off) to 4.2V (no margin of error provided, assuming 0.05V)
# Charger stops charging at 4.07V (92%) to reduce battery wear.
#define RG_BATTERY_CALC_PERCENT(raw) (((raw) * 2.f - 3150.f) / (4150.f - 3150.f) * 100.f)
#define RG_BATTERY_CALC_VOLTAGE(raw) ((raw) * 2.f * 0.001f)


# USB connected, full battery: VBAT 4.179 5V: 5.1
# read_battery_voltage raw_value: 1598.4
# read_battery_voltage raw_value: 1598.1
# read_battery_voltage raw_value: 1596.5
# on display: 1596.8
# => FULL is 1597 at 4.193V so * 2.6255 / 1000
#
# unplugged: VBAT: 4.157 5V: 0
# 1591.3: 4.157		2.6123
# 1588.5: 4.156
# 1580.4: 4.14		2.619
# 1577.8: 4.12
# 1561.2: 4.08		2.61
# 1555: 4.06
# 1505: 3.95		2.624
# 1489: 3.90
# 1470: 3.85		2.61
# 1454: 3.8
# 1445: 3.81
# 1412 should be empty 3.7
#
# USB connected, no battery:
# 1566 * 0.00261 = 4.08V = 75%
# 1566 * 0.00241 = 3.77V = 14%
# 1564-1567
#
# quite empty and charging:
# 1594: 4.18V
# 16..
#
# logically, it should be * 0.00241758241758 but emperically, it seems to be * 0.00261 which is 8% higher
# => Let's go with 0.00262
def read_battery_voltage():
    if not have_adc:
        import random
        random_voltage = random.randint(round(MIN_VOLTAGE*100),round(MAX_VOLTAGE*100)) / 100
        #print(f"returning random voltage: {random_voltage}")
        return random_voltage
    # Read raw ADC value
    total = 0
    # Read multiple times to try to reduce variability.
    # Reading 10 times takes around 3ms so it's fine...
    for _ in range(10):
        total = total + adc.read()
    raw_value = total / 10
    #print(f"read_battery_voltage raw_value: {raw_value}")
    # Convert to voltage, accounting for divider and reference
    #voltage = (raw_value / ADC_MAX) * VREF * VOLTAGE_DIVIDER
    #voltage = raw_value * 262 / 100000 # 2inch
    voltage = raw_value * 2 / 1000 # fri3d-2024
    # Clamp to 0–4.2V range for LiPo battery
    voltage = max(0, min(voltage, MAX_VOLTAGE))
    #return raw_value
    return voltage

# Could be interesting to keep a "rolling average" of the percentage so that it doesn't fluctuate too quickly
def get_battery_percentage():
    return (read_battery_voltage() - MIN_VOLTAGE) * 100 / (MAX_VOLTAGE - MIN_VOLTAGE)


# Main loop to read and print battery voltage
if False:
#for _ in range(10):
    battery_voltage = read_battery_voltage()
    print("Battery Voltage: {:.2f} V".format(battery_voltage))
    time.sleep(1)  # Wait 1 second
