"""
BLEManager — Bluetooth Low Energy framework.

Singleton manager following the same module-level state pattern as BatteryManager.
All methods are @staticmethod / @classmethod; state lives in module globals.
"""

import logging

logger = logging.getLogger(__name__)

_ble = None
_simulation_mode = False
_irq = None

_scan_results = []
_scan_filters = []
_advertising = False
_advertising_was_connectable = False

_gatt_server = None
_gatt_clients = {}

_irq_handlers = []

_owner_tag = None
_owner_state = None


class ScanResult:
    __slots__ = ("addr_type", "addr", "rssi", "adv_data", "parsed_ad")

    def __init__(self, addr_type, addr, rssi, adv_data, parsed_ad=None):
        self.addr_type = addr_type
        self.addr = addr
        self.rssi = rssi
        self.adv_data = adv_data
        self.parsed_ad = parsed_ad or {}


class BLEManager:
    IRQ_CENTRAL_CONNECT = 1
    IRQ_CENTRAL_DISCONNECT = 2
    IRQ_GATTS_WRITE = 3
    IRQ_SCAN_RESULT = 5
    IRQ_SCAN_DONE = 6
    IRQ_PERIPHERAL_CONNECT = 7
    IRQ_PERIPHERAL_DISCONNECT = 8
    IRQ_GATTC_SERVICE_RESULT = 9
    IRQ_GATTC_SERVICE_DONE = 10
    IRQ_GATTC_CHARACTERISTIC_RESULT = 11
    IRQ_GATTC_CHARACTERISTIC_DONE = 12
    IRQ_GATTC_READ_RESULT = 15
    IRQ_GATTC_WRITE_DONE = 17
    IRQ_MTU_EXCHANGED = 21
    IRQ_GATTC_NOTIFY = 18

    AD_TYPE_SERVICE_UUID_16_COMPLETE = 3
    AD_TYPE_SHORT_NAME = 8
    AD_TYPE_COMPLETE_NAME = 9
    AD_TYPE_SERVICE_DATA_16 = 0x16
    AD_TYPE_MANUFACTURER = 0xFF

    @staticmethod
    def is_available():
        return _ble is not None

    @staticmethod
    def is_simulation():
        return _simulation_mode

    @classmethod
    def get_ble(cls):
        global _ble, _simulation_mode
        if _ble is None:
            _ble = cls._init_ble()
        return _ble

    @classmethod
    def _init_ble(cls):
        global _simulation_mode
        try:
            import bluetooth
        except ImportError:
            bluetooth = None
        if bluetooth is None:
            from mpos.testing.mocks import MockBluetooth

            _simulation_mode = True
            if __debug__:
                logger.debug("BLEManager: simulation mode (no bluetooth module)")
            return MockBluetooth().BLE()
        _simulation_mode = False
        return bluetooth.BLE()

    @classmethod
    def activate(cls):
        global _advertising
        ble = cls.get_ble()
        if not cls.is_active():
            ble.active(True)
            _advertising = False
            if __debug__:
                logger.debug("BLEManager: activated")

    @classmethod
    def deactivate(cls):
        global _advertising, _gatt_server
        ble = cls.get_ble()
        if cls.is_active():
            if _gatt_server:
                _gatt_server._on_radio_off()
            ble.active(False)
            _advertising = False
            if __debug__:
                logger.debug("BLEManager: deactivated")

    @classmethod
    def is_active(cls):
        ble = cls.get_ble()
        try:
            return ble.active()
        except Exception:
            return False

    @classmethod
    def register_irq(cls, handler):
        global _irq
        _irq = handler
        ble = cls.get_ble()
        ble.irq(cls._internal_irq)

    _irq_depth = 0

    @classmethod
    def _internal_irq(cls, event, data):
        cls._irq_depth += 1
        if cls._irq_depth > 8:
            cls._irq_depth -= 1
            return
        try:
            cls._dispatch_event(event, data)
        finally:
            cls._irq_depth -= 1

    @classmethod
    def _dispatch_event(cls, event, data):
        if event == cls.IRQ_SCAN_RESULT:
            addr_type, addr, adv_type, rssi, adv_data = data
            addr = bytes(addr)
            adv_data = bytes(adv_data)
            data = (addr_type, addr, adv_type, rssi, adv_data)
            parsed = cls.ad_parse(adv_data)
            if cls._apply_scan_filters(addr, parsed):
                _scan_results.append(
                    ScanResult(addr_type, addr, rssi, adv_data, parsed)
                )
                if _irq:
                    _irq(event, data)
        elif event == cls.IRQ_CENTRAL_DISCONNECT and _advertising:
            cls.start_advertising(connectable=_advertising_was_connectable)
            cls._dispatch_handlers(event, data)
            if _irq:
                _irq(event, data)
        elif event in (cls.IRQ_GATTS_WRITE, cls.IRQ_GATTC_NOTIFY):
            if _gatt_server and event == cls.IRQ_GATTS_WRITE:
                conn_handle, value_handle = data
                value = _ble.gatts_read(value_handle)
                _gatt_server._handle_write(conn_handle, value_handle, value)
            cls._dispatch_handlers(event, data)
            if _irq:
                _irq(event, data)
        else:
            cls._dispatch_handlers(event, data)
            if _irq:
                _irq(event, data)

    @classmethod
    def _dispatch_handlers(cls, event, data):
        for h in _irq_handlers:
            h(event, data)

    @classmethod
    def _apply_scan_filters(cls, addr, parsed_ad):
        if not _scan_filters:
            return True
        for f in _scan_filters:
            if f.get("mac") is not None and f["mac"] != addr:
                continue
            name_ok = True
            if f.get("name") is not None:
                ad_name = parsed_ad.get(cls.AD_TYPE_COMPLETE_NAME) or parsed_ad.get(cls.AD_TYPE_SHORT_NAME)
                name_ok = ad_name is not None and f["name"] in ad_name
            uuid_ok = True
            if f.get("service_uuid") is not None:
                uuid_ok = any(
                    parsed_ad.get(t) and f["service_uuid"] in parsed_ad[t]
                    for t in (cls.AD_TYPE_SERVICE_UUID_16_COMPLETE, 0x02, 0x04, 0x06)
                )
            if name_ok and uuid_ok:
                return True
        return False

    @staticmethod
    def ad_parse(adv_data):
        result = {}
        i = 0
        length = len(adv_data)
        while i < length - 1:
            field_len = adv_data[i]
            if field_len == 0 or i + field_len >= length:
                break
            ad_type = adv_data[i + 1]
            payload = adv_data[i + 2 : i + field_len + 1]
            if ad_type in result:
                existing = result[ad_type]
                if isinstance(existing, list):
                    existing.append(payload)
                else:
                    result[ad_type] = [existing, payload]
            else:
                result[ad_type] = payload
            i += field_len + 1
        return result

    @staticmethod
    def ad_field(ad_type, data):
        return bytes([len(data) + 1, ad_type]) + data

    @staticmethod
    def ad_build(fields):
        parts = []
        total = 0
        for ad_type, data in fields:
            field = BLEManager.ad_field(ad_type, data)
            if total + len(field) > 31:
                if __debug__:
                    logger.debug("ad_build: 31-byte limit reached, dropping field 0x%02x", ad_type)
                break
            parts.append(field)
            total += len(field)
        return b"".join(parts)

    @staticmethod
    def ad_build_scan_resp(fields):
        parts = []
        total = 0
        for ad_type, data in fields:
            field = BLEManager.ad_field(ad_type, data)
            if total + len(field) > 31:
                if __debug__:
                    logger.debug("ad_build_scan_resp: 31-byte limit reached, dropping field 0x%02x", ad_type)
                break
            parts.append(field)
            total += len(field)
        return b"".join(parts)

    @staticmethod
    def ad_name(name, short=False):
        name_bytes = name.encode("utf-8")[:29]
        ad_type = BLEManager.AD_TYPE_SHORT_NAME if short else BLEManager.AD_TYPE_COMPLETE_NAME
        return BLEManager.ad_field(ad_type, name_bytes)

    @staticmethod
    def ad_service_uuid(uuid_bytes):
        size = len(uuid_bytes)
        if size == 2:
            return BLEManager.ad_field(BLEManager.AD_TYPE_SERVICE_UUID_16_COMPLETE, uuid_bytes)
        _SIZES = {2: 0x02, 4: 0x04, 16: 0x06}
        ad_type = _SIZES.get(size, 0x06)
        return BLEManager.ad_field(ad_type, uuid_bytes)

    @staticmethod
    def ad_service_data(uuid_bytes, data):
        return BLEManager.ad_field(BLEManager.AD_TYPE_SERVICE_DATA_16, uuid_bytes + data)

    @staticmethod
    def ad_manufacturer(company_id, data):
        payload = bytes([company_id & 0xFF, (company_id >> 8) & 0xFF]) + data
        return BLEManager.ad_field(BLEManager.AD_TYPE_MANUFACTURER, payload)

    @staticmethod
    def mac_str(addr):
        return ":".join("%02x" % b for b in addr)

    @staticmethod
    def mac_bytes(s):
        return bytes(int(part, 16) for part in s.split(":"))

    @staticmethod
    def mac_compare(a, b):
        return a == b

    @classmethod
    def start_scan(cls, duration_ms=0, interval_us=30000, window_us=30000, active=False):
        ble = cls.get_ble()
        ble.gap_scan(duration_ms, interval_us, window_us, active)
        if __debug__:
            logger.debug("BLEManager: scan started (duration=%sms)", duration_ms)

    @classmethod
    def stop_scan(cls):
        ble = cls.get_ble()
        ble.gap_scan(None)
        if __debug__:
            logger.debug("BLEManager: scan stopped")

    @classmethod
    def get_scan_results(cls):
        return list(_scan_results)

    @classmethod
    def clear_scan_results(cls):
        global _scan_results
        _scan_results = []

    @classmethod
    def add_scan_filter(cls, mac=None, name=None, service_uuid=None):
        f = {}
        if mac is not None:
            f["mac"] = mac
        if name is not None:
            f["name"] = name
        if service_uuid is not None:
            f["service_uuid"] = service_uuid
        if f:
            _scan_filters.append(f)
        if __debug__:
            logger.debug("BLEManager: scan filter added: %s", f)

    @classmethod
    def clear_scan_filters(cls):
        global _scan_filters
        _scan_filters = []
        if __debug__:
            logger.debug("BLEManager: scan filters cleared")

    @classmethod
    def start_advertising(cls, interval_us=100000, connectable=False, adv_data=None, resp_data=None, name=None, service_uuid=None):
        global _advertising
        ble = cls.get_ble()
        if adv_data is None:
            fields = []
            if name:
                fields.append((cls.AD_TYPE_COMPLETE_NAME, name.encode("utf-8")[:29]))
            if service_uuid:
                fields.append((cls.AD_TYPE_SERVICE_UUID_16_COMPLETE, service_uuid))
            if fields:
                adv_data = cls.ad_build(fields)
        ble.gap_advertise(interval_us, adv_data=adv_data, resp_data=resp_data, connectable=connectable)
        _advertising = True
        global _advertising_was_connectable
        _advertising_was_connectable = connectable
        if __debug__:
            logger.debug("BLEManager: advertising started (connectable=%s)", connectable)

    @classmethod
    def stop_advertising(cls):
        global _advertising
        ble = cls.get_ble()
        ble.gap_advertise(None)
        _advertising = False
        if __debug__:
            logger.debug("BLEManager: advertising stopped")

    @classmethod
    def is_advertising(cls):
        return _advertising

    @staticmethod
    def irq_name(event):
        return {
            1: "CENTRAL_CONNECT", 2: "CENTRAL_DISCONNECT", 3: "GATTS_WRITE",
            5: "SCAN_RESULT", 6: "SCAN_DONE",
            7: "PERIPHERAL_CONNECT", 8: "PERIPHERAL_DISCONNECT",
            9: "GATTC_SERVICE_RESULT", 10: "GATTC_SERVICE_DONE",
            11: "GATTC_CHARACTERISTIC_RESULT", 12: "GATTC_CHARACTERISTIC_DONE",
            15: "GATTC_READ_RESULT", 17: "GATTC_WRITE_DONE", 18: "GATTC_NOTIFY",
            21: "MTU_EXCHANGED",
        }.get(event, "UNKNOWN(%d)" % event)

    @classmethod
    def create_gatt_server(cls):
        global _gatt_server
        if _gatt_server is not None:
            return _gatt_server
        _gatt_server = GattServer()
        return _gatt_server

    @classmethod
    def get_gatt_server(cls):
        return _gatt_server

    @classmethod
    def create_gatt_client(cls):
        client = GattClient()
        _gatt_clients[id(client)] = client
        return client

    @classmethod
    def suspend(cls, owner_tag):
        global _owner_tag, _owner_state
        _owner_tag = owner_tag
        _owner_state = {
            "advertising": _advertising,
            "scan_results": list(_scan_results),
            "scan_filters": list(_scan_filters),
        }
        if __debug__:
            logger.debug("BLEManager: suspended by %s", owner_tag)

    @classmethod
    def resume(cls, owner_tag):
        global _owner_tag, _owner_state
        if _owner_tag != owner_tag:
            if __debug__:
                logger.debug("BLEManager: resume tag mismatch %s != %s", owner_tag, _owner_tag)
            return
        if _owner_state and _owner_state["advertising"]:
            cls.start_advertising()
        _owner_tag = None
        _owner_state = None
        if __debug__:
            logger.debug("BLEManager: resumed by %s", owner_tag)


_FLAG_READ = 0x0002
_FLAG_WRITE = 0x0008
_FLAG_NOTIFY = 0x0010


class GattServer:
    def __init__(self):
        self._ble = BLEManager.get_ble()
        self._handles = {}
        self._service_defs = []
        self._registered = False
        self._mtu_set = False
        self._write_cb = None
        self._read_cb = None

    def add_service(self, uuid, characteristics, owner_tag=None):
        if self._registered:
            raise RuntimeError("GattServer: services already registered")
        svc = (uuid, tuple(characteristics))
        cb = owner_tag
        self._service_defs.append((svc, cb))

    def register(self):
        if self._registered:
            return
        if not self._service_defs:
            return
        self._probe_and_heal()
        if self._registered:
            return
        svcs = tuple(s[0] for s in self._service_defs)
        handles = self._ble.gatts_register_services(svcs)
        if isinstance(handles[0], int):
            handles = (handles,)
        for i, (_, cb) in enumerate(self._service_defs):
            if callable(cb):
                cb(handles[i])
        self._registered = True
        if __debug__:
            logger.debug("GattServer: registered %d services", len(self._service_defs))

    def _probe_and_heal(self):
        if not self._registered:
            return
        heal = False
        try:
            self._ble.gatts_write(self._handles.get("_probe", 0xFFFF), b"\x00")
        except Exception:
            heal = True
        if heal:
            if __debug__:
                logger.debug("GattServer: stale handles, re-registering")
            self._on_radio_off()
            self._registered = False

    def _on_radio_off(self):
        self._handles = {}
        self._registered = False
        self._mtu_set = False

    def set_probe_handle(self, handle):
        self._handles["_probe"] = handle

    def on_write(self, callback):
        self._write_cb = callback

    def on_read(self, callback):
        self._read_cb = callback

    def _handle_write(self, conn_handle, value_handle, value):
        if self._write_cb:
            self._write_cb(conn_handle, value_handle, value)

    def read(self, value_handle):
        return self._ble.gatts_read(value_handle)

    def write(self, value_handle, data, response=False):
        self._ble.gatts_write(value_handle, data)

    def notify(self, conn_handle, value_handle, data):
        self._ble.gatts_notify(conn_handle, value_handle, data)


class GattClient:
    _IDLE = 0
    _CONNECTING = 1
    _DISCOVERING = 2
    _WRITING = 4

    def __init__(self):
        self._ble = BLEManager.get_ble()
        self._state = self._IDLE
        self._conn_handle = None
        self._svc_start = None
        self._svc_end = None
        self._value_handle = None
        self._busy = False
        self._deadline = 0
        self.target_service_uuid = None
        self.target_char_uuid = None
        self.on_service_done = None
        self.on_char_done = None
        self.on_write_done = None
        self.addr = None
        self.addr_type = None
        _irq_handlers.append(self._irq)

    def __del__(self):
        if self._irq in _irq_handlers:
            _irq_handlers.remove(self._irq)

    def _irq(self, event, data):
        if event == BLEManager.IRQ_PERIPHERAL_CONNECT:
            self._conn_handle, _, _ = data
        elif event == BLEManager.IRQ_PERIPHERAL_DISCONNECT:
            self._reset()
        elif event == BLEManager.IRQ_GATTC_SERVICE_RESULT:
            conn_handle, start, end, uuid = data
            if self.target_service_uuid is None or uuid == self.target_service_uuid:
                self._svc_start = start
                self._svc_end = end
        elif event == BLEManager.IRQ_GATTC_CHARACTERISTIC_RESULT:
            conn_handle, def_handle, value_handle, props, uuid = data
            if self.target_char_uuid is None or uuid == self.target_char_uuid:
                self._value_handle = value_handle
        elif event == BLEManager.IRQ_GATTC_SERVICE_DONE:
            self._state = self._DISCOVERING
            if self.on_service_done and self._svc_start:
                self.on_service_done(self)
            elif self._svc_start:
                self.discover_characteristics(self._svc_start, self._svc_end)
        elif event == BLEManager.IRQ_GATTC_CHARACTERISTIC_DONE:
            if self.on_char_done and self._value_handle:
                self.on_char_done(self)
        elif event == BLEManager.IRQ_GATTC_WRITE_DONE:
            self._state = self._IDLE
            if self.on_write_done:
                self.on_write_done(self)

    def connect(self, addr_type, addr):
        self._state = self._CONNECTING
        self._busy = True
        self._deadline = _ticks_add(_ticks_ms(), 10000)
        self._ble.gap_connect(addr_type, addr)

    def disconnect(self):
        if self._conn_handle is not None:
            self._ble.gap_disconnect(self._conn_handle)
        self._reset()

    def discover_services(self):
        if self._conn_handle is None:
            self._reset()
            return
        self._state = self._DISCOVERING
        self._ble.gattc_discover_services(self._conn_handle)

    def discover_characteristics(self, start_handle, end_handle):
        if self._conn_handle is None:
            self._reset()
            return
        self._ble.gattc_discover_characteristics(self._conn_handle, start_handle, end_handle)

    def read(self, value_handle):
        return self._ble.gattc_read(self._conn_handle, value_handle)

    def write(self, value_handle, data, response=True):
        mode = 1 if response else 0
        self._state = self._WRITING
        self._ble.gattc_write(self._conn_handle, value_handle, data, mode)

    @property
    def is_connected(self):
        return self._conn_handle is not None

    @property
    def is_busy(self):
        if self._busy and self._deadline and _ticks_diff(_ticks_ms(), self._deadline) < 0:
            self._reset()
        return self._busy

    def _reset(self):
        self._state = self._IDLE
        self._conn_handle = None
        self._svc_start = None
        self._svc_end = None
        self._value_handle = None
        self._busy = False
        self._deadline = 0


def _ticks_ms():
    try:
        import time
        return time.ticks_ms()
    except Exception:
        import time as _t
        return _t.time() * 1000


def _ticks_add(a, b):
    try:
        import time
        return time.ticks_add(a, b)
    except Exception:
        return a + b


def _ticks_diff(a, b):
    try:
        import time
        return time.ticks_diff(a, b)
    except Exception:
        return a - b
