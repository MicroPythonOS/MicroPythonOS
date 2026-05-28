import lvgl as lv
import keypad_framework

import mpos.ui
import mpos.ui.focus_direction


_MOD_LSHIFT = 0x02
_MOD_RSHIFT = 0x20
_MOD_SHIFT = _MOD_LSHIFT | _MOD_RSHIFT


_SHIFT_DIGITS = {
    0x1E: "!",
    0x1F: "@",
    0x20: "#",
    0x21: "$",
    0x22: "%",
    0x23: "^",
    0x24: "&",
    0x25: "*",
    0x26: "(",
    0x27: ")",
}


_PUNCT = {
    0x2D: ("-", "_"),
    0x2E: ("=", "+"),
    0x2F: ("[", "{"),
    0x30: ("]", "}"),
    0x31: ("\\", "|"),
    0x33: (";", ":"),
    0x34: ("'", '"'),
    0x35: ("`", "~"),
    0x36: (",", "<"),
    0x37: (".", ">"),
    0x38: ("/", "?"),
}


_SPECIAL = {
    0x28: lv.KEY.ENTER,
    0x29: lv.KEY.ESC,
    0x2A: getattr(lv.KEY, "BACKSPACE", 8),
    0x2B: lv.KEY.NEXT,
    0x2C: ord(" "),
    0x4A: lv.KEY.HOME,
    0x4B: getattr(lv.KEY, "PAGE_UP", lv.KEY.PREV),
    0x4C: getattr(lv.KEY, "DEL", 127),
    0x4D: lv.KEY.END,
    0x4E: getattr(lv.KEY, "PAGE_DOWN", lv.KEY.NEXT),
    0x4F: lv.KEY.RIGHT,
    0x50: lv.KEY.LEFT,
    0x51: lv.KEY.DOWN,
    0x52: lv.KEY.UP,
}


class Fri3dCommunicatorKeyboard(keypad_framework.KeypadDriver):
    """LVGL keypad indev for Fri3d communicator HID key reports.

    Works with both Communicator2024 and Communicator2026, as long as the
    object exposes a `key_report` property returning an 8-byte USB HID
    keyboard report tuple:

      (modifier, reserved, key1, key2, key3, key4, key5, key6)
    """

    def __init__(self, communicator):
        super().__init__()
        self._communicator = communicator
        self._prev_keys = []
        self._active_lv_by_hid = {}
        self._queue = []

    def _fire_mpos_nav_hook(self, state, key):
        if state != self.PRESSED:
            return
        if key == lv.KEY.ESC:
            mpos.ui.back_screen()
        elif key == lv.KEY.RIGHT:
            mpos.ui.focus_direction.move_focus_direction(90)
        elif key == lv.KEY.LEFT:
            mpos.ui.focus_direction.move_focus_direction(270)
        elif key == lv.KEY.UP:
            mpos.ui.focus_direction.move_focus_direction(0)
        elif key == lv.KEY.DOWN:
            mpos.ui.focus_direction.move_focus_direction(180)

    def _hid_to_lv(self, hid_usage, modifiers):
        shifted = (modifiers & _MOD_SHIFT) != 0

        if 0x04 <= hid_usage <= 0x1D:
            ch = chr(ord("a") + hid_usage - 0x04)
            if shifted:
                ch = ch.upper()
            return ord(ch)

        if 0x1E <= hid_usage <= 0x27:
            if shifted:
                return ord(_SHIFT_DIGITS[hid_usage])
            return ord(chr(ord("1") + hid_usage - 0x1E)) if hid_usage != 0x27 else ord("0")

        punct = _PUNCT.get(hid_usage)
        if punct is not None:
            return ord(punct[1] if shifted else punct[0])

        return _SPECIAL.get(hid_usage)

    def _poll(self):
        report = self._communicator.key_report
        if report is None or len(report) < 8:
            return

        modifiers = report[0]
        curr_keys = [k for k in report[2:8] if k]

        for hid_usage in curr_keys:
            if hid_usage in self._prev_keys:
                continue
            lv_key = self._hid_to_lv(hid_usage, modifiers)
            if lv_key is None:
                continue
            self._active_lv_by_hid[hid_usage] = lv_key
            self._queue.append((self.PRESSED, lv_key))

        for hid_usage in self._prev_keys:
            if hid_usage in curr_keys:
                continue
            lv_key = self._active_lv_by_hid.pop(hid_usage, None)
            if lv_key is None:
                continue
            self._queue.append((self.RELEASED, lv_key))

        self._prev_keys = curr_keys

    def _get_key(self):
        self._poll()
        if self._queue:
            state, key = self._queue.pop(0)
            self._fire_mpos_nav_hook(state, key)
            return state, key

        return None
