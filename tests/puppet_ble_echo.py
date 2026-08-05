"""
Puppet BLE beacon for on-device testing of BLEManager.

Deploy to a secondary ESP32S3 (no USB during test). This device
advertises continuously as "BLE-Puppet" with a known 16-bit service UUID.

Deploy with: mpremote cp tests/puppet_ble_echo.py :puppet_ble_echo.py
Run on boot: add `import puppet_ble_echo` to the secondary device's main.py

Phase 2 will add GATT echo characteristic (write value → notify back).
"""

import bluetooth
import time

PUPPET_NAME = b"BLE-Puppet"
SERVICE_UUID = b"\x12\x34"

IRQ_SCAN_RESULT = const(5)
IRQ_SCAN_DONE = const(6)

_AD_TYPE_SHORT_NAME = 0x08
_AD_TYPE_SERVICE_UUID_16_COMPLETE = 0x03


def _build_adv():
    payload = bytearray()
    payload.append(len(SERVICE_UUID) + 1)
    payload.append(_AD_TYPE_SERVICE_UUID_16_COMPLETE)
    payload.extend(SERVICE_UUID)
    payload.append(len(PUPPET_NAME) + 1)
    payload.append(_AD_TYPE_SHORT_NAME)
    payload.extend(PUPPET_NAME)
    return bytes(payload)


def main():
    ble = bluetooth.BLE()
    ble.active(True)
    print("Puppet: advertising as '%s'" % PUPPET_NAME.decode())
    ble.gap_advertise(100000, adv_data=_build_adv(), connectable=False)

    while True:
        time.sleep(60000)


main()
