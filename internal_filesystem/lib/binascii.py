from ubinascii import *

if not "unhexlify" in globals():

    def unhexlify(data):
        if len(data) % 2 != 0:
            raise ValueError("Odd-length string")

        return bytes([int(data[i : i + 2], 16) for i in range(0, len(data), 2)])


b2a_hex = hexlify
a2b_hex = unhexlify
