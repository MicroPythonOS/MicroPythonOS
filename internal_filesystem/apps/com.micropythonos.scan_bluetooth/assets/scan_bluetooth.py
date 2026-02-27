"""
Initial author: https://github.com/jedie
https://docs.micropython.org/en/latest/library/bluetooth.html
"""

try:
    import bluetooth
except ImportError:  # Linux test runner may not provide bluetooth module
    bluetooth = None

import sys

import lvgl as lv
from micropython import const
from mpos import Activity, TaskManager

# Scan for 5 seconds,
SCAN_DURATION_MS = const(5000)  # Duration of each BLE scan in milliseconds
# with very low interval/window (to maximize detection rate):
INTERVAL_US = const(30000)
WINDOW_US = const(30000)

_IRQ_SCAN_RESULT = const(5)
_IRQ_SCAN_DONE = const(6)

# BLE Advertising Data Types (Standardized by Bluetooth SIG)
_ADV_TYPE_SHORT_NAME = const(8)
_ADV_TYPE_NAME = const(9)


def decode_name(payload: bytes) -> str:
    i = 0
    payload_len = len(payload)
    while i < payload_len:
        length = payload[i]
        if length == 0 or i + length >= payload_len:
            break
        field_type = payload[i + 1]
        if field_type in (_ADV_TYPE_SHORT_NAME, _ADV_TYPE_NAME):
            if new_name := payload[i + 2 : i + length + 1]:
                return str(new_name, "utf-8")
        else:
            print(f"Unsupported: {field_type=} with {length=}")
        i += length + 1
    return "Unknown"


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
    def onCreate(self):
        main_content = lv.obj()
        main_content.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        main_content.set_style_pad_all(0, 0)
        main_content.set_size(lv.pct(100), lv.pct(100))

        info_column = lv.obj(main_content)
        info_column.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        info_column.set_style_pad_all(1, 1)
        info_column.set_size(lv.pct(100), lv.SIZE_CONTENT)

        self.info_label = lv.label(info_column)
        self.info_label.set_style_text_font(lv.font_montserrat_14, 0)

        if bluetooth is None:
            self.info("Bluetooth not available on this platform")
            self.setContentView(main_content)
            return

        tabel_column = lv.obj(main_content)
        tabel_column.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        tabel_column.set_style_pad_all(0, 0)
        tabel_column.set_size(lv.pct(100), lv.SIZE_CONTENT)

        self.table = lv.table(tabel_column)
        set_cell_value(
            self.table,
            row=0,
            values=("pos", "MAC", "RSSI", "count", "Name"),
        )
        set_dynamic_column_widths(self.table)

        self.scan_count = 0
        self.mac2column = {}
        self.mac2counts = {}

        self.ble = bluetooth.BLE()

        self.setContentView(main_content)

    def info(self, text):
        print(text)
        self.info_label.set_text(text)

    async def ble_scan(self):
        """Check sensor every second"""
        while self.scanning:
            print(f"async scan for {SCAN_DURATION_MS}ms...")
            self.ble.gap_scan(SCAN_DURATION_MS, INTERVAL_US, WINDOW_US, True)
            await TaskManager.sleep_ms(SCAN_DURATION_MS + 100)

    def onResume(self, screen):
        super().onResume(screen)
        if bluetooth is None:
            return

        self.info("Activating Bluetooth...")
        self.ble.irq(self.ble_irq_handler)
        self.ble.active(True)

        self.scanning = True
        TaskManager.create_task(self.ble_scan())

    def onPause(self, screen):
        super().onPause(screen)
        if bluetooth is None:
            return

        self.scanning = False

        self.info("Stop scanning...")
        self.ble.gap_scan(None)
        self.info("Deactivating BLE...")
        self.ble.active(False)
        self.info("BLE deactivated")

    def ble_irq_handler(self, event: int, data: tuple) -> None:
        try:
            if event == _IRQ_SCAN_RESULT:
                addr_type, addr, adv_type, rssi, adv_data = data
                addr = ":".join(f"{b:02x}" for b in addr)
                print(f"{addr=} {rssi=} {len(adv_data)=}")
                name = decode_name(adv_data)

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
            elif event == _IRQ_SCAN_DONE:
                set_dynamic_column_widths(self.table)
                self.scan_count += 1
                self.info(
                    f"{len(self.mac2column)} unique devices (Scan {self.scan_count})"
                )
            else:
                print(f"Ignored BLE {event=}")
        except Exception as e:
            sys.print_exception(e)
            print(f"Error in BLE IRQ handler {event=}: {e}")
