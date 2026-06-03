# Payment class — one entry in the on-screen transaction list.
#
# Amounts are always stored as signed integer satoshis (negative = outgoing /
# fee-only self-transfer); the unit shown to the user is always sats too,
# regardless of whether the balance label is set to bits / micro-BTC / etc.
# The only display variation is whether to use the "₿" prefix vs the "sats"
# suffix (`use_symbol` toggle), and the thousands separator follows the
# MicroPythonOS NumberFormat preference (US "1,234", EU "1.234", etc.) so
# transaction amounts match the balance label's separator style.

try:
    from mpos import NumberFormat
    _HAVE_NUMBER_FORMAT = True
except ImportError:
    # Fallback for builds before MPOS 0.9.1 (when NumberFormat was added).
    # str() gives no thousands separator, but the app still renders correctly.
    _HAVE_NUMBER_FORMAT = False


def _format_sats(amount):
    """Render a signed satoshi integer with the user's MPOS-configured
    thousands separator. Falls back to bare str() if NumberFormat isn't
    available (pre-0.9.1 firmware)."""
    if _HAVE_NUMBER_FORMAT:
        return NumberFormat.format_number(int(amount))
    return str(int(amount))


class Payment:
    use_symbol = False  # When True, use ₿ prefix instead of "sats" suffix

    def __init__(self, epoch_time, amount_sats, comment):
        self.epoch_time = epoch_time
        self.amount_sats = amount_sats
        self.comment = comment

    def __str__(self):
        amount_str = _format_sats(self.amount_sats)
        if Payment.use_symbol:
            if not self.comment:
                verb = "spent"
                if self.amount_sats > 0:
                    verb = "received!"
                return f"₿{amount_str} {verb}"
            return f"₿{amount_str}: {self.comment}"
        else:
            sattext = "sats"
            if self.amount_sats == 1:
                sattext = "sat"
            if not self.comment:
                verb = "spent"
                if self.amount_sats > 0:
                    verb = "received!"
                return f"{amount_str} {sattext} {verb}"
            return f"{amount_str} {sattext}: {self.comment}"

    def __eq__(self, other):
        if not isinstance(other, Payment):
            return False
        return self.epoch_time == other.epoch_time and self.amount_sats == other.amount_sats and self.comment == other.comment

    def __lt__(self, other):
        if not isinstance(other, Payment):
            return NotImplemented
        return (self.epoch_time, self.amount_sats, self.comment) < (other.epoch_time, other.amount_sats, other.comment)

    def __le__(self, other):
        if not isinstance(other, Payment):
            return NotImplemented
        return (self.epoch_time, self.amount_sats, self.comment) <= (other.epoch_time, other.amount_sats, other.comment)

    def __gt__(self, other):
        if not isinstance(other, Payment):
            return NotImplemented
        return (self.epoch_time, self.amount_sats, self.comment) > (other.epoch_time, other.amount_sats, other.comment)

    def __ge__(self, other):
        if not isinstance(other, Payment):
            return NotImplemented
        return (self.epoch_time, self.amount_sats, self.comment) >= (other.epoch_time, other.amount_sats, other.comment)
