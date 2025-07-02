import time
import mpos.config
from mpos.timezones import TIMEZONE_MAP

import localPTZtime

timezone_preference = None

def epoch_seconds():
    import sys
    if sys.platform == "esp32":
        # on esp32, it needs this correction:
        return time.time() + 946684800
    else:
        return round(time.time())

def sync_time():
    import ntptime
    print("Synchronizing clock...")
    # Set the NTP server and sync time
    ntptime.host = 'pool.ntp.org'  # Set NTP server
    try:
        print('Syncing time with', ntptime.host)
        ntptime.settime()  # Fetch and set time (in UTC)
        print("Time sync'ed successfully")
        refresh_timezone_preference() # if the time was sync'ed, then it needs refreshing
    except Exception as e:
        print('Failed to sync time:', e)

def refresh_timezone_preference():
    global timezone_preference
    prefs = mpos.config.SharedPreferences("com.micropythonos.settings")
    timezone_preference = prefs.get_string("timezone")
    if not timezone_preference:
        timezone_preference = "Etc/GMT" # Use a default value so that it doesn't refresh every time the time is requested

def localtime():
    global timezone_preference
    if not timezone_preference: # if it's the first time, then it needs refreshing
        refresh_timezone_preference()
    ptz = timezone_to_posix_time_zone(timezone_preference)
    t = time.time()
    return localPTZtime.tztime(t, ptz)

def timezone_to_posix_time_zone(timezone):
    """
    Convert a timezone name to its POSIX timezone string.

    Args:
        timezone (str or None): Timezone name (e.g., 'Africa/Abidjan') or None.

    Returns:
        str: POSIX timezone string (e.g., 'GMT0'). Returns 'GMT0' if timezone is None or not found.
    """
    if timezone is None or timezone not in TIMEZONE_MAP:
        return "GMT0"
    return TIMEZONE_MAP[timezone]

def get_timezones():
    """
    Get a list of all available timezone names.

    Returns:
        list: List of timezone names (e.g., ['Africa/Abidjan', 'Africa/Accra', ...]).
    """
    return sorted(TIMEZONE_MAP.keys()) # even though they are defined alphabetical, the order isn't maintained in MicroPython

