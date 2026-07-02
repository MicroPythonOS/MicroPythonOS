class Sensor:
    """Sensor metadata (lightweight data class, Android-inspired)."""

    def __init__(self, name, sensor_type, vendor, version, max_range, resolution, power_ma):
        """Initialize sensor metadata.

        Args:
            name: Human-readable sensor name
            sensor_type: Sensor type constant (TYPE_ACCELEROMETER, etc.)
            vendor: Sensor vendor/manufacturer
            version: Driver version
            max_range: Maximum measurement range (with units)
            resolution: Measurement resolution (with units)
            power_ma: Power consumption in mA (or 0 if unknown)
        """
        self.name = name
        self.type = sensor_type
        self.vendor = vendor
        self.version = version
        self.max_range = max_range
        self.resolution = resolution
        self.power = power_ma

    def __repr__(self):
        return f"Sensor({self.name}, type={self.type})"
