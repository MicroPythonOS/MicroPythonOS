import lvgl as lv  # NOQA
import pointer_framework


def _to_signed(v):
    return v - 256 if v > 127 else v


def parse_boot_mouse_report(report):
    if report is None or len(report) < 3:
        return None
    buttons = report[0] & 0x07
    dx = _to_signed(report[1])
    dy = _to_signed(report[2])
    wheel = _to_signed(report[3]) if len(report) > 3 else 0
    return (buttons, dx, dy, wheel)


class ReportParser:
    kind = "generic"

    @staticmethod
    def match(subclass, protocol):
        return False

    def parse(self, report):
        return None


class BootMouseParser(ReportParser):
    kind = "mouse"

    @staticmethod
    def match(subclass, protocol):
        return subclass == 1 and protocol == 2

    def parse(self, report):
        return parse_boot_mouse_report(report)


class BootKeyboardParser(ReportParser):
    kind = "keyboard"

    @staticmethod
    def match(subclass, protocol):
        return subclass == 1 and protocol == 1


PARSERS = [BootMouseParser(), BootKeyboardParser()]


def find_parser(subclass, protocol):
    for parser in PARSERS:
        try:
            if parser.match(subclass, protocol):
                return parser
        except Exception:
            continue
    return None


class HIDSource:
    def drain(self):
        try:
            import usb_disp  # NOQA
        except ImportError:
            return []
        if not hasattr(usb_disp, "hid_drain"):
            return []
        try:
            return list(usb_disp.hid_drain())
        except Exception:
            return []


class FakeHIDSource:
    def __init__(self):
        self._reports = []

    def inject(self, addr, subclass, protocol, report):
        self._reports.append((addr, subclass, protocol, bytes(report)))

    def inject_mouse(self, buttons=0, dx=0, dy=0, wheel=0, addr=5):
        dx_b = dx & 0xFF
        dy_b = dy & 0xFF
        wheel_b = wheel & 0xFF
        self.inject(addr, 1, 2, bytes([buttons & 0x07, dx_b, dy_b, wheel_b]))

    def drain(self):
        reports, self._reports = self._reports, []
        return reports


class _IdentityCal:
    alphaX = None
    betaX = None
    deltaX = None
    alphaY = None
    betaY = None
    deltaY = None
    mirrorX = None
    mirrorY = None


_CURSOR_W = 16
_CURSOR_H = 16
_CURSOR_MAP = None


def _cursor_map():
    global _CURSOR_MAP
    if _CURSOR_MAP is None:
        px = bytearray(_CURSOR_W * _CURSOR_H * 4)
        for y in range(_CURSOR_H):
            for x in range(_CURSOR_W - y):
                if x < 2 or y < 2 or x == _CURSOR_W - 1 - y:
                    o = (y * _CURSOR_W + x) * 4
                    px[o] = 255
                    px[o + 1] = 255
                    px[o + 2] = 255
                    px[o + 3] = 255
        _CURSOR_MAP = bytes(px)
    return _CURSOR_MAP


class USBMouse(pointer_framework.PointerDriver):
    __usb_absolute__ = True

    def __init__(
        self,
        source=None,
        sensitivity=1.0,
        debug=False,
    ):
        self._source = source if source is not None else HIDSource()
        self._sensitivity = sensitivity
        super().__init__(
            touch_cal=_IdentityCal(),
            startup_rotation=pointer_framework.lv.DISPLAY_ROTATION._0,  # NOQA
            debug=debug,
        )
        self._x = self._width // 2
        self._y = self._height // 2
        self._buttons = 0
        self._cursor = None
        self._cursor_theme = None

    def _calc_coords(self, x, y):
        return (x, y)

    def _clamp(self, v, hi):
        if v < 0:
            return 0
        if v > hi:
            return hi
        return v

    def _apply_wheel(self, wheel):
        try:
            pt = lv.point_t()  # NOQA
            pt.x = self._x
            pt.y = self._y
            obj = self.search_obj(pt)
            if obj is None:
                return
            obj.scroll_by(0, -wheel * 20, lv.ANIM.OFF)  # NOQA
        except Exception:
            pass

    def _get_coords(self):
        try:
            reports = self._source.drain()
        except Exception:
            reports = []
        for item in reports:
            try:
                _, subclass, protocol, raw = item
            except Exception:
                continue
            parser = find_parser(subclass, protocol)
            if parser is None or parser.kind != "mouse":
                continue
            try:
                event = parser.parse(raw)
            except Exception:
                continue
            if event is None:
                continue
            buttons, dx, dy, wheel = event
            self._buttons = buttons
            step = self._sensitivity
            self._x = self._clamp(int(self._x + dx * step), self._width - 1)
            self._y = self._clamp(int(self._y + dy * step), self._height - 1)
            if wheel:
                self._apply_wheel(wheel)
        state = self.PRESSED if self._buttons else self.RELEASED
        self._sync_cursor_theme()
        return (state, self._x, self._y)

    def _cursor_target_theme(self):
        try:
            from mpos.ui.appearance_manager import AppearanceManager
            light = AppearanceManager.is_light_mode()
        except Exception:
            light = True
        return "black" if light else "white"

    def _sync_cursor_theme(self):
        if self._cursor is None:
            return
        target = self._cursor_target_theme()
        if target == self._cursor_theme:
            return
        try:
            if target == "black":
                self._cursor.set_style_image_recolor(lv.color_hex(0x000000), 0)  # NOQA
            else:
                self._cursor.set_style_image_recolor(lv.color_hex(0xFFFFFF), 0)  # NOQA
            self._cursor.set_style_image_recolor_opa(lv.OPA.COVER, 0)  # NOQA
        except Exception:
            return
        self._cursor_theme = target

    def _on_size_change(self, event):
        super()._on_size_change(event)
        self._x = self._clamp(self._x, self._width - 1)
        self._y = self._clamp(self._y, self._height - 1)

    def attach_cursor(self):
        if self._cursor is not None:
            return self._cursor
        dsc = lv.image_dsc_t()  # NOQA
        dsc.header.cf = lv.COLOR_FORMAT.ARGB8888  # NOQA
        dsc.header.w = _CURSOR_W
        dsc.header.h = _CURSOR_H
        dsc.header.stride = _CURSOR_W * 4
        dsc.data_size = _CURSOR_W * _CURSOR_H * 4
        dsc.data = _cursor_map()
        disp = self._disp_drv
        try:
            layer = disp.get_layer_top()  # NOQA
        except Exception:
            layer = lv.screen_active()
        cursor = lv.image(layer)  # NOQA
        cursor.set_src(dsc)
        cursor.remove_flag(lv.obj.FLAG.CLICKABLE)  # NOQA cursor must never take input
        self._cursor_dsc = dsc
        self._cursor = cursor
        try:
            self.set_cursor(cursor)
        except Exception:
            pass
        self._sync_cursor_theme()
        return cursor

    def show_cursor(self):
        if self._cursor is None:
            self.attach_cursor()
        try:
            self._cursor.remove_flag(lv.obj.FLAG.HIDDEN)  # NOQA
        except Exception:
            pass

    def hide_cursor(self):
        if self._cursor is None:
            return
        try:
            self._cursor.add_flag(lv.obj.FLAG.HIDDEN)  # NOQA
        except Exception:
            pass

    def _on_display_changed(self, new_lv_disp):
        self._disp_drv = new_lv_disp
        self._width = new_lv_disp.get_horizontal_resolution()
        self._height = new_lv_disp.get_vertical_resolution()
        self._x = self._clamp(self._x, self._width - 1)
        self._y = self._clamp(self._y, self._height - 1)
        if self._cursor is not None:
            try:
                self._cursor.set_parent(new_lv_disp.get_layer_top())  # NOQA
            except Exception:
                pass
            try:
                self.set_cursor(self._cursor)
            except Exception:
                pass

    def delete(self):
        try:
            if self._cursor is not None:
                self._cursor.delete()  # NOQA
        except Exception:
            pass
        self._cursor = None
        try:
            if self in pointer_framework.PointerDriver._indevs:
                pointer_framework.PointerDriver._indevs.remove(self)
        except Exception:
            pass
        try:
            self._indev_drv.delete()  # NOQA
        except Exception:
            try:
                self.enable(False)
            except Exception:
                pass
