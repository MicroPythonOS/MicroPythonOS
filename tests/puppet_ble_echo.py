"""
Puppet BLE echo peripheral for on-device testing of BLEManager Phase 2.

Deploy to a secondary ESP32S3 (no USB during test). This device
advertises as "BLE-Puppet" with a known 16-bit service UUID and serves
a GATT echo characteristic: write value → notify same value back.

Deploy with: mpremote cp tests/puppet_ble_echo.py :puppet_ble_echo.py
Run on boot: add `import puppet_ble_echo` to the secondary device's main.py
"""

import bluetooth
import time
from micropython import const

IRQ_CENTRAL_CONNECT = const(1)
IRQ_CENTRAL_DISCONNECT = const(2)
IRQ_GATTS_WRITE = const(3)

FLAG_WRITE = const(0x0008)
FLAG_NOTIFY = const(0x0010)

PUPPET_NAME = b"BLE-Puppet"
SERVICE_UUID = b"\x12\x34"

_AD_TYPE_SHORT_NAME = const(0x08)
_AD_TYPE_SERVICE_UUID_16_COMPLETE = const(0x03)

_ECHO_SVC_UUID = bluetooth.UUID("12345678-1234-1234-1234-123456789ABC")
_ECHO_CHAR_UUID = bluetooth.UUID("12345678-1234-1234-1235-123456789ABC")

_ECHO_SERVICE = (
    _ECHO_SVC_UUID,
    ((_ECHO_CHAR_UUID, FLAG_WRITE | FLAG_NOTIFY),),
)


def _build_adv():
    payload = bytearray()
    payload.append(len(SERVICE_UUID) + 1)
    payload.append(_AD_TYPE_SERVICE_UUID_16_COMPLETE)
    payload.extend(SERVICE_UUID)
    payload.append(len(PUPPET_NAME) + 1)
    payload.append(_AD_TYPE_SHORT_NAME)
    payload.extend(PUPPET_NAME)
    return bytes(payload)


class EchoPeripheral:
    def __init__(self):
        self._ble = bluetooth.BLE()
        self._ble.active(True)
        self._ble.irq(self._irq)
        ((self._echo_handle,),) = self._ble.gatts_register_services((_ECHO_SERVICE,))
        self._ble.gatts_set_buffer(self._echo_handle, 128, False)
        self._connections = set()
        self._advertise()

    def _irq(self, event, data):
        if event == IRQ_CENTRAL_CONNECT:
            conn_handle, _, _ = data
            self._connections.add(conn_handle)
        elif event == IRQ_CENTRAL_DISCONNECT:
            conn_handle, _, _ = data
            self._connections.discard(conn_handle)
            self._advertise()
        elif event == IRQ_GATTS_WRITE:
            conn_handle, value_handle = data
            if value_handle == self._echo_handle:
                value = self._ble.gatts_read(value_handle)
                self._ble.gatts_notify(conn_handle, self._echo_handle, value)

    def _advertise(self):
        self._ble.gap_advertise(100000, adv_data=_build_adv(), connectable=True)


def main():
    EchoPeripheral()
    print("Puppet: advertising as '%s' (echo service active)" % PUPPET_NAME.decode())
    while True:
        time.sleep(60000)


main()
