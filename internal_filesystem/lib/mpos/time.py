import logging
import time
from .time_zone import TimeZone

import localPTZtime

logger = logging.getLogger(__name__)

def epoch_seconds():
    import sys
    if sys.platform == "esp32":
        # on esp32, it needs this correction:
        return time.time() + 946684800
    else:
        return round(time.time())

def sync_time():
    import ntptime
    if __debug__: logger.debug("Synchronizing clock...")
    # Set the NTP server and sync time
    ntptime.host = 'pool.ntp.org'  # Set NTP server
    try:
        if __debug__: logger.debug("Syncing time with %s", ntptime.host)
        ntptime.settime()  # Fetch and set time (in UTC)
        if __debug__: logger.debug("Time sync'ed successfully")
        if hasattr(TimeZone, "rtc"):
            if __debug__: logger.debug("Real Time Clock (RTC) found, setting it")
            try: # RTC driver might throw an exception
                import time
                lt = time.localtime() # (year, month, mday, hour, minute, second, weekday, yearday)
                TimeZone.rtc.datetime((lt[0],lt[1],lt[2],lt[6],lt[3],lt[4],lt[5])) # weekday order is different
            except Exception as e:
                logger.error("Exception while setting RTC time: %s", e)
        TimeZone.refresh_timezone_preference() # if the time was sync'ed, then it needs refreshing
    except Exception as e:
        logger.error("Failed to sync time: %s", e)

def localtime():
    if not TimeZone.timezone_preference: # if it's the first time, then it needs refreshing
        TimeZone.refresh_timezone_preference()
    ptz = TimeZone.timezone_to_posix_time_zone(TimeZone.timezone_preference)
    t = time.time()
    try:
        localtime = localPTZtime.tztime(t, ptz)
    except Exception:
        return time.localtime()
    return localtime

