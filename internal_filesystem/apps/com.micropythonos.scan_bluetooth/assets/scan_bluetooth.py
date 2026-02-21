"""
Initial author: https://github.com/jedie
https://docs.micropython.org/en/latest/library/bluetooth.html
"""

import time

try:
    import bluetooth
except ImportError:  # Linux test runner may not provide bluetooth module
    bluetooth = None

import lvgl as lv
from micropython import const
from mpos import Activity

SCAN_DURATION = const(1000)  # Duration of each BLE scan in milliseconds
_IRQ_SCAN_RESULT = const(5)


# BLE Advertising Data Types (Standardized by Bluetooth SIG)
_ADV_TYPE_NAME = const(0x09)


def decode_field(payload: bytes, adv_type: int) -> list:
    results = []
    i = 0
    payload_len = len(payload)
    while i < payload_len:
        length = payload[i]
        if length == 0 or i + length >= payload_len:
            break
        field_type = payload[i + 1]
        if field_type == adv_type:
            results.append(payload[i + 2 : i + length + 1])
        i += length + 1
    return results


class BluetoothScanner:
    def __init__(self, device_callback):
        if bluetooth is None:
            raise RuntimeError("Bluetooth module not available")
        self.device_callback = device_callback
        self.ble = bluetooth.BLE()
        self.ble.irq(self.ble_irq_handler)

    def __enter__(self):
        print("Activating BLE")
        self.ble.active(True)
        return self

    def ble_irq_handler(self, event: int, data: tuple) -> None:
        if event == _IRQ_SCAN_RESULT:
            addr_type, addr, adv_type, rssi, adv_data = data
            addr = ":".join(f"{b:02x}" for b in addr)
            names = decode_field(adv_data, _ADV_TYPE_NAME)
            name = str(names[0], "utf-8") if names else "Unknown"
            self.device_callback(addr, rssi, name)

    def scan(self, duration_ms: int):
        print(f"BLE scanning for {duration_ms}ms...")
        self.ble.gap_scan(duration_ms, 20000, 10000)

    def __exit__(self, exc_type, exc_val, exc_tb):
        print("Deactivating BLE")
        self.ble.active(False)


def set_dynamic_column_widths(table, font=None, padding=8):
    font = font or lv.font_montserrat_14
    for col in range(table.get_column_count()):
        max_width = 0
        for row in range(table.get_row_count()):
            value = table.get_cell_value(row, col)
            width = lv.text_get_width(value, len(value), font, lv.TEXT_FLAG.NONE)
            if width > max_width:
                max_width = width
        table.set_column_width(col, max_width + padding)


def set_cell_value(table, *, row: int, values: tuple):
    for col, value in enumerate(values):
        table.set_cell_value(row, col, value)


class ScanBluetooth(Activity):
    refresh_timer = None

    def onCreate(self):
        screen = lv.obj()
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        screen.set_style_pad_all(0, 0)
        screen.set_size(lv.pct(100), lv.pct(100))

        if bluetooth is None:
            label = lv.label(screen)
            label.set_text("Bluetooth not available on this platform")
            label.center()
            self.setContentView(screen)
            return

        self.table = lv.table(screen)
        set_cell_value(
            self.table,
            row=0,
            values=("pos", "MAC", "RSSI", "count", "Name"),
        )
        set_dynamic_column_widths(self.table)

        self.mac2column = {}
        self.mac2counts = {}

        self.scanner_cm = BluetoothScanner(device_callback=self.scan_callback)
        self.scanner = self.scanner_cm.__enter__()  # Activate BLE

        self.setContentView(screen)

    def scan_callback(self, addr, rssi, name):
        if not (column_index := self.mac2column.get(addr)):
            column_index = len(self.mac2column) + 1
            self.mac2column[addr] = column_index
            self.mac2counts[addr] = 1
        else:
            self.mac2counts[addr] += 1

        set_cell_value(
            self.table,
            row=column_index,
            values=(
                str(column_index),
                addr,
                f"{rssi} dBm",
                str(self.mac2counts[addr]),
                name,
            ),
        )

    def onResume(self, screen):
        super().onResume(screen)
        if bluetooth is None:
            return

        def update(timer):
            self.scanner.scan(SCAN_DURATION)
            set_dynamic_column_widths(self.table)
            time.sleep_ms(SCAN_DURATION + 100)  # Wait ?
            print(f"Scan complete: {len(self.mac2column)} unique devices")

        self.refresh_timer = lv.timer_create(update, SCAN_DURATION + 1000, None)

    def onPause(self, screen):
        super().onPause(screen)
        if bluetooth is None:
            return
        self.scanner.__exit__(None, None, None)  # Deactivate BLE
        if self.refresh_timer:
            self.refresh_timer.delete()
            self.refresh_timer = None
