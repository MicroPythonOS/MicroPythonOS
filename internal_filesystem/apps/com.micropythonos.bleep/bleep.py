import json
import logging
import time

import lvgl as lv
from micropython import const
from mpos import Activity, BLEManager, DisplayMetrics, Intent, SettingActivity, SharedPreferences, TaskManager

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

_BLEEP_ADV_UUID = const(0xB1E3)
_BLEEP_GATT_SVC_VAL = 0xB2E4
_BLEEP_GATT_CHAR_VAL = 0xB2E5

SCAN_DURATION_MS = const(10000)

_REL_STRANGER = const(0)
_REL_OUTGOING_REQUEST = const(1)
_REL_INCOMING_REQUEST = const(2)
_REL_FRIEND = const(3)

_REL_LABELS = {
    _REL_STRANGER: "",
    _REL_OUTGOING_REQUEST: "req...",
    _REL_INCOMING_REQUEST: "friend?",
    _REL_FRIEND: "Friend: ",
}

_MSG_FR = "fr"
_MSG_FC = "fc"
_MSG_FA = "fa"
_MSG_FD = "fd"
_MSG_UF = "uf"

_devices = {}
_friends = {}
_queue = {}
_nickname = ""
_own_mac = "00:00:00:00:00:00"
_scanning = False
_gatt_connections = {}
_prefs = None

_list_refresh = None
_info_refresh = None
_scan_start_ticks = 0


def _random_nickname():
    return "Happy%d" % (time.ticks_ms() % 900 + 100)


def _load_friends():
    global _friends, _prefs
    if _prefs is None:
        _prefs = SharedPreferences("com.micropythonos.bleep")
    try:
        data = _prefs.get_string("friends", "{}")
        _friends = json.loads(data)
    except Exception:
        _friends = {}


def _save_friends():
    global _prefs
    if _prefs is None:
        _prefs = SharedPreferences("com.micropythonos.bleep")
    editor = _prefs.edit()
    editor.put_string("friends", json.dumps(_friends))
    editor.commit()


def _load_queue():
    global _queue, _prefs
    if _prefs is None:
        _prefs = SharedPreferences("com.micropythonos.bleep")
    try:
        data = _prefs.get_string("msg_queue", "{}")
        _queue = json.loads(data)
    except Exception:
        _queue = {}


def _save_queue():
    global _prefs
    if _prefs is None:
        _prefs = SharedPreferences("com.micropythonos.bleep")
    editor = _prefs.edit()
    editor.put_string("msg_queue", json.dumps(_queue))
    editor.commit()


def _queue_message(addr, msg_type):
    if addr not in _queue:
        _queue[addr] = []
    _queue[addr].append({"t": msg_type})
    _save_queue()
    if __debug__: logger.debug("_queue_message: %s -> %s", addr, msg_type)


def _dequeue_messages(addr):
    if addr in _queue:
        if __debug__: logger.debug("_dequeue_messages: cleared %s msgs for %s", len(_queue[addr]), addr)
        del _queue[addr]
        _save_queue()


def _process_incoming_message(sender_addr, msg):
    t = msg.get("t", "")
    old_rel = _devices.get(sender_addr, {}).get("relation_state", _REL_STRANGER)
    if __debug__: logger.debug("_process_incoming: from=%s msg=%s old_rel=%s", sender_addr, t, old_rel)

    if t == _MSG_FR:
        if old_rel == _REL_OUTGOING_REQUEST:
            _friends[sender_addr] = {"nickname": _devices[sender_addr].get("nickname", "Unknown"), "since": time.time()}
            _save_friends()
            if sender_addr in _devices:
                _devices[sender_addr]["relation_state"] = _REL_FRIEND
            if __debug__: logger.debug("  mutual friend: %s", sender_addr)
        elif old_rel == _REL_STRANGER:
            if sender_addr in _devices:
                _devices[sender_addr]["relation_state"] = _REL_INCOMING_REQUEST
            if __debug__: logger.debug("  incoming request: %s", sender_addr)
    elif t == _MSG_FC:
        if old_rel == _REL_INCOMING_REQUEST or (sender_addr in _devices and _devices[sender_addr]["relation_state"] == _REL_STRANGER):
            if sender_addr in _devices:
                _devices[sender_addr]["relation_state"] = _REL_STRANGER
    elif t == _MSG_FA:
        _friends[sender_addr] = {"nickname": _devices.get(sender_addr, {}).get("nickname", "Unknown"), "since": time.time()}
        _save_friends()
        if sender_addr in _devices:
            _devices[sender_addr]["relation_state"] = _REL_FRIEND
        if __debug__: logger.debug("  accepted: %s", sender_addr)
    elif t == _MSG_FD:
        if sender_addr in _devices:
            _devices[sender_addr]["relation_state"] = _REL_STRANGER
    elif t == _MSG_UF:
        _friends.pop(sender_addr, None)
        _save_friends()
        if sender_addr in _devices:
            _devices[sender_addr]["relation_state"] = _REL_STRANGER
        if __debug__: logger.debug("  unfriended: %s", sender_addr)


def _on_scan_result(data):
    addr_type, addr, adv_type, rssi, adv_data = data
    addr_str = BLEManager.mac_str(addr)
    parsed = BLEManager.ad_parse(adv_data)
    friend_count_raw = parsed.get(BLEManager.AD_TYPE_SERVICE_DATA_16, b"\x00\x00")
    friend_count = friend_count_raw[2] if len(friend_count_raw) >= 3 else 0
    nickname_bytes = parsed.get(BLEManager.AD_TYPE_SHORT_NAME, b"Unknown")
    nickname = str(nickname_bytes, "utf-8") if nickname_bytes else "Unknown"
    if nickname == "Unknown":
        return
    old = _devices.get(addr_str, {})
    rel = old.get("relation_state", _REL_STRANGER)
    if addr_str in _friends and rel != _REL_FRIEND:
        rel = _REL_FRIEND
    if addr_str not in _devices or rssi > old.get("rssi", -999):
        _devices[addr_str] = {
            "rssi": rssi,
            "nickname": nickname,
            "friend_count": friend_count,
            "addr_type": addr_type,
            "relation_state": rel,
            "last_seen": time.ticks_ms(),
        }
        if __debug__: logger.debug("  BLEep: %s friends=%s name=%s rel=%s", addr_str, friend_count, nickname, rel)
    _process_gatt_queue()


def _on_scan_done():
    cutoff = _scan_start_ticks - 3 * (SCAN_DURATION_MS + 500)
    stale = [a for a, d in _devices.items() if d.get("last_seen", 0) < cutoff]
    for a in stale:
        del _devices[a]
    if __debug__: logger.debug("scan_done: %s devices (%s removed, cutoff=%s)", len(_devices), len(stale), cutoff)
    if _list_refresh:
        _list_refresh()
    _process_gatt_queue()


def _on_central_connect(data):
    conn_handle, addr_type, addr = data
    _gatt_connections[conn_handle] = (addr_type, bytes(addr))
    if __debug__: logger.debug("central_connect: conn=%s addr=%s", conn_handle, BLEManager.mac_str(addr))


def _on_central_disconnect(data):
    conn_handle, addr_type, addr = data
    _gatt_connections.pop(conn_handle, None)
    if __debug__: logger.debug("central_disconnect: conn=%s", conn_handle)


def _on_gatts_write(conn_handle, value_handle, value):
    if __debug__: logger.debug("gatts_write: conn=%s", conn_handle)
    _, addr_bytes = _gatt_connections.get(conn_handle, (None, None))
    if addr_bytes is None:
        return
    addr = BLEManager.mac_str(addr_bytes)
    try:
        msg = json.loads(value)
    except Exception:
        logger.error("invalid gatt message: %s", value)
        return
    _process_incoming_message(addr, msg)


def _on_gatt_client_write_done(client):
    target_addr_str = client.gatt_target_addr_str
    if __debug__: logger.debug("write_done: to=%s queue_was=%s", target_addr_str, len(_queue.get(target_addr_str, [])))
    if target_addr_str in _queue and _queue[target_addr_str]:
        _queue[target_addr_str].pop(0)
        if not _queue[target_addr_str]:
            del _queue[target_addr_str]
        _save_queue()
    client.disconnect()
    if _info_refresh:
        _info_refresh()


def _process_gatt_queue():
    for addr_str, msgs in list(_queue.items()):
        if not msgs:
            continue
        if addr_str not in _devices:
            continue
        client = BLEManager.create_gatt_client()
        client.target_service_uuid = _BLEEP_GATT_SVC_VAL
        client.target_char_uuid = _BLEEP_GATT_CHAR_VAL
        client.on_write_done = _on_gatt_client_write_done
        client.gatt_target_addr_str = addr_str
        client.addr_type = _devices[addr_str]["addr_type"]
        client.addr = BLEManager.mac_bytes(addr_str)
        if __debug__: logger.debug("_process_gatt_queue: connecting to %s msgs=%s", addr_str, len(msgs))
        msg = msgs[0]
        msg_json = json.dumps(msg)
        client._pending_write_data = msg_json
        client.connect(client.addr_type, client.addr)
        return


def _on_gatt_char_done(client):
    if client._pending_write_data and client._value_handle:
        client.write(client._value_handle, client._pending_write_data, response=True)


def _on_gatt_service_done(client):
    if client._svc_start:
        client.discover_characteristics(client._svc_start, client._svc_end)


def _build_adv_data():
    fields = [
        (BLEManager.AD_TYPE_SERVICE_UUID_16_COMPLETE, bytes([_BLEEP_ADV_UUID & 0xFF, (_BLEEP_ADV_UUID >> 8) & 0xFF])),
        (BLEManager.AD_TYPE_SERVICE_DATA_16, bytes([_BLEEP_ADV_UUID & 0xFF, (_BLEEP_ADV_UUID >> 8) & 0xFF, len(_friends) & 0xFF])),
        (BLEManager.AD_TYPE_SHORT_NAME, bytes(_nickname, "utf-8")[:29]),
    ]
    return BLEManager.ad_build(fields)


async def _ble_scan_loop():
    global _scanning, _scan_start_ticks
    while _scanning:
        if __debug__: logger.debug("_ble_scan_loop: starting scan")
        _scan_start_ticks = time.ticks_ms()
        BLEManager.start_scan(SCAN_DURATION_MS, 30000, 30000, True)
        await TaskManager.sleep_ms(SCAN_DURATION_MS + 500)


def _ble_init():
    global _scanning, _prefs
    _prefs = SharedPreferences("com.micropythonos.bleep")
    _load_friends()
    _load_queue()

    BLEManager.activate()
    BLEManager.register_irq(_ble_irq_handler)
    BLEManager.add_scan_filter(service_uuid=bytes([_BLEEP_ADV_UUID & 0xFF, (_BLEEP_ADV_UUID >> 8) & 0xFF]))

    gatt_server = BLEManager.create_gatt_server()
    gatt_server.add_service(_BLEEP_GATT_SVC_VAL, [(_BLEEP_GATT_CHAR_VAL, 0x0008)])
    gatt_server.on_write(_on_gatts_write)
    gatt_server.register()

    _scanning = True
    BLEManager.start_advertising(adv_data=_build_adv_data())
    TaskManager.create_task(_ble_scan_loop())
    if __debug__: logger.debug("_ble_init: started, simulation=%s friends=%s queue=%s", BLEManager.is_simulation(), len(_friends), len(_queue))


def _ble_deinit():
    global _scanning
    if __debug__: logger.debug("_ble_deinit")
    _scanning = False
    BLEManager.stop_scan()
    BLEManager.stop_advertising()
    BLEManager.deactivate()
    BLEManager.clear_scan_filters()
    _devices.clear()
    _gatt_connections.clear()


def _ble_irq_handler(event, data):
    if event == BLEManager.IRQ_SCAN_RESULT:
        _on_scan_result(data)
    elif event == BLEManager.IRQ_SCAN_DONE:
        _on_scan_done()
    elif event == BLEManager.IRQ_CENTRAL_CONNECT:
        _on_central_connect(data)
    elif event == BLEManager.IRQ_CENTRAL_DISCONNECT:
        _on_central_disconnect(data)


class BLEepDetail(Activity):

    def onCreate(self):
        self.addr = self.intent.extras.get("addr") if self.intent else None
        info = _devices.get(self.addr, {"nickname": "?", "rssi": 0, "friend_count": 0})
        self._info = info

        screen = lv.obj()
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        pad = DisplayMetrics.pct_of_width(2)
        screen.set_style_pad_all(pad, 0)
        screen.set_style_pad_gap(DisplayMetrics.pct_of_width(1), 0)

        header = lv.obj(screen)
        header.set_size(lv.pct(100), lv.SIZE_CONTENT)
        header.set_flex_flow(lv.FLEX_FLOW.ROW)
        header.set_flex_align(lv.FLEX_ALIGN.SPACE_BETWEEN, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)

        title = lv.label(header)
        title.set_text("Detail")
        back_btn = lv.button(header)
        back_btn.set_size(DisplayMetrics.pct_of_width(20), DisplayMetrics.pct_of_width(10))
        back_btn.add_event_cb(lambda e: self.finish(), lv.EVENT.CLICKED, None)
        back_lbl = lv.label(back_btn)
        back_lbl.set_text(lv.SYMBOL.LEFT + " Back")
        back_lbl.center()

        self._nick_label = lv.label(screen)
        self._nick_label.set_text("Nickname: %s" % info.get("nickname", "?"))

        self._mac_label = lv.label(screen)
        self._mac_label.set_text("MAC: %s" % self.addr)

        self._friends_label = lv.label(screen)
        self._friends_label.set_text("Friends: %s" % info.get("friend_count", 0))

        rssi_label = lv.label(screen)
        rssi_label.set_text("RSSI: %s dBm" % info.get("rssi", 0))

        self._action_btn = lv.button(screen)
        self._action_btn.set_size(lv.pct(80), DisplayMetrics.pct_of_height(8))
        self._action_btn.add_event_cb(self._on_action, lv.EVENT.CLICKED, None)
        self._action_btn_label = lv.label(self._action_btn)
        self._action_btn_label.center()

        self._action2_btn = lv.button(screen)
        self._action2_btn.set_size(lv.pct(80), DisplayMetrics.pct_of_height(8))
        self._action2_btn.add_event_cb(self._on_action2, lv.EVENT.CLICKED, None)
        self._action2_btn_label = lv.label(self._action2_btn)
        self._action2_btn_label.center()
        self._action2_btn.add_flag(lv.obj.FLAG.HIDDEN)

        self._update_buttons()
        self._timer = lv.timer_create(lambda t: self._update_buttons(), 1000, None)
        self.setContentView(screen)

    def onPause(self, screen):
        super().onPause(screen)
        if self._timer:
            self._timer.delete()
            self._timer = None

    def _update_buttons(self):
        if self.addr not in _devices:
            return
        info = _devices[self.addr]
        rel = info["relation_state"]

        self._nick_label.set_text("Nickname: %s" % info.get("nickname", "?"))
        self._friends_label.set_text("Friends: %s" % info.get("friend_count", 0))

        self._action2_btn.add_flag(lv.obj.FLAG.HIDDEN)
        if rel == _REL_STRANGER:
            self._action_btn_label.set_text("Send Friend Request")
            self._action_btn.remove_flag(lv.obj.FLAG.HIDDEN)
        elif rel == _REL_OUTGOING_REQUEST:
            self._action_btn_label.set_text("Cancel Friend Request")
            self._action_btn.remove_flag(lv.obj.FLAG.HIDDEN)
        elif rel == _REL_INCOMING_REQUEST:
            self._action_btn_label.set_text("Accept")
            self._action_btn.remove_flag(lv.obj.FLAG.HIDDEN)
            self._action2_btn_label.set_text("Deny")
            self._action2_btn.remove_flag(lv.obj.FLAG.HIDDEN)
        elif rel == _REL_FRIEND:
            self._action_btn_label.set_text("Unfriend")
            self._action_btn.remove_flag(lv.obj.FLAG.HIDDEN)

    def _on_action(self, event):
        info = _devices.get(self.addr, {})
        rel = info.get("relation_state", _REL_STRANGER)
        if __debug__: logger.debug("_on_action: addr=%s rel=%s -> ", self.addr, rel)
        if rel == _REL_STRANGER:
            if self.addr in _devices:
                _devices[self.addr]["relation_state"] = _REL_OUTGOING_REQUEST
            _queue_message(self.addr, _MSG_FR)
            _process_gatt_queue()
        elif rel == _REL_OUTGOING_REQUEST:
            if self.addr in _devices:
                _devices[self.addr]["relation_state"] = _REL_STRANGER
            _queue_message(self.addr, _MSG_FC)
            _process_gatt_queue()
            _dequeue_messages(self.addr)
        elif rel == _REL_INCOMING_REQUEST:
            _friends[self.addr] = {"nickname": info.get("nickname", "Unknown"), "since": time.time()}
            _save_friends()
            _devices[self.addr]["relation_state"] = _REL_FRIEND
            _queue_message(self.addr, _MSG_FA)
            _process_gatt_queue()
        elif rel == _REL_FRIEND:
            _friends.pop(self.addr, None)
            _save_friends()
            _devices[self.addr]["relation_state"] = _REL_STRANGER
            _queue_message(self.addr, _MSG_UF)
            _process_gatt_queue()
        self._update_buttons()

    def _on_action2(self, event):
        if __debug__: logger.debug("_on_action2: deny %s", self.addr)
        if self.addr in _devices:
            _devices[self.addr]["relation_state"] = _REL_STRANGER
        _queue_message(self.addr, _MSG_FD)
        _process_gatt_queue()
        self._update_buttons()


class BLEep(Activity):

    def onCreate(self):
        global _list_refresh
        self.prefs = SharedPreferences(self.appFullName)
        global _prefs
        if _prefs is None:
            _prefs = self.prefs

        nickname_saved = self.prefs.get_string("nickname", None)
        if nickname_saved:
            global _nickname
            _nickname = nickname_saved
        else:
            _nickname = _random_nickname()
            editor = self.prefs.edit()
            editor.put_string("nickname", _nickname)
            editor.commit()
        if __debug__: logger.debug("onCreate: nickname=%s", _nickname)

        _ble_init()

        _, mac_bytes = BLEManager.get_ble().config("mac")
        global _own_mac
        _own_mac = BLEManager.mac_str(mac_bytes)

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
        self.mac_label.set_text("MAC: %s" % _own_mac)

        gear_btn = lv.button(header)
        gear_btn.set_size(DisplayMetrics.pct_of_width(10), DisplayMetrics.pct_of_width(10))
        gear_btn.add_event_cb(self._open_settings, lv.EVENT.CLICKED, None)
        gear_lbl = lv.label(gear_btn)
        gear_lbl.set_text(lv.SYMBOL.SETTINGS)
        gear_lbl.center()

        self.info_label = lv.label(screen)
        self.info_label.set_text(
            "Nickname: %s  |  Friends: %s  |  Queued: %s" % (_nickname, len(_friends), sum(len(v) for v in _queue.values()))
        )

        self.device_list = lv.list(screen)
        self.device_list.set_size(lv.pct(100), lv.pct(75))

        _list_refresh = self._refresh_list
        _info_refresh = self._update_info_label
        self.setContentView(screen)

    def onResume(self, screen):
        super().onResume(screen)
        global _list_refresh, _info_refresh
        _list_refresh = self._refresh_list
        _info_refresh = self._update_info_label
        nickname_saved = self.prefs.get_string("nickname", None)
        if nickname_saved:
            global _nickname
            _nickname = nickname_saved
        self._refresh_list()

    def onPause(self, screen):
        super().onPause(screen)
        global _list_refresh, _info_refresh
        _list_refresh = None
        _info_refresh = None

    def onDestroy(self, screen):
        _ble_deinit()

    def _update_info_label(self):
        self.info_label.set_text(
            "Nickname: %s  |  Friends: %s  |  Queued: %s" % (_nickname, len(_friends), sum(len(v) for v in _queue.values()))
        )

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

    def _refresh_list(self):
        self._update_info_label()
        now = time.ticks_ms()
        items = list(_devices.items())
        items.sort(key=lambda x: x[1]["rssi"], reverse=True)
        parent = self.device_list.get_parent()
        old = self.device_list
        self.device_list = lv.list(parent)
        self.device_list.set_size(lv.pct(100), lv.pct(75))
        for addr, info in items:
            rel = info["relation_state"]
            prefix = _REL_LABELS.get(rel, "")
            age_s = (now - info.get("last_seen", now)) // 1000
            age_str = "now" if age_s < 1 else ("%ss" % age_s) if age_s < 60 else ("%sm" % (age_s // 60))
            text = "%s%s %s dBm  F:%s  %s" % (prefix, info["nickname"], info["rssi"], info["friend_count"], age_str)
            btn = self.device_list.add_button(None, text)
            btn.add_event_cb(lambda e, a=addr: self._open_detail(a), lv.EVENT.CLICKED, None)
        old.delete()

    def _open_detail(self, addr):
        intent = Intent(activity_class=BLEepDetail)
        intent.putExtra("addr", addr)
        self.startActivity(intent)
