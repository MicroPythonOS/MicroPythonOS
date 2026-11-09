from machine import Pin, SoftI2C


def _matches(scl, sda, addresses, register, expected, addrsize=8):
    try:
        bus = SoftI2C(scl=Pin(scl), sda=Pin(sda), freq=100000, timeout=10000)
        for address in addresses:
            try:
                value = bus.readfrom_mem(address, register, len(expected), addrsize=addrsize)
                if value == expected:
                    return True
            except OSError:
                continue
        return False
    finally:
        Pin(scl, Pin.IN, pull=None)
        Pin(sda, Pin.IN, pull=None)


def detect():
    try:
        if not _matches(41, 42, (0x5D, 0x14), 0x8140, b"911\x00", 16):
            return False
        return _matches(7, 6, (0x6A, 0x6B), 0, b"\x05")
    except (OSError, ValueError):
        return False
