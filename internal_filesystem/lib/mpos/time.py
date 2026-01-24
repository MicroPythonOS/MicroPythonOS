import time
from . import config
from .time_zone import TimeZone

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
    prefs = config.SharedPreferences("com.micropythonos.settings")
    timezone_preference = prefs.get_string("timezone")
    if not timezone_preference:
        timezone_preference = "Etc/GMT" # Use a default value so that it doesn't refresh every time the time is requested

def localtime():
    global timezone_preference
    if not timezone_preference: # if it's the first time, then it needs refreshing
        refresh_timezone_preference()
    ptz = TimeZone.timezone_to_posix_time_zone(timezone_preference)
    t = time.time()
    try:
        localtime = localPTZtime.tztime(t, ptz)
    except Exception as e:
        #print(f"localPTZtime setting got exception {e}, defaulting to non-localized time...") # this gets called too often to print
        return time.localtime()
    return localtime

