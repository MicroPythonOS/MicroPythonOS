from ubinascii import *

if not "Error" in globals():
    # CPython's binascii.Error is a ValueError subclass. ubinascii raises plain
    # ValueError and defines no Error, so base64.py's "raise binascii.Error(...)"
    # used to be an AttributeError.
    Error = ValueError

if not "unhexlify" in globals():

    def unhexlify(data):
        if len(data) % 2 != 0:
            raise ValueError("Odd-length string")

        return bytes([int(data[i : i + 2], 16) for i in range(0, len(data), 2)])


b2a_hex = hexlify
a2b_hex = unhexlify
