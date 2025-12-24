import time

MIN_VOLTAGE = 3.15
MAX_VOLTAGE = 4.15

adc = None
conversion_func = None  # Conversion function: ADC value -> voltage
adc_pin = None

# Cache to reduce WiFi interruptions (ADC2 requires WiFi to be disabled)
_cached_raw_adc = None
_last_read_time = 0
CACHE_DURATION_ADC1_MS = 30000   # 30 seconds (cheaper: no WiFi interference)
CACHE_DURATION_ADC2_MS = 600000  # 600 seconds (expensive: requires WiFi disable)
#CACHE_DURATION_ADC2_MS = CACHE_DURATION_ADC1_MS # trigger frequent disconnections for debugging OSUpdate resume

def _is_adc2_pin(pin):
    """Check if pin is on ADC2 (ESP32-S3: GPIO11-20)."""
    return 11 <= pin <= 20


def init_adc(pinnr, adc_to_voltage_func):
    """
    Initialize ADC for battery voltage monitoring.

    IMPORTANT for ESP32-S3: ADC2 (GPIO11-20) doesn't work when WiFi is active!
    Use ADC1 pins (GPIO1-10) for battery monitoring if possible.
    If using ADC2, WiFi will be temporarily disabled during readings.

    Args:
        pinnr: GPIO pin number
        adc_to_voltage_func: Conversion function that takes raw ADC value (0-4095)
                             and returns battery voltage in volts
    """
    global adc, conversion_func, adc_pin

    conversion_func = adc_to_voltage_func
    adc_pin = pinnr

    try:
        print(f"Initializing ADC pin {pinnr} with conversion function")
        if _is_adc2_pin(pinnr):
            print(f"  WARNING: GPIO{pinnr} is on ADC2 - WiFi will be disabled during readings")
        from machine import ADC, Pin
        adc = ADC(Pin(pinnr))
        adc.atten(ADC.ATTN_11DB)  # 0-3.3V range
    except Exception as e:
        print(f"Info: this platform has no ADC for measuring battery voltage: {e}")

    initial_adc_value = read_raw_adc()
    print(f"Reading ADC at init to fill cache: {initial_adc_value} => {read_battery_voltage(raw_adc_value=initial_adc_value)}V => {get_battery_percentage(raw_adc_value=initial_adc_value)}%")


def read_raw_adc(force_refresh=False):
    """
    Read raw ADC value (0-4095) with adaptive caching.

    On ESP32-S3 with ADC2, WiFi is temporarily disabled during reading.
    Raises RuntimeError if WifiService is busy (connecting/scanning) when using ADC2.

    Args:
        force_refresh: Bypass cache and force fresh reading

    Returns:
        float: Raw ADC value (0-4095)

    Raises:
        RuntimeError: If WifiService is busy (only when using ADC2)
    """
    global _cached_raw_adc, _last_read_time

    # Desktop mode - return random value in typical ADC range
    if not adc:
        import random
        return random.randint(1900, 2600)

    # Check if this is an ADC2 pin (requires WiFi disable)
    needs_wifi_disable = adc_pin is not None and _is_adc2_pin(adc_pin)

    # Use different cache durations based on cost
    cache_duration = CACHE_DURATION_ADC2_MS if needs_wifi_disable else CACHE_DURATION_ADC1_MS

    # Check cache
    current_time = time.ticks_ms()
    if not force_refresh and _cached_raw_adc is not None:
        age = time.ticks_diff(current_time, _last_read_time)
        if age < cache_duration:
            return _cached_raw_adc

    # Import WifiService only if needed
    WifiService = None
    if needs_wifi_disable:
        try:
            from mpos.net.wifi_service import WifiService
        except ImportError:
            pass

    # Temporarily disable WiFi for ADC2 reading
    was_connected = False
    if needs_wifi_disable and WifiService:
        # This will raise RuntimeError if WiFi is already busy
        was_connected = WifiService.temporarily_disable()
        time.sleep(0.05)  # Brief delay for WiFi to fully disable

    try:
        # Read ADC (average of 10 samples)
        total = sum(adc.read() for _ in range(10))
        raw_value = total / 10.0

        # Update cache
        _cached_raw_adc = raw_value
        _last_read_time = current_time

        return raw_value

    finally:
        # Re-enable WiFi (only if we disabled it)
        if needs_wifi_disable and WifiService:
            WifiService.temporarily_enable(was_connected)


def read_battery_voltage(force_refresh=False, raw_adc_value=None):
    """
    Read battery voltage in volts.

    Args:
        force_refresh: Bypass cache and force fresh reading

    Returns:
        float: Battery voltage in volts (clamped to 0-MAX_VOLTAGE)
    """
    raw = raw_adc_value if raw_adc_value else read_raw_adc(force_refresh)
    voltage = conversion_func(raw) if conversion_func else 0.0
    return voltage


def get_battery_percentage(raw_adc_value=None):
    """
    Get battery charge percentage.

    Returns:
        float: Battery percentage (0-100)
    """
    voltage = read_battery_voltage(raw_adc_value=raw_adc_value)
    percentage = (voltage - MIN_VOLTAGE) * 100.0 / (MAX_VOLTAGE - MIN_VOLTAGE)
    return max(0,min(100.0, percentage)) # limit to 100.0% and make sure it's positive


def clear_cache():
    """Clear the battery voltage cache to force fresh reading on next call."""
    global _cached_raw_adc, _last_read_time
    _cached_raw_adc = None
    _last_read_time = 0
