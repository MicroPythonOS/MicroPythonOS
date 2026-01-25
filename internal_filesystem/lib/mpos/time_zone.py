from .time_zones import TIME_ZONE_MAP
from . import config


class TimeZone:
    """Timezone utility class for converting and managing timezone information."""

    timezone_preference = None

    @staticmethod
    def timezone_to_posix_time_zone(timezone):
        """
        Convert a timezone name to its POSIX timezone string.

        Args:
            timezone (str or None): Timezone name (e.g., 'Africa/Abidjan') or None.

        Returns:
            str: POSIX timezone string (e.g., 'GMT0'). Returns 'GMT0' if timezone is None or not found.
        """
        if timezone is None or timezone not in TIME_ZONE_MAP:
            return "GMT0"
        return TIME_ZONE_MAP[timezone]

    @staticmethod
    def get_timezones():
        """
        Get a list of all available timezone names.

        Returns:
            list: List of timezone names (e.g., ['Africa/Abidjan', 'Africa/Accra', ...]).
        """
        return sorted(TIME_ZONE_MAP.keys())  # even though they are defined alphabetical, the order isn't maintained in MicroPython

    @staticmethod
    def refresh_timezone_preference():
        """
        Refresh the timezone preference from SharedPreferences.
        """
        TimeZone.timezone_preference = config.SharedPreferences("com.micropythonos.settings").get_string("timezone")
        if not TimeZone.timezone_preference:
            TimeZone.timezone_preference = "Etc/GMT" # Use a default value so that it doesn't refresh every time the time is requested
