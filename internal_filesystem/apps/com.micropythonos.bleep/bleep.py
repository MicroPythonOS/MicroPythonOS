import logging
import random
import lvgl as lv
from micropython import const
from mpos import Activity, DisplayMetrics, Intent, SettingActivity, SharedPreferences, TaskManager

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

try:
    import bluetooth
except ImportError:
    bluetooth = None
    from mpos.testing.mocks import MockBluetooth, _encode_bleep_advertisement

_BLEEP_SVC_UUID = const(0xB1E3)
SCAN_DURATION_MS = const(5000)

_IRQ_SCAN_RESULT = const(5)
_IRQ_SCAN_DONE = const(6)

_ADV_TYPE_COMPLETE_UUID_16 = const(0x03)
_ADV_TYPE_SVC_DATA_16 = const(0x16)
_ADV_TYPE_SHORT_NAME = const(0x08)
_ADV_TYPE_COMPLETE_NAME = const(0x09)


def _random_nickname():
    adjectives = ("Happy", "Sunny", "Brave", "Swift", "Cool", "Jolly", "Fuzzy", "Zippy")
    adj = adjectives[random.randint(0, len(adjectives) - 1)]
    num = random.randint(100, 999)
    return "%s%s" % (adj, num)


def _decode_field(adv_data, field_type):
    i = 0
    end = len(adv_data)
    while i < end:
        length = adv_data[i]
        if length == 0 or i + length >= end:
            break
        ftype = adv_data[i + 1]
        if ftype == field_type:
            return adv_data[i + 2 : i + length + 1]
        i += length + 1
    return None


class BLEep(Activity):

    def onCreate(self):
        self.simulation_mode = bluetooth is None
        if __debug__: logger.debug("onCreate: simulation_mode=%s", self.simulation_mode)
        self.prefs = SharedPreferences(self.appFullName)
        self.friend_count = 0
        self.own_mac = "00:00:00:00:00:00"
        self.devices = {}

        if self.simulation_mode:
            bleep_results = [
                (0, b"\x11\x22\x33\x44\x55\x01", 0, -42, _encode_bleep_advertisement(5, "HappyCamper")),
                (0, b"\x11\x22\x33\x44\x55\x02", 0, -55, _encode_bleep_advertisement(3, "SunnyDay")),
                (0, b"\x11\x22\x33\x44\x55\x03", 0, -68, _encode_bleep_advertisement(7, "BraveFox")),
            ]
            ble_module = MockBluetooth(scan_results=bleep_results)
        else:
            ble_module = bluetooth
        self.ble = ble_module.BLE()

        self.nickname = self.prefs.get_string("nickname", None)
        if not self.nickname:
            self.nickname = _random_nickname()
            if __debug__: logger.debug("onCreate: generated random nickname=%s", self.nickname)
            editor = self.prefs.edit()
            editor.put_string("nickname", self.nickname)
            editor.commit()
        else:
            if __debug__: logger.debug("onCreate: loaded nickname=%s", self.nickname)

        screen = lv.obj()
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        pad = DisplayMetrics.pct_of_width(2)
        screen.set_style_pad_all(pad, 0)
        screen.set_style_pad_gap(DisplayMetrics.pct_of_width(1), 0)

        header = lv.obj(screen)
        header.set_size(lv.pct(100), lv.SIZE_CONTENT)
        header.set_flex_flow(lv.FLEX_FLOW.ROW)
        header.set_flex_align(lv.FLEX_ALIGN.SPACE_BETWEEN, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)

        self.mac_label = lv.label(header)
        self.mac_label.set_text("MAC: %s" % self.own_mac)

        gear_btn = lv.button(header)
        gear_btn.set_size(DisplayMetrics.pct_of_width(10), DisplayMetrics.pct_of_width(10))
        gear_btn.add_event_cb(self._open_settings, lv.EVENT.CLICKED, None)
        gear_label = lv.label(gear_btn)
        gear_label.set_text(lv.SYMBOL.SETTINGS)
        gear_label.center()

        self.friend_label = lv.label(screen)
        self._update_friend_label()

        friend_btn = lv.button(screen)
        friend_btn.set_size(lv.pct(100), DisplayMetrics.pct_of_height(8))
        friend_btn.add_event_cb(self._on_befriend, lv.EVENT.CLICKED, None)
        friend_btn_label = lv.label(friend_btn)
        friend_btn_label.set_text("Befriend!")
        friend_btn_label.center()

        self.device_list = lv.list(screen)
        self.device_list.set_size(lv.pct(100), lv.pct(75))

        self.setContentView(screen)

    def onResume(self, screen):
        super().onResume(screen)
        self.nickname = self.prefs.get_string("nickname", self.nickname)
        if __debug__: logger.debug("onResume: nickname=%s friend_count=%s", self.nickname, self.friend_count)
        self._update_friend_label()

        self.ble.irq(self._ble_irq_handler)
        self.ble.active(True)
        if __debug__: logger.debug("onResume: BLE activated")

        if not self.simulation_mode:
            _, mac_bytes = self.ble.config("mac")
            self.own_mac = ":".join("%02x" % b for b in mac_bytes)
        else:
            _, mac_bytes = self.ble.config("mac")
            self.own_mac = ":".join("%02x" % b for b in mac_bytes)
        self.mac_label.set_text("MAC: %s" % self.own_mac)
        if __debug__: logger.debug("onResume: own_mac=%s", self.own_mac)

        self._start_advertising()
        self._scanning = True
        TaskManager.create_task(self._ble_scan_loop())

    def onPause(self, screen):
        super().onPause(screen)
        if __debug__: logger.debug("onPause: stopping scan and advertising")
        self._scanning = False
        self.ble.gap_scan(None)
        self._stop_advertising()
        self.ble.active(False)
        if __debug__: logger.debug("onPause: BLE deactivated")

    def update_ui_threadsafe_if_foreground(self, func, *args, **kwargs):
        super().update_ui_threadsafe_if_foreground(func, *args, **kwargs)

    def _update_friend_label(self):
        self.friend_label.set_text("Nickname: %s  |  Friends: %s" % (self.nickname, self.friend_count))

    def _open_settings(self, event):
        setting = {
            "title": "Nickname",
            "key": "nickname",
            "default_value": _random_nickname(),
            "placeholder": "Enter your nickname",
        }
        intent = Intent(activity_class=SettingActivity)
        intent.putExtra("setting", setting)
        intent.putExtra("prefs", self.prefs)
        self.startActivity(intent)

    def _on_befriend(self, event):
        self.friend_count += 1
        if __debug__: logger.debug("_on_befriend: friend_count=%s", self.friend_count)
        self._update_friend_label()
        self._start_advertising()

    def _build_adv_data(self):
        payload = bytearray()
        payload.append(3)
        payload.append(0x03)
        payload.append(0xE3)
        payload.append(0xB1)
        payload.append(4)
        payload.append(0x16)
        payload.append(0xE3)
        payload.append(0xB1)
        payload.append(self.friend_count & 0xFF)
        nickname_bytes = bytes(self.nickname, "utf-8")
        max_name = 31 - len(payload) - 2
        if len(nickname_bytes) > max_name:
            nickname_bytes = nickname_bytes[:max_name]
        payload.append(len(nickname_bytes) + 1)
        payload.append(0x08)
        payload.extend(nickname_bytes)
        return bytes(payload)

    def _start_advertising(self):
        adv_data = self._build_adv_data()
        if __debug__: logger.debug("_start_advertising: len=%s hex=%s", len(adv_data), adv_data.hex() if hasattr(adv_data, "hex") else "..")
        self.ble.gap_advertise(100000, adv_data=adv_data)

    def _stop_advertising(self):
        if __debug__: logger.debug("_stop_advertising")
        self.ble.gap_advertise(None)

    async def _ble_scan_loop(self):
        while self._scanning:
            if __debug__: logger.debug("_ble_scan_loop: starting scan duration=%sms", SCAN_DURATION_MS)
            self.devices.clear()
            self.ble.gap_scan(SCAN_DURATION_MS, 30000, 30000, True)
            await TaskManager.sleep_ms(SCAN_DURATION_MS + 500)

    def _ble_irq_handler(self, event, data):
        try:
            if event == _IRQ_SCAN_RESULT:
                addr_type, addr, adv_type, rssi, adv_data = data
                addr = ":".join("%02x" % b for b in addr)
                if __debug__: logger.debug("_ble_irq: SCAN_RESULT addr=%s rssi=%s adv_len=%s", addr, rssi, len(adv_data))
                if not self._is_bleep_device(adv_data):
                    return
                friend_count = self._decode_friend_count(adv_data)
                nickname = self._decode_nickname(adv_data)
                if __debug__: logger.debug("_ble_irq: BLEep device addr=%s rssi=%s friends=%s nickname=%s", addr, rssi, friend_count, nickname)
                if addr not in self.devices or rssi > self.devices[addr]["rssi"]:
                    self.devices[addr] = {"rssi": rssi, "friends": friend_count, "nickname": nickname}
            elif event == _IRQ_SCAN_DONE:
                if __debug__: logger.debug("_ble_irq: SCAN_DONE, refreshing list with %s devices", len(self.devices))
                self._refresh_device_list()
        except Exception as e:
            logger.error("BLE IRQ error: %s", e)

    def _is_bleep_device(self, adv_data):
        svc_data = _decode_field(adv_data, _ADV_TYPE_COMPLETE_UUID_16)
        if svc_data and len(svc_data) >= 2:
            uuid = svc_data[0] | (svc_data[1] << 8)
            return uuid == _BLEEP_SVC_UUID
        return False

    def _decode_friend_count(self, adv_data):
        svc_data = _decode_field(adv_data, _ADV_TYPE_SVC_DATA_16)
        if svc_data and len(svc_data) >= 3:
            uuid = svc_data[0] | (svc_data[1] << 8)
            if uuid == _BLEEP_SVC_UUID:
                return svc_data[2]
        return 0

    def _decode_nickname(self, adv_data):
        name_data = _decode_field(adv_data, _ADV_TYPE_SHORT_NAME)
        if not name_data:
            name_data = _decode_field(adv_data, _ADV_TYPE_COMPLETE_NAME)
        if name_data:
            return str(name_data, "utf-8")
        return "Unknown"

    def _refresh_device_list(self):
        items = list(self.devices.items())
        items.sort(key=lambda x: x[1]["rssi"], reverse=True)
        if __debug__: logger.debug("_refresh_device_list: %s devices sorted by rssi", len(items))
        parent = self.device_list.get_parent()
        old_list = self.device_list
        self.device_list = lv.list(parent)
        self.device_list.set_size(lv.pct(100), lv.pct(75))
        for addr, info in items:
            text = "%s  %s  %s dBm  F:%s" % (info["nickname"], addr, info["rssi"], info["friends"])
            if __debug__: logger.debug("_refresh_device_list: item %s", text)
            self.device_list.add_button(None, text)
        old_list.delete()
