"""
On-device tests for BLEManager Phase 2: GattServer and GattClient.

Requires a puppet ESP32S3 running tests/puppet_ble_echo.py within BLE range.

Usage:
  python3 scripts/test_runner.py tests/test_ble_manager_device.py --ondevice --port /dev/ttyACM0 --timeout 120
"""

import sys
import time
import unittest

try:
    import bluetooth
    from micropython import const
    HAS_BLE = True
except ImportError:
    HAS_BLE = False


_IRQ_SCAN_RESULT = 5
_IRQ_SCAN_DONE = 6
_IRQ_PERIPHERAL_CONNECT = 7
_IRQ_PERIPHERAL_DISCONNECT = 8
_IRQ_GATTC_SERVICE_RESULT = 9
_IRQ_GATTC_SERVICE_DONE = 10
_IRQ_GATTC_CHARACTERISTIC_RESULT = 11
_IRQ_GATTC_CHARACTERISTIC_DONE = 12
_IRQ_GATTC_NOTIFY = 18

PUPPET_NAME = b"BLE-Puppet"
_ECHO_SVC_UUID = bluetooth.UUID("12345678-1234-1234-1234-123456789ABC") if HAS_BLE else None
_ECHO_CHAR_UUID = bluetooth.UUID("12345678-1234-1234-1235-123456789ABC") if HAS_BLE else None

_TIMEOUT_MS = 15000


class BLEEchoClient:
    def __init__(self):
        self._ble = bluetooth.BLE()
        self._ble.active(True)
        self._ble.irq(self._irq)
        self._addr_type = None
        self._addr = None
        self._conn_handle = None
        self._svc_start = None
        self._svc_end = None
        self._echo_handle = None
        self._notify_data = None
        self._irq_depth = 0

    def _irq(self, event, data):
        self._irq_depth += 1
        if self._irq_depth > 8:
            self._irq_depth -= 1
            return
        try:
            if event == _IRQ_SCAN_RESULT:
                _addr_type, addr, _adv_type, _rssi, adv_data = data
                addr = bytes(addr)
                if PUPPET_NAME in adv_data:
                    self._addr_type = _addr_type
                    self._addr = addr
            elif event == _IRQ_PERIPHERAL_CONNECT:
                self._conn_handle, _, _ = data
            elif event == _IRQ_PERIPHERAL_DISCONNECT:
                self._conn_handle = None
                self._svc_start = None
                self._svc_end = None
                self._echo_handle = None
            elif event == _IRQ_GATTC_SERVICE_RESULT:
                conn_handle, start, end, uuid = data
                if HAS_BLE and isinstance(uuid, bluetooth.UUID):
                    pass
                if uuid == 0xB2E4:
                    pass
                self._svc_start = start
                self._svc_end = end
            elif event == _IRQ_GATTC_CHARACTERISTIC_RESULT:
                conn_handle, _def_handle, value_handle, _props, uuid = data
                self._echo_handle = value_handle
            elif event == _IRQ_GATTC_NOTIFY:
                _conn_handle, _value_handle, notify_data = data
                self._notify_data = bytes(notify_data)
        except Exception:
            pass
        self._irq_depth -= 1

    def scan_and_find(self, timeout_ms=None):
        if timeout_ms is None:
            timeout_ms = _TIMEOUT_MS
        self._addr_type = None
        self._addr = None
        self._ble.gap_scan(0, 30000, 30000)
        deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            if self._addr is not None:
                self._ble.gap_scan(None)
                return True
            time.sleep_ms(50)
        self._ble.gap_scan(None)
        return False

    def connect(self, timeout_ms=None):
        if timeout_ms is None:
            timeout_ms = _TIMEOUT_MS
        if self._addr_type is None or self._addr is None:
            return False
        self._ble.gap_connect(self._addr_type, self._addr)
        deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            if self._conn_handle is not None:
                return True
            time.sleep_ms(50)
        return False

    def wait_for_services(self, timeout_ms=None):
        if timeout_ms is None:
            timeout_ms = _TIMEOUT_MS
        if self._conn_handle is None:
            return False
        self._svc_start = None
        self._svc_end = None
        self._ble.gattc_discover_services(self._conn_handle)
        deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            if self._svc_end is not None:
                return True
            time.sleep_ms(50)
        return False

    def wait_for_characteristics(self, timeout_ms=None):
        if timeout_ms is None:
            timeout_ms = _TIMEOUT_MS
        if self._conn_handle is None or self._svc_start is None:
            return False
        self._echo_handle = None
        self._ble.gattc_discover_characteristics(self._conn_handle, self._svc_start, self._svc_end)
        deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            if self._echo_handle is not None:
                return True
            time.sleep_ms(50)
        return False

    def write_and_wait_notify(self, data, timeout_ms=None):
        if timeout_ms is None:
            timeout_ms = _TIMEOUT_MS
        if self._conn_handle is None or self._echo_handle is None:
            return None
        self._notify_data = None
        self._ble.gattc_write(self._conn_handle, self._echo_handle, data, 1)
        deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
        while time.ticks_diff(deadline, time.ticks_ms()) > 0:
            if self._notify_data is not None:
                result = self._notify_data
                self._notify_data = None
                return result
            time.sleep_ms(50)
        return None

    def disconnect(self):
        if self._conn_handle is not None:
            self._ble.gap_disconnect(self._conn_handle)

    def deinit(self):
        self._ble.active(False)


class TestBLEManagerDevice(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform != "esp32":
            raise unittest.SkipTest("Requires ESP32 hardware with BLE")
        cls.client = BLEEchoClient()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "client"):
            cls.client.disconnect()
            cls.client.deinit()

    def test_scan_finds_puppet(self):
        found = self.client.scan_and_find()
        self.assertTrue(found, "Puppet 'BLE-Puppet' not found")

    def test_connect_to_puppet(self):
        self.assertTrue(self.client.scan_and_find())
        self.assertTrue(self.client.connect())

    def test_discover_services(self):
        self.assertTrue(self.client.scan_and_find())
        self.assertTrue(self.client.connect())
        self.assertTrue(self.client.wait_for_services())

    def test_discover_characteristics(self):
        self.assertTrue(self.client.scan_and_find())
        self.assertTrue(self.client.connect())
        self.assertTrue(self.client.wait_for_services())
        self.assertTrue(self.client.wait_for_characteristics())

    def test_echo_write_read(self):
        self.assertTrue(self.client.scan_and_find())
        self.assertTrue(self.client.connect())
        self.assertTrue(self.client.wait_for_services())
        self.assertTrue(self.client.wait_for_characteristics())
        echo = self.client.write_and_wait_notify(b"ping")
        self.assertIsNotNone(echo)
        self.assertEqual(echo, b"ping")
