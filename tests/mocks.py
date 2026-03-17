class MockSharedPreferences:
    """Mock SharedPreferences for testing."""

    _all_data = {}  # Class-level storage

    def __init__(self, app_id, filename=None):
        self.app_id = app_id
        self.filename = filename
        if app_id not in MockSharedPreferences._all_data:
            MockSharedPreferences._all_data[app_id] = {}

    def _get_value(self, key, default):
        return MockSharedPreferences._all_data.get(self.app_id, {}).get(key, default)

    def get_dict(self, key):
        return self._get_value(key, {})

    def get_list(self, key, default=None):
        return self._get_value(key, default)

    def get_bool(self, key, default=False):
        value = self._get_value(key, default)
        return bool(value)

    def get_string(self, key, default=""):
        value = self._get_value(key, default)
        return value if value is not None else default

    def get_int(self, key, default=0):
        value = self._get_value(key, default)
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def edit(self):
        return MockEditor(self)

    @classmethod
    def reset_all(cls):
        cls._all_data = {}


class MockEditor:
    """Mock editor for SharedPreferences."""

    def __init__(self, prefs):
        self.prefs = prefs
        self.pending = {}

    def put_dict(self, key, value):
        self.pending[key] = value

    def put_list(self, key, value):
        self.pending[key] = value

    def put_bool(self, key, value):
        self.pending[key] = bool(value)

    def put_string(self, key, value):
        self.pending[key] = value

    def put_int(self, key, value):
        self.pending[key] = int(value)

    def commit(self):
        if self.prefs.app_id not in MockSharedPreferences._all_data:
            MockSharedPreferences._all_data[self.prefs.app_id] = {}
        MockSharedPreferences._all_data[self.prefs.app_id].update(self.pending)


class MockMpos:
    """Mock mpos module with config and time."""

    class config:
        @staticmethod
        def SharedPreferences(app_id):
            return MockSharedPreferences(app_id)

    class time:
        @staticmethod
        def sync_time():
            pass  # No-op for testing


class HotspotMockNetwork:
    """Mock network module with AP/STA support for hotspot tests."""

    STA_IF = 0
    AP_IF = 1

    AUTH_OPEN = 0
    AUTH_WPA_PSK = 1
    AUTH_WPA2_PSK = 2
    AUTH_WPA_WPA2_PSK = 3

    class MockWLAN:
        def __init__(self, interface):
            self.interface = interface
            self._active = False
            self._connected = False
            self._config = {}
            self._scan_results = []
            self._ifconfig = ("0.0.0.0", "0.0.0.0", "0.0.0.0", "0.0.0.0")

        def active(self, is_active=None):
            if is_active is None:
                return self._active
            self._active = is_active
            return None

        def isconnected(self):
            return self._connected

        def connect(self, ssid, password):
            self._connected = True
            self._config["essid"] = ssid

        def disconnect(self):
            self._connected = False

        def config(self, *args, **kwargs):
            if kwargs:
                self._config.update(kwargs)
                return None
            if args:
                return self._config.get(args[0])
            return self._config

        def ifconfig(self, cfg=None):
            if cfg is None:
                return self._ifconfig
            self._ifconfig = cfg
            return None

        def ipconfig(self, key=None):
            config = self.ifconfig()
            mapping = {
                "addr4": config[0],
                "netmask4": config[1],
                "gw4": config[2],
                "dns4": config[3],
            }
            if key is None:
                return mapping
            return mapping.get(key)

        def scan(self):
            return self._scan_results

    def __init__(self):
        self._wlan_instances = {}

    def WLAN(self, interface):
        if interface not in self._wlan_instances:
            self._wlan_instances[interface] = self.MockWLAN(interface)
        return self._wlan_instances[interface]


class MockADC:
    """Mock ADC for testing."""

    ATTN_11DB = 3

    def __init__(self, pin):
        self.pin = pin
        self._atten = None
        self._read_value = 2048

    def atten(self, value):
        self._atten = value

    def read(self):
        return self._read_value

    def set_read_value(self, value):
        """Test helper to set ADC reading."""
        self._read_value = value


class MockPin:
    """Mock Pin for testing."""

    def __init__(self, pin_num):
        self.pin_num = pin_num


class MockMachineADC:
    """Mock machine module with ADC/Pin."""

    ADC = MockADC
    Pin = MockPin


class MockWifiService:
    """Mock WifiService for testing."""

    wifi_busy = False
    _connected = False
    _temporarily_disabled = False

    @classmethod
    def is_connected(cls):
        return cls._connected

    @classmethod
    def disconnect(cls):
        cls._connected = False

    @classmethod
    def temporarily_disable(cls):
        """Temporarily disable WiFi and return whether it was connected."""
        if cls.wifi_busy:
            raise RuntimeError("Cannot disable WiFi: WifiService is already busy")
        was_connected = cls._connected
        cls.wifi_busy = True
        cls._connected = False
        cls._temporarily_disabled = True
        return was_connected

    @classmethod
    def temporarily_enable(cls, was_connected):
        """Re-enable WiFi and reconnect if it was connected before."""
        cls.wifi_busy = False
        cls._temporarily_disabled = False
        if was_connected:
            cls._connected = True

    @classmethod
    def reset(cls):
        """Test helper to reset state."""
        cls.wifi_busy = False
        cls._connected = False
        cls._temporarily_disabled = False


class MockI2C:
    """Mock I2C bus for testing."""

    def __init__(self, bus_id, sda=None, scl=None):
        self.bus_id = bus_id
        self.sda = sda
        self.scl = scl
        self.memory = {}

    def readfrom_mem(self, addr, reg, nbytes):
        """Read from memory (simulates I2C read)."""
        if addr not in self.memory:
            raise OSError("I2C device not found")
        if reg not in self.memory[addr]:
            return bytes([0] * nbytes)
        return bytes(self.memory[addr][reg])

    def writeto_mem(self, addr, reg, data):
        """Write to memory (simulates I2C write)."""
        if addr not in self.memory:
            self.memory[addr] = {}
        self.memory[addr][reg] = list(data)


class MockQMI8658:
    """Mock QMI8658 IMU sensor."""

    def __init__(self, i2c_bus, address=0x6B, accel_scale=0b10, gyro_scale=0b100):
        self.i2c = i2c_bus
        self.address = address
        self.accel_scale = accel_scale
        self.gyro_scale = gyro_scale

    @property
    def temperature(self):
        """Return mock temperature."""
        return 25.5

    @property
    def acceleration(self):
        """Return mock acceleration (in G)."""
        return (0.0, 0.0, 1.0)

    @property
    def gyro(self):
        """Return mock gyroscope (in deg/s)."""
        return (0.0, 0.0, 0.0)


class MockWsenIsds:
    """Mock WSEN_ISDS IMU sensor."""

    def __init__(self, i2c, address=0x6B, acc_range="8g", acc_data_rate="104Hz",
                 gyro_range="500dps", gyro_data_rate="104Hz"):
        self.i2c = i2c
        self.address = address
        self.acc_range = acc_range
        self.gyro_range = gyro_range
        self.acc_sensitivity = 0.244
        self.gyro_sensitivity = 17.5
        self.acc_offset_x = 0
        self.acc_offset_y = 0
        self.acc_offset_z = 0
        self.gyro_offset_x = 0
        self.gyro_offset_y = 0
        self.gyro_offset_z = 0

    def get_chip_id(self):
        """Return WHO_AM_I value."""
        return 0x6A

    def _read_raw_accelerations(self):
        """Return mock acceleration (in mg)."""
        return (0.0, 0.0, 1000.0)

    def read_angular_velocities(self):
        """Return mock gyroscope (in mdps)."""
        return (0.0, 0.0, 0.0)

    def acc_calibrate(self, samples=None):
        """Mock calibration."""
        pass

    def gyro_calibrate(self, samples=None):
        """Mock calibration."""
        pass


def make_machine_i2c_module(i2c_cls, pin_cls=None):
    if pin_cls is None:
        pin_cls = type("Pin", (), {})
    return type("module", (), {"I2C": i2c_cls, "Pin": pin_cls})()


def make_machine_timer_module(timer_cls):
    return type("module", (), {"Timer": timer_cls})()


def make_usocket_module(socket_cls):
    class MockUsocket:
        """Mock usocket module."""

        AF_INET = socket_cls.AF_INET
        SOCK_STREAM = socket_cls.SOCK_STREAM

        @staticmethod
        def socket(af, sock_type):
            return socket_cls(af, sock_type)

    return MockUsocket


def make_config_module(shared_prefs_cls):
    return type("module", (), {"SharedPreferences": shared_prefs_cls})()
