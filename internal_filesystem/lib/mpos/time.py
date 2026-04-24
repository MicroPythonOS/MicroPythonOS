import time
from .time_zone import TimeZone

import localPTZtime

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
        if hasattr(TimeZone, "rtc"):
            print("Real Time Clock (RTC) found, setting it")
            try: # RTC driver might throw an exception
                import time
                lt = time.localtime() # (year, month, mday, hour, minute, second, weekday, yearday)
                TimeZone.rtc.datetime((lt[0],lt[1],lt[2],lt[6],lt[3],lt[4],lt[5])) # weekday order is different
            except Exception as e:
                print(f"Exception while setting RTC time: {e}")
        TimeZone.refresh_timezone_preference() # if the time was sync'ed, then it needs refreshing
    except Exception as e:
        print('Failed to sync time:', e)

def localtime():
    if not TimeZone.timezone_preference: # if it's the first time, then it needs refreshing
        TimeZone.refresh_timezone_preference()
    ptz = TimeZone.timezone_to_posix_time_zone(TimeZone.timezone_preference)
    t = time.time()
    try:
        localtime = localPTZtime.tztime(t, ptz)
    except Exception as e:
        #print(f"localPTZtime setting got exception {e}, defaulting to non-localized time...") # this gets called too often to print
        return time.localtime()
    return localtime

