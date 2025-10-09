import time

MIN_VOLTAGE = 3.15
MAX_VOLTAGE = 4.15

adc = None
scale_factor = 0

# This gets called by (the device-specific) boot*.py
def init_adc(pinnr, sf):
    global adc, scale_factor
    try:
        print(f"Initializing ADC pin {pinnr} with scale_factor {scale_factor}")
        from machine import ADC, Pin # do this inside the try because it will fail on desktop
        adc = ADC(Pin(pinnr))
        # Set ADC to 11dB attenuation for 0–3.3V range (common for ESP32)
        adc.atten(ADC.ATTN_11DB)
        scale_factor = sf
    except Exception as e:
        print("Info: this platform has no ADC for measuring battery voltage")

def read_battery_voltage():
    if not adc:
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
    voltage = raw_value * scale_factor
    # Clamp to 0–4.2V range for LiPo battery
    voltage = max(0, min(voltage, MAX_VOLTAGE))
    return voltage

# Could be interesting to keep a "rolling average" of the percentage so that it doesn't fluctuate too quickly
def get_battery_percentage():
    return (read_battery_voltage() - MIN_VOLTAGE) * 100 / (MAX_VOLTAGE - MIN_VOLTAGE)

