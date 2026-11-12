# BLEManager Implementation Plans

## Phase 1: Core Framework (Current)

**Goal:** Radio lifecycle, IRQ helpers, AD utilities, MAC helpers, advertising, scanning.

**Deliverables:**
- `lib/mpos/ble_manager.py` — BLEManager class (~350-400 lines)
- `lib/mpos/__init__.py` — add import + `__all__` entry
- Adapt `scan_bluetooth.py` to use BLEManager as proof-of-concept
- `tests/test_ble_manager.py` — mock-based unit tests
- `tests/puppet_ble_echo.py` — puppet script for on-device testing (deploy to 2nd ESP32S3)
- `tests/test_graphical_ble_manager_device.py` — on-device test (test_runner.py --ondevice)

**API surface:**

```
# Radio lifecycle
BLEManager.get_ble()           → BLE() or MockBLE() (auto-detects desktop)
BLEManager.activate() / deactivate()
BLEManager.is_available() / is_active()

# IRQ constants
BLEManager.IRQ_SCAN_RESULT = const(5)
BLEManager.IRQ_SCAN_DONE = const(6)
# ... all 13 constants

# IRQ management
BLEManager.register_irq(handler)

# AD utilities
BLEManager.ad_parse(adv_data)           → {type: bytes}
BLEManager.ad_field(ad_type, data)      → bytes
BLEManager.ad_build(fields)             → bytes (31-byte capped)
BLEManager.ad_build_scan_resp(fields)   → bytes
BLEManager.ad_name(name, short=False)   → 0x08/0x09 payload
BLEManager.ad_service_uuid(uuid)        → 0x02/0x03 payload
BLEManager.ad_service_data(uuid, data)  → 0x16 payload
BLEManager.ad_manufacturer(id, data)    → 0xFF payload

# MAC utilities
BLEManager.mac_str(addr) / mac_bytes(s) / mac_compare(a, b)

# Advertising
BLEManager.start_advertising(*, interval_us=100000, connectable=False,
                             adv_data=None, resp_data=None, name=None, service_uuid=None)
BLEManager.stop_advertising() / is_advertising()

# Scanning
BLEManager.start_scan(*, duration_ms=0, interval_us=30000, window_us=30000,
                      active=False)
BLEManager.stop_scan()
BLEManager.get_scan_results()           → [ScanResult]
BLEManager.clear_scan_results()
BLEManager.add_scan_filter(mac=None, name=None, service_uuid=None) / clear_scan_filters()

# Simulation (test helpers)
BLEManager.Simulation.inject_scan_result(addr, rssi, adv_data)
BLEManager.Simulation.reset()
```

---

## Phase 2: GATT

**Goal:** GATT server/client classes, cooperative radio ownership.

**Deliverables:**
- `GattServer` class in `ble_manager.py`
- `GattClient` class in `ble_manager.py`
- `suspend()`/`resume()` cooperative ownership
- `on_advertise_restart` callback (auto re-advertise on disconnect)
- `re_register_on_handle_poison` (self-heal stale GATT handles)
- Adapt `BLEep` to use BLEManager + GattClient/GattServer
- Update puppet script with echo characteristic
- Full on-device GATT tests (connect/discover/read/write/echo/disconnect)

**API surface:**

```python
class GattServer:
    def add_service(self, uuid, characteristics)
    def register(self)
    def read(self, handle) → bytes
    def write(self, handle, data, response=False)
    def notify(self, conn_handle, handle, data)
    def indicate(self, conn_handle, handle, data)
    def on_write(self, callback)    # (conn_handle, handle, value) → None
    def on_read(self, callback)     # (conn_handle, handle) → bytes

class GattClient:
    def connect(self, addr_type, addr) → conn_handle
    def disconnect(self)
    def discover_services(self)
    def discover_characteristics(self, start_handle, end_handle)
    def read(self, handle) → bytes
    def write(self, handle, data, response=True)
    def on_connect(self, callback)
    def on_disconnect(self, callback)
    def on_services_discovered(self, callback)
    def on_chars_discovered(self, callback)
    @property
    def is_connected(self) → bool

BLEManager.create_gatt_server() / get_gatt_server()
BLEManager.create_gatt_client(addr_type, addr)
BLEManager.suspend(owner_tag) / resume(owner_tag)
BLEManager.register_owner(tag) / unregister_owner(tag)
```

---

## Phase 3: HID / Text Input Relay

**Goal:** Phone-as-keyboard feature from fri3d-friends issue #3.

**Deliverables:**
- `register_hid_keyboard()` / `send_hid_report()` / `unregister_hid_keyboard()`
- `register_text_input_service(name)` with `on_text_input(callback)`
- Integration into `MposKeyboard` — any text field becomes phone-fillable

**Trigger:** When the `fri3d-friends#3` "pair with smartphone" feature ships.

---

## Phase 4: Port Remaining Apps

**Goal:** All existing BLE apps use the framework.

**Deliverables:**
- [x] Port `BLEep` (794 → ~400 lines, -200+ lines of raw BLE code)
- [ ] Port `fri3d-friends` (proximity, exchange, setup, beacon) to BLEManager
- [ ] `BluetoothService` base class for background beacon services

---

## Non-Goals (YAGNI)

- **No mesh networking.** NimBLE doesn't ship mesh support.
- **No Bluetooth Classic (RFCOMM/SPP).** ESP32 NimBLE is BLE only.
- **No persistent pairing.** NimBLE has no bond storage on ESP32.
- **No connection parameter negotiation at manager level.** Apps call `ble.config()` directly.
- **No file transfer protocol.** Build on top of GattClient/GattServer if needed.
