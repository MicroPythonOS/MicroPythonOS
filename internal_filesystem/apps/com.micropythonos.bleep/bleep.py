import json
import logging
import time

import lvgl as lv
from micropython import const
from mpos import Activity, DisplayMetrics, Intent, SettingActivity, SharedPreferences, TaskManager

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

try:
    import bluetooth as _bt
except ImportError:
    _bt = None
    from mpos.testing.mocks import MockBluetooth, _encode_bleep_advertisement

_BLEEP_ADV_UUID = const(0xB1E3)
_BLEEP_GATT_SVC_VAL = 0xB2E4
_BLEEP_GATT_CHAR_VAL = 0xB2E5

SCAN_DURATION_MS = const(5000)

_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)
_IRQ_SCAN_RESULT = const(5)
_IRQ_SCAN_DONE = const(6)
_IRQ_PERIPHERAL_CONNECT = const(7)
_IRQ_PERIPHERAL_DISCONNECT = const(8)
_IRQ_GATTC_SERVICE_RESULT = const(9)
_IRQ_GATTC_SERVICE_DONE = const(10)
_IRQ_GATTC_CHARACTERISTIC_RESULT = const(11)
_IRQ_GATTC_CHARACTERISTIC_DONE = const(12)
_IRQ_GATTC_WRITE_DONE = const(17)

_FLAG_WRITE = const(0x0008)
_FLAG_WRITE_NO_RESPONSE = const(0x0004)

_ADV_TYPE_COMPLETE_UUID_16 = const(0x03)
_ADV_TYPE_SVC_DATA_16 = const(0x16)
_ADV_TYPE_SHORT_NAME = const(0x08)

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

_GATT_IDLE = const(0)
_GATT_CONNECTING = const(1)
_GATT_DISCOVERING = const(2)
_GATT_CHAR_DISCOVERING = const(3)
_GATT_WRITING = const(4)

_ble = None
_simulation_mode = False
_devices = {}
_friends = {}
_queue = {}
_nickname = ""
_own_mac = "00:00:00:00:00:00"
_scanning = False
_msg_handle = None
_gatt_connections = {}
_prefs = None

_gatt_state = _GATT_IDLE
_gatt_conn_handle = None
_gatt_target_addr = None
_gatt_target_addr_type = None
_gatt_start_handle = None
_gatt_end_handle = None
_gatt_value_handle = None

_list_refresh = None


def _random_nickname():
    return "Happy%d" % (time.ticks_ms() % 900 + 100)


def _decode_field(data, field_type):
    i = 0
    end = len(data)
    while i < end:
        length = data[i]
        if length == 0 or i + length >= end:
            break
        if data[i + 1] == field_type:
            return data[i + 2:i + length + 1]
        i += length + 1
    return None


def _mac_str(addr_bytes):
    return ":".join("%02x" % b for b in addr_bytes)


def _mac_bytes(addr_str):
    return bytes(int(b, 16) for b in addr_str.split(":"))


def _uuid(val):
    if _simulation_mode or _bt is None:
        return val
    return _bt.UUID(val)


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
        del _queue[addr]
        _save_queue()


def _is_bleep_device(adv_data):
    svc_data = _decode_field(adv_data, _ADV_TYPE_COMPLETE_UUID_16)
    if svc_data and len(svc_data) >= 2:
        uuid = svc_data[0] | (svc_data[1] << 8)
        return uuid == _BLEEP_ADV_UUID
    return False


def _decode_adv_friend_count(adv_data):
    svc_data = _decode_field(adv_data, _ADV_TYPE_SVC_DATA_16)
    if svc_data and len(svc_data) >= 3:
        uuid = svc_data[0] | (svc_data[1] << 8)
        if uuid == _BLEEP_ADV_UUID:
            return svc_data[2]
    return 0


def _decode_adv_nickname(adv_data):
    name_data = _decode_field(adv_data, _ADV_TYPE_SHORT_NAME)
    if name_data:
        return str(name_data, "utf-8")
    return "Unknown"


def _build_adv_data():
    payload = bytearray()
    payload.append(3)
    payload.append(_ADV_TYPE_COMPLETE_UUID_16)
    payload.append(_BLEEP_ADV_UUID & 0xFF)
    payload.append((_BLEEP_ADV_UUID >> 8) & 0xFF)
    payload.append(4)
    payload.append(_ADV_TYPE_SVC_DATA_16)
    payload.append(_BLEEP_ADV_UUID & 0xFF)
    payload.append((_BLEEP_ADV_UUID >> 8) & 0xFF)
    payload.append(len(_friends) & 0xFF)
    nickname_bytes = bytes(_nickname, "utf-8")
    max_name = 31 - len(payload) - 2
    if len(nickname_bytes) > max_name:
        nickname_bytes = nickname_bytes[:max_name]
    payload.append(len(nickname_bytes) + 1)
    payload.append(_ADV_TYPE_SHORT_NAME)
    payload.extend(nickname_bytes)
    return bytes(payload)


def _start_advertising():
    adv_data = _build_adv_data()
    if __debug__: logger.debug("_start_advertising: len=%s", len(adv_data))
    _ble.gap_advertise(100000, adv_data=adv_data)


def _stop_advertising():
    _ble.gap_advertise(None)


def _init_gatt_server():
    global _msg_handle
    svc_uuid = _uuid(_BLEEP_GATT_SVC_VAL)
    char_uuid = _uuid(_BLEEP_GATT_CHAR_VAL)
    svc = (svc_uuid, ((char_uuid, _FLAG_WRITE),))
    ((_msg_handle,),) = _ble.gatts_register_services((svc,))
    if not _simulation_mode and _bt is not None:
        _ble.gatts_set_buffer(_msg_handle, 128, False)
    if __debug__: logger.debug("_init_gatt_server: msg_handle=%s", _msg_handle)


def _process_incoming_message(sender_addr, msg):
    t = msg.get("t", "")
    if __debug__: logger.debug("_process_incoming: from=%s msg=%s", sender_addr, t)
    old_rel = _devices.get(sender_addr, {}).get("relation_state", _REL_STRANGER)

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


def _ble_irq_handler(event, data):
    try:
        if event == _IRQ_SCAN_RESULT:
            _on_scan_result(data)
        elif event == _IRQ_SCAN_DONE:
            _on_scan_done()
        elif event == _IRQ_CENTRAL_CONNECT:
            _on_central_connect(data)
        elif event == _IRQ_CENTRAL_DISCONNECT:
            _on_central_disconnect(data)
        elif event == _IRQ_GATTS_WRITE:
            _on_gatts_write(data)
        elif event == _IRQ_PERIPHERAL_CONNECT:
            _on_client_connect(data)
        elif event == _IRQ_PERIPHERAL_DISCONNECT:
            _on_client_disconnect(data)
        elif event == _IRQ_GATTC_SERVICE_RESULT:
            _on_service_result(data)
        elif event == _IRQ_GATTC_SERVICE_DONE:
            _on_service_done(data)
        elif event == _IRQ_GATTC_CHARACTERISTIC_RESULT:
            _on_char_result(data)
        elif event == _IRQ_GATTC_CHARACTERISTIC_DONE:
            _on_char_done(data)
        elif event == _IRQ_GATTC_WRITE_DONE:
            _on_write_done(data)
    except Exception as e:
        logger.error("BLE IRQ error: %s", e)


def _on_scan_result(data):
    addr_type, addr, adv_type, rssi, adv_data = data
    addr_str = _mac_str(addr)
    if __debug__: logger.debug("scan_result: %s rssi=%s", addr_str, rssi)
    if not _is_bleep_device(adv_data):
        return
    friend_count = _decode_adv_friend_count(adv_data)
    nickname = _decode_adv_nickname(adv_data)
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
    if __debug__: logger.debug("scan_done: %s devices", len(_devices))
    if _list_refresh:
        _list_refresh()
    _process_gatt_queue()


def _on_central_connect(data):
    conn_handle, addr_type, addr = data
    _gatt_connections[conn_handle] = (addr_type, bytes(addr))
    if __debug__: logger.debug("central_connect: conn=%s addr=%s", conn_handle, _mac_str(addr))


def _on_central_disconnect(data):
    conn_handle, addr_type, addr = data
    _gatt_connections.pop(conn_handle, None)
    if __debug__: logger.debug("central_disconnect: conn=%s", conn_handle)
    _start_advertising()


def _on_gatts_write(data):
    conn_handle, value_handle = data
    if conn_handle not in _gatt_connections:
        return
    if value_handle != _msg_handle:
        return
    _, addr_bytes = _gatt_connections[conn_handle]
    addr = _mac_str(addr_bytes)
    msg_data = _ble.gatts_read(_msg_handle)
    if __debug__: logger.debug("gatts_write: from=%s data=%s", addr, msg_data)
    try:
        msg = json.loads(msg_data)
    except Exception:
        logger.error("invalid gatt message: %s", msg_data)
        return
    _process_incoming_message(addr, msg)


def _on_client_connect(data):
    global _gatt_state, _gatt_conn_handle
    conn_handle, addr_type, addr = data
    addr_str = _mac_str(addr)
    if addr_str != _mac_str(_gatt_target_addr):
        return
    _gatt_conn_handle = conn_handle
    _gatt_state = _GATT_DISCOVERING
    if __debug__: logger.debug("client_connect: conn=%s addr=%s", conn_handle, addr_str)
    _ble.gattc_discover_services(_gatt_conn_handle)


def _on_client_disconnect(data):
    global _gatt_state, _gatt_conn_handle, _gatt_start_handle, _gatt_end_handle, _gatt_value_handle
    conn_handle, _, _ = data
    if conn_handle == _gatt_conn_handle:
        if __debug__: logger.debug("client_disconnect: conn=%s", conn_handle)
        _gatt_state = _GATT_IDLE
        _gatt_conn_handle = None
        _gatt_start_handle = None
        _gatt_end_handle = None
        _gatt_value_handle = None
        _start_advertising()
        _process_gatt_queue()


def _on_service_result(data):
    global _gatt_start_handle, _gatt_end_handle
    conn_handle, start_handle, end_handle, uuid = data
    if conn_handle == _gatt_conn_handle and uuid == _BLEEP_GATT_SVC_VAL:
        if __debug__: logger.debug("service_result: start=%s end=%s", start_handle, end_handle)
        _gatt_start_handle = start_handle
        _gatt_end_handle = end_handle


def _on_service_done(data):
    if _gatt_start_handle and _gatt_end_handle:
        _ble.gattc_discover_characteristics(_gatt_conn_handle, _gatt_start_handle, _gatt_end_handle)
    else:
        logger.error("GATT service not found")
        _ble.gap_disconnect(_gatt_conn_handle)


def _on_char_result(data):
    global _gatt_value_handle
    conn_handle, def_handle, value_handle, properties, uuid = data
    if conn_handle == _gatt_conn_handle and uuid == _BLEEP_GATT_CHAR_VAL:
        if __debug__: logger.debug("char_result: value_handle=%s", value_handle)
        _gatt_value_handle = value_handle


def _on_char_done(data):
    global _gatt_state
    if _gatt_value_handle:
        _gatt_state = _GATT_WRITING
        target_addr_str = _mac_str(_gatt_target_addr)
        if target_addr_str not in _queue or not _queue[target_addr_str]:
            _ble.gap_disconnect(_gatt_conn_handle)
            return
        msg = _queue[target_addr_str][0]
        msg_json = json.dumps(msg)
        if __debug__: logger.debug("char_done: writing msg=%s", msg_json)
        _ble.gattc_write(_gatt_conn_handle, _gatt_value_handle, msg_json, 1)
    else:
        logger.error("GATT characteristic not found")
        _ble.gap_disconnect(_gatt_conn_handle)


def _on_write_done(data):
    global _gatt_state
    conn_handle, value_handle, status = data
    if conn_handle != _gatt_conn_handle:
        return
    if __debug__: logger.debug("write_done: status=%s", status)
    target_addr_str = _mac_str(_gatt_target_addr)
    if target_addr_str in _queue and _queue[target_addr_str]:
        _queue[target_addr_str].pop(0)
        if not _queue[target_addr_str]:
            del _queue[target_addr_str]
        _save_queue()
    _ble.gap_disconnect(_gatt_conn_handle)


def _process_gatt_queue():
    global _gatt_state, _gatt_target_addr, _gatt_target_addr_type
    if _gatt_state != _GATT_IDLE:
        return
    for addr_str, msgs in list(_queue.items()):
        if not msgs:
            continue
        if addr_str not in _devices:
            continue
        _gatt_state = _GATT_CONNECTING
        _gatt_target_addr = _mac_bytes(addr_str)
        _gatt_target_addr_type = _devices[addr_str]["addr_type"]
        if __debug__: logger.debug("_process_gatt_queue: connecting to %s msgs=%s", addr_str, len(msgs))
        _ble.gap_connect(_gatt_target_addr_type, _gatt_target_addr)
        return


async def _ble_scan_loop():
    global _scanning
    while _scanning:
        if __debug__: logger.debug("_ble_scan_loop: starting scan")
        _ble.gap_scan(SCAN_DURATION_MS, 30000, 30000, True)
        await TaskManager.sleep_ms(SCAN_DURATION_MS + 500)


def _ble_init():
    global _ble, _simulation_mode, _scanning, _prefs
    _prefs = SharedPreferences("com.micropythonos.bleep")
    _simulation_mode = _bt is None
    if _simulation_mode:
        bleep_results = [
            (0, b"\x11\x22\x33\x44\x55\x01", 0, -42, _encode_bleep_advertisement(5, "HappyCamper")),
            (0, b"\x11\x22\x33\x44\x55\x02", 0, -55, _encode_bleep_advertisement(3, "SunnyDay")),
            (0, b"\x11\x22\x33\x44\x55\x03", 0, -68, _encode_bleep_advertisement(7, "BraveFox")),
        ]
        _ble = MockBluetooth(scan_results=bleep_results).BLE()
    else:
        _ble = _bt.BLE()
    _load_friends()
    _load_queue()
    _ble.irq(_ble_irq_handler)
    _ble.active(True)
    _init_gatt_server()
    _scanning = True
    _start_advertising()
    TaskManager.create_task(_ble_scan_loop())
    if __debug__: logger.debug("_ble_init: started, simulation=%s friends=%s queue=%s", _simulation_mode, len(_friends), len(_queue))


def _ble_deinit():
    global _scanning
    _scanning = False
    _ble.gap_scan(None)
    _stop_advertising()
    _ble.active(False)


class BLEepDetail(Activity):

    def onCreate(self):
        self.addr = self.intent.getStringExtra("addr")
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
        if rel == _REL_STRANGER:
            if self.addr in _devices:
                _devices[self.addr]["relation_state"] = _REL_OUTGOING_REQUEST
            _queue_message(self.addr, _MSG_FR)
            _process_gatt_queue()
        elif rel == _REL_OUTGOING_REQUEST:
            if self.addr in _devices:
                _devices[self.addr]["relation_state"] = _REL_STRANGER
            _queue_message(self.addr, _MSG_FC)
            _dequeue_messages(self.addr)
            _process_gatt_queue()
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

        _ble_init()

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

        _, mac_bytes = _ble.config("mac")
        global _own_mac
        _own_mac = _mac_str(mac_bytes)

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
        self.setContentView(screen)

    def onResume(self, screen):
        super().onResume(screen)
        global _list_refresh
        _list_refresh = self._refresh_list
        nickname_saved = self.prefs.get_string("nickname", None)
        if nickname_saved:
            global _nickname
            _nickname = nickname_saved
        if len(_gatt_connections):
            _ble.irq(_ble_irq_handler)
        self._refresh_list()

    def onPause(self, screen):
        super().onPause(screen)
        global _list_refresh
        _list_refresh = None

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
        self.info_label.set_text(
            "Nickname: %s  |  Friends: %s  |  Queued: %s" % (_nickname, len(_friends), sum(len(v) for v in _queue.values()))
        )
        items = list(_devices.items())
        items.sort(key=lambda x: x[1]["rssi"], reverse=True)
        parent = self.device_list.get_parent()
        old = self.device_list
        self.device_list = lv.list(parent)
        self.device_list.set_size(lv.pct(100), lv.pct(75))
        for addr, info in items:
            rel = info["relation_state"]
            prefix = _REL_LABELS.get(rel, "")
            text = "%s%s %s dBm  F:%s" % (prefix, info["nickname"], info["rssi"], info["friend_count"])
            btn = self.device_list.add_button(None, text)
            btn.add_event_cb(lambda e, a=addr: self._open_detail(a), lv.EVENT.CLICKED, None)
        old.delete()

    def _open_detail(self, addr):
        intent = Intent(activity_class=BLEepDetail)
        intent.putExtra("addr", addr)
        self.startActivity(intent)
