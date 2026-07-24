"""Minimal device manager for shared bus references."""


class DeviceManager:
    _i2c_buses = []

    @classmethod
    def registerBus(cls, type="i2c", i2c_bus=None):
        if type == "i2c" and i2c_bus is not None:
            cls._i2c_buses.append(i2c_bus)

    @classmethod
    def getBus(cls, type="i2c"):
        if type == "i2c" and cls._i2c_buses:
            return cls._i2c_buses[0]
        return None
