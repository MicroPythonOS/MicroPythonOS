from . import config


NUMBER_FORMAT_MAP = {
    "comma_dot":   (".", ","),   # 1,234.56  US/UK
    "dot_comma":   (",", "."),   # 1.234,56  Europe
    "space_comma": (",", " "),   # 1 234,56  French
    "apos_dot":    (".", "'"),   # 1'234.56  Swiss
    "under_dot":   (".", "_"),   # 1_234.56  Tech
    "none_dot":    (".", ""),    # 1234.56   No thousands
    "none_comma":  (",", ""),    # 1234,56   No thousands
}

DEFAULT_FORMAT = "comma_dot"


class NumberFormat:
    """Number formatting utility using the system number format preference."""

    number_format_preference = None

    @staticmethod
    def refresh_preference():
        """Refresh the number format preference from SharedPreferences."""
        NumberFormat.number_format_preference = config.SharedPreferences(
            "com.micropythonos.settings"
        ).get_string("number_format")
        if not NumberFormat.number_format_preference:
            NumberFormat.number_format_preference = DEFAULT_FORMAT

    @staticmethod
    def get_separators():
        """Return (decimal_sep, thousands_sep) for the current preference."""
        if NumberFormat.number_format_preference is None:
            NumberFormat.refresh_preference()
        return NUMBER_FORMAT_MAP.get(
            NumberFormat.number_format_preference,
            NUMBER_FORMAT_MAP[DEFAULT_FORMAT],
        )

    @staticmethod
    def format_number(value, decimals=None):
        """Format a number using the current number format preference.

        Args:
            value: int or float to format.
            decimals: number of decimal places (None = auto for ints, strip trailing zeros for floats).

        Returns:
            Formatted string.
        """
        dec_sep, thou_sep = NumberFormat.get_separators()

        if isinstance(value, int) and decimals is None:
            negative = value < 0
            s = str(abs(value))
            s = _insert_thousands(s, thou_sep)
            return ("-" + s) if negative else s

        # Float formatting
        if decimals is None:
            decimals = 2
        s = "{:.{}f}".format(float(value), decimals)

        negative = s.startswith("-")
        if negative:
            s = s[1:]

        # Split on the Python decimal point
        if "." in s:
            int_part, frac_part = s.split(".")
            # Strip trailing zeros from fractional part
            frac_part = frac_part.rstrip("0")
        else:
            int_part = s
            frac_part = ""

        int_part = _insert_thousands(int_part, thou_sep)

        if frac_part:
            result = int_part + dec_sep + frac_part
        else:
            result = int_part

        return ("-" + result) if negative else result

    @staticmethod
    def get_format_options():
        """Return a list of (label, key) tuples for the settings dropdown."""
        return [
            ("1,234.56 (US/UK)", "comma_dot"),
            ("1.234,56 (Europe)", "dot_comma"),
            ("1 234,56 (French)", "space_comma"),
            ("1'234.56 (Swiss)", "apos_dot"),
            ("1_234.56 (Tech)", "under_dot"),
            ("1234.56 (No separator)", "none_dot"),
            ("1234,56 (No separator)", "none_comma"),
        ]


def _insert_thousands(int_str, separator):
    """Insert thousands separator into an integer string."""
    if not separator or len(int_str) <= 3:
        return int_str
    parts = []
    while len(int_str) > 3:
        parts.append(int_str[-3:])
        int_str = int_str[:-3]
    parts.append(int_str)
    parts.reverse()
    return separator.join(parts)
