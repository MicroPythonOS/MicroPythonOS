"""
Initial author: https://github.com/jedie
https://docs.micropython.org/en/latest/library/bluetooth.html
"""

import time

import sys

import lvgl as lv
from micropython import const
from mpos import Activity, TaskManager

try:
    import bluetooth
except ImportError:  # Linux test runner / desktop may not provide bluetooth module
    bluetooth = None
    from mpos.testing.mocks import MockBluetooth

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

# Column layout: key, title, width percentage
_COLUMNS = (
    ("pos", "#", 8),
    ("mac", "MAC", 26),
    ("rssi", "RSSI", 13),
    ("last", "Last", 13),
    ("count", "Cnt", 10),
    ("name", "Name", 30),
)


def decode_name(payload: bytes) -> str | None:
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
            print("Unsupported: field_type=%s with length=%s" % (field_type, length))
        i += length + 1


class ScanBluetooth(Activity):
    def onCreate(self):
        self.simulation_mode = bluetooth is None
        if self.simulation_mode:
            ble_module = MockBluetooth()
        else:
            ble_module = bluetooth
        self.ble = ble_module.BLE()

        main_content = lv.obj()
        main_content.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        main_content.set_style_pad_all(5, 0)
        main_content.set_size(lv.pct(100), lv.pct(100))

        info_column = lv.obj(main_content)
        info_column.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        info_column.set_style_pad_all(2, 0)
        info_column.set_size(lv.pct(100), lv.SIZE_CONTENT)

        self.info_label = lv.label(info_column)
        self.info_label.set_style_text_font(lv.font_montserrat_14, 0)
        if self.simulation_mode:
            self.info("Bluetooth simulation mode")
        else:
            self.info("Bluetooth ready")

        header_row = lv.obj(main_content)
        header_row.set_flex_flow(lv.FLEX_FLOW.ROW)
        header_row.set_style_pad_all(2, 0)
        header_row.set_style_pad_gap(4, 0)
        header_row.set_size(lv.pct(100), lv.SIZE_CONTENT)
        self._create_header(header_row)

        self.rows_container = lv.obj(main_content)
        self.rows_container.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        self.rows_container.set_style_flex_grow(1, 0)
        self.rows_container.set_style_pad_all(2, 0)
        self.rows_container.set_style_pad_gap(2, 0)
        self.rows_container.set_size(lv.pct(100), lv.SIZE_CONTENT)
        self.rows_container.add_flag(lv.obj.FLAG.SCROLLABLE)

        self.scan_count = 0
        self.scanning = False
        self.mac2column = {}
        self.mac2counts = {}
        self.mac2name = {}
        self.mac2last_seen = {}
        self.row_widgets = {}

        self.setContentView(main_content)

    def _create_header(self, parent):
        for key, title, width in _COLUMNS:
            label = lv.label(parent)
            label.set_text(title)
            label.set_size(lv.pct(width), lv.SIZE_CONTENT)
            label.set_style_text_font(lv.font_montserrat_12, 0)

    def _get_or_create_row(self, addr):
        labels = self.row_widgets.get(addr)
        if labels:
            return labels
        row = lv.obj(self.rows_container)
        row.set_flex_flow(lv.FLEX_FLOW.ROW)
        row.set_style_pad_all(2, 0)
        row.set_style_pad_gap(4, 0)
        row.set_size(lv.pct(100), lv.SIZE_CONTENT)
        labels = {}
        for key, title, width in _COLUMNS:
            label = lv.label(row)
            label.set_text("")
            label.set_size(lv.pct(width), lv.SIZE_CONTENT)
            label.set_style_text_font(lv.font_montserrat_12, 0)
            labels[key] = label
        self.row_widgets[addr] = labels
        return labels

    def info(self, text):
        print(text)
        if self.simulation_mode:
            text = "Simulation mode\n%s" % text
        self.info_label.set_text(text)

    async def ble_scan(self):
        """Check sensor every second"""
        while self.scanning:
            print("async scan for %sms..." % SCAN_DURATION_MS)
            self.ble.gap_scan(SCAN_DURATION_MS, INTERVAL_US, WINDOW_US, True)
            await TaskManager.sleep_ms(SCAN_DURATION_MS + 500)

    def onResume(self, screen):
        super().onResume(screen)

        self.info("Activating Bluetooth...")
        self.ble.irq(self.ble_irq_handler)
        self.ble.active(True)

        self.scanning = True
        TaskManager.create_task(self.ble_scan())

    def onPause(self, screen):
        super().onPause(screen)

        self.scanning = False

        self.info("Stop scanning...")
        self.ble.gap_scan(None)
        self.info("Deactivating BLE...")
        self.ble.active(False)
        self.info("BLE deactivated")

    def update_last_seen(self):
        current_time = int(time.time())
        for addr, last_seen in self.mac2last_seen.items():
            last_seen_sec = int(current_time - last_seen)
            labels = self.row_widgets.get(addr)
            if labels:
                labels["last"].set_text("%ss" % last_seen_sec)

    def ble_irq_handler(self, event: int, data: tuple) -> None:
        try:
            if event == _IRQ_SCAN_RESULT:
                addr_type, addr, adv_type, rssi, adv_data = data
                addr = ":".join("%02x" % b for b in addr)
                print("addr=%s rssi=%s len(adv_data)=%s" % (addr, rssi, len(adv_data)))
                self.mac2last_seen[addr] = int(time.time())
                if name := decode_name(adv_data):
                    self.mac2name[addr] = name
                else:
                    name = self.mac2name.get(addr, "Unknown")

                if not (column_index := self.mac2column.get(addr)):
                    column_index = len(self.mac2column) + 1
                    self.mac2column[addr] = column_index
                    self.mac2counts[addr] = 1
                else:
                    self.mac2counts[addr] += 1

                labels = self._get_or_create_row(addr)
                labels["pos"].set_text(str(column_index))
                labels["mac"].set_text(addr)
                labels["rssi"].set_text("%s dBm" % rssi)
                labels["last"].set_text("0s")
                labels["count"].set_text(str(self.mac2counts[addr]))
                labels["name"].set_text(name)
            elif event == _IRQ_SCAN_DONE:
                self.update_last_seen()
                self.scan_count += 1
                self.info(
                    "%s unique devices (Scan %s)" % (len(self.mac2column), self.scan_count)
                )
            else:
                print("Ignored BLE event=%s" % event)
        except Exception as e:
            sys.print_exception(e)
            print("Error in BLE IRQ handler event=%s: %s" % (event, e))
