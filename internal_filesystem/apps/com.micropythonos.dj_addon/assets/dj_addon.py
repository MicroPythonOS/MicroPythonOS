import math
import time
from mpos import DeviceManager
import lvgl as lv
from mpos import Activity, DisplayMetrics

_ADC_MAX = 4095

# ADC channel indices in DMA rank order (rank N → adc_channels[N-1])
_CH_PM_LEFT_BOTTOM  = 0  # rank 1
_CH_PM_LEFT_MID     = 1  # rank 2
_CH_PM_LEFT_TOP     = 2  # rank 3
_CH_SLIDER_LEFT     = 3  # rank 4
_CH_PM_RIGHT_BOTTOM = 4  # rank 5
_CH_PM_RIGHT_MID    = 5  # rank 6
_CH_PM_RIGHT_TOP    = 6  # rank 7
_CH_SLIDER_RIGHT    = 7  # rank 8
_CH_SLIDER_MID      = 8  # rank 9

_MARGIN       = 4
_ARC_GAP      = 4
_BTN_GAP      = 2
_CROSSFADER_H = 22
_REFRESH_MS   = 100
_MIDI_MS      = 10

# LVGL arc default angles (0°=east, clockwise). In REVERSE mode the needle
# tip sits at _ARC_END_DEG when value=0 and sweeps _ARC_RANGE_DEG CCW to
# _ARC_START_DEG when value=_ADC_MAX.
_ARC_END_DEG   = 45
_ARC_RANGE_DEG = 270

# Maps dj.buttons index → pad_buttons index.
# DJ row 0 (indices 0-3) sits at the bottom of the hardware, which corresponds
# to pad row 1 (indices 4-7) at the bottom of the display grid, and vice versa.
_DJ_TO_PAD = (3,7,1,2,0,5,6,4)
_PAD_COLORS = ((0, 0, 0), (255, 0, 0), (0, 255, 0), (0, 0, 255))

class _MockDJAddon:
    version = (1, 0, 0)

    @property
    def analog(self):
        t = time.ticks_ms()
        result = []
        for i in range(9):
            phase = (t + i * 222) % 2000
            val = phase if phase < 1000 else 2000 - phase
            result.append(int(val * 4.095))
        return result

    @property
    def buttons(self):
        idx = (time.ticks_ms() // 1000) % 8
        return tuple(i == idx for i in range(8))

    def set_led(self, idx, r, g, b):
        pass


class DJAddonActivity(Activity):

    def __init__(self):
        super().__init__()
        self.dj = None
        self.m = None
        self.uart = None
        self.write_idx = 0
        self.timer = None
        self.midi_timer = None
        self.arcs_left  = []  # list of (arc, needle, cx, cy, r)
        self.arcs_right = []  # list of (arc, needle, cx, cy, r)
        self.bar_left   = None
        self.bar_right  = None
        self.slider_mid = None
        self.pad_buttons = []
        self.pad_button_states = []  # 0=off, 1=R, 2=G, 3=B cycles on each click

    def onCreate(self):
        screen = lv.obj()
        screen.set_style_bg_color(lv.color_black(), lv.PART.MAIN)
        screen.set_style_border_width(0, lv.PART.MAIN)
        screen.set_style_pad_all(0, lv.PART.MAIN)

        try:
            from drivers.fri3d.dj import DJAddon
            i2c_bus = DeviceManager.getBus(type="i2c")
            self.dj = DJAddon(i2c_bus=i2c_bus)
            version = self.dj.version
            print("DJ Addon FW version:", ".".join(str(i) for i in version))
            if version != (1, 0, 0):
                raise ValueError("unexpected firmware version")
            print("Disabling UART REPL because it receives data from the DJ Add-On. Use esp.uart_repl(True) to re-enable.")

            # disable the REPL on the uart
            import esp
            esp.uart_repl(False)

            # enable a USB midi device
            import usb.device
            from usb.device.midi import MIDIInterface
            self.m = MIDIInterface()
            usb.device.get().init(self.m, builtin_driver=True)

            # start reading MIDI messages from UART
            from machine import UART, Pin
            self.uart = UART(2, baudrate=115200, rx=Pin(44), tx=Pin(43))
            self.uart.init(115200, bits=8, parity=None, stop=1)
            self._uart_rx_buf = bytearray(4)
            self._uart_rx_mv = memoryview(self._uart_rx_buf)
            self.uart.flush()

        except Exception as e:
            print("DJ Addon not available, using mock:", e)
            self.dj = _MockDJAddon()

        self._build_ui(screen)
        self.setContentView(screen)

    # pipes the DJ Add-on UART MIDI messages to USB
    def _flush_midi(self, _):
        if self.uart is None or self.m is None:
            return
        try:
            if not self.uart.any():
                return
            n = self.uart.readinto(self._uart_rx_mv[self.write_idx:], 4 - self.write_idx)
            if not n:
                return
            self.write_idx += n
            if self.write_idx >= 4:
                if self.m.is_open():
                    self.m.send_event(self._uart_rx_buf[0], self._uart_rx_buf[1], self._uart_rx_buf[2], self._uart_rx_buf[3])
                self.write_idx = 0
        except Exception as e:
            print("MIDI flush error:", e)
            self.uart.flush()
            self.write_idx = 0

    # --- widget factories ---

    def _make_arc_at(self, parent, size, x, y):
        arc = lv.arc(parent)
        arc.set_size(size, size)
        arc.set_pos(x, y)
        arc.set_range(0, _ADC_MAX)
        arc.set_value(0)
        arc.set_mode(lv.arc.MODE.REVERSE)
        arc.set_style_opa(lv.OPA.TRANSP, lv.PART.INDICATOR)
        arc.set_style_opa(lv.OPA.TRANSP, lv.PART.KNOB)
        arc.remove_flag(lv.obj.FLAG.CLICKABLE)

        cx = x + size // 2
        cy = y + size // 2
        r  = size // 2 - 4

        needle = lv.line(parent)
        needle.set_style_line_width(4, lv.PART.MAIN)
        needle.set_style_line_color(lv.color_white(), lv.PART.MAIN)
        needle.set_style_line_rounded(True, lv.PART.MAIN)
        self._set_needle(needle, cx, cy, r, 0)

        return arc, needle, cx, cy, r

    def _make_vbar(self, parent, w, h):
        bar = lv.bar(parent)
        bar.set_size(w, h)
        bar.set_range(0, _ADC_MAX)
        bar.set_value(0, False)
        bar.remove_flag(lv.obj.FLAG.CLICKABLE)
        return bar

    def _make_pad_grid(self, parent, x, y, w, h):
        btn_w = (w - _BTN_GAP * 3) // 4
        btn_h = (h - _BTN_GAP) // 2
        self.pad_buttons = []
        self.pad_button_states = []
        for row in range(2):
            for col in range(4):
                idx = len(self.pad_buttons)
                btn = lv.obj(parent)
                btn.set_size(btn_w, btn_h)
                btn.set_pos(x + col * (btn_w + _BTN_GAP), y + row * (btn_h + _BTN_GAP))
                btn.set_style_bg_color(lv.color_black(), lv.PART.MAIN)
                btn.set_style_border_width(2, lv.PART.MAIN)
                btn.set_style_border_color(lv.color_hex(0x444444), lv.PART.MAIN)
                btn.set_style_radius(3, lv.PART.MAIN)
                btn.remove_flag(lv.obj.FLAG.SCROLLABLE)
                btn.add_event_cb(lambda _e, i=idx: self._on_pad_click(i), lv.EVENT.CLICKED, None)
                self.pad_buttons.append(btn)
                self.pad_button_states.append(0)

    @staticmethod
    def _set_needle(needle, cx, cy, r, value):
        angle_rad = math.radians(_ARC_END_DEG - (value / _ADC_MAX) * _ARC_RANGE_DEG)
        tx = int(cx + r * math.cos(angle_rad))
        ty = int(cy + r * math.sin(angle_rad))
        needle.set_points([{'x': cx, 'y': cy}, {'x': tx, 'y': ty}], 2)

    def _on_pad_click(self, idx):
        self.pad_button_states[idx] = (self.pad_button_states[idx] + 1) % 4
        r, g, b = _PAD_COLORS[self.pad_button_states[idx]]
        self.set_button_color(idx, r, g, b)

    # --- public API ---

    def set_button_color(self, idx: int, r: int, g: int, b: int):
        if 0 <= idx < len(self.pad_buttons):
            self.pad_buttons[idx].set_style_bg_color(lv.color_make(r, g, b), lv.PART.MAIN)
        if self.dj is not None:
            self.dj.set_led(idx, r, g, b)

    # --- layout ---

    def _build_ui(self, screen):
        W = DisplayMetrics.width()
        H = DisplayMetrics.height()

        top_h = H - _CROSSFADER_H - _MARGIN * 3

        # Three-zone layout: [left deck | button grid | right deck]
        center_w = W // 2
        side_w   = (W - center_w) // 2
        center_x = side_w

        # Arcs fill the full side width (no separate slider column)
        arc_size = min((top_h - _ARC_GAP * 2) // 3, side_w - _MARGIN * 2)
        arc_h    = 3 * arc_size + 2 * _ARC_GAP

        left_arc_x  = _MARGIN
        right_arc_x = center_x + center_w + _MARGIN

        # Left deck: bar first (background), then arcs on top
        self.bar_left = self._make_vbar(screen, arc_size, arc_h)
        self.bar_left.set_pos(left_arc_x, _MARGIN)

        self.arcs_left = []
        for i in range(3):
            self.arcs_left.append(
                self._make_arc_at(screen, arc_size, left_arc_x, _MARGIN + i * (arc_size + _ARC_GAP))
            )

        # Center: 2-row × 4-column pad button grid
        self._make_pad_grid(screen, center_x, _MARGIN, center_w, top_h)

        # Right deck: bar first (background), then arcs on top
        self.bar_right = self._make_vbar(screen, arc_size, arc_h)
        self.bar_right.set_pos(right_arc_x, _MARGIN)

        self.arcs_right = []
        for i in range(3):
            self.arcs_right.append(
                self._make_arc_at(screen, arc_size, right_arc_x, _MARGIN + i * (arc_size + _ARC_GAP))
            )

        # Crossfader: horizontal, full width, bottom
        self.slider_mid = lv.slider(screen)
        self.slider_mid.set_size(W - _MARGIN * 2, _CROSSFADER_H - 6)
        self.slider_mid.set_range(_ADC_MAX, 0)
        self.slider_mid.set_value(_ADC_MAX // 2, False)
        self.slider_mid.set_style_opa(lv.OPA.TRANSP, lv.PART.INDICATOR)
        self.slider_mid.remove_flag(lv.obj.FLAG.CLICKABLE)
        self.slider_mid.set_pos(_MARGIN, H - _MARGIN - _CROSSFADER_H)

    # --- data update ---

    def _update_ui(self, analog, buttons):
        vals_left  = (analog[_CH_PM_LEFT_TOP],  analog[_CH_PM_LEFT_MID],  analog[_CH_PM_LEFT_BOTTOM])
        vals_right = (analog[_CH_PM_RIGHT_TOP], analog[_CH_PM_RIGHT_MID], analog[_CH_PM_RIGHT_BOTTOM])

        for (_, needle, cx, cy, r), val in zip(self.arcs_left, vals_left):
            self._set_needle(needle, cx, cy, r, val)

        for (_, needle, cx, cy, r), val in zip(self.arcs_right, vals_right):
            self._set_needle(needle, cx, cy, r, val)

        for dj_idx, pressed in enumerate(buttons):
            color = lv.color_white() if pressed else lv.color_hex(0x444444)
            self.pad_buttons[_DJ_TO_PAD[dj_idx]].set_style_border_color(color, lv.PART.MAIN)

        self.bar_left.set_value(_ADC_MAX - analog[_CH_SLIDER_LEFT], False)
        self.bar_right.set_value(_ADC_MAX - analog[_CH_SLIDER_RIGHT], False)
        self.slider_mid.set_value(analog[_CH_SLIDER_MID], False)

    # --- lifecycle ---

    def onResume(self, screen):
        if self.timer is None:
            self.timer = lv.timer_create(self.refresh, _REFRESH_MS, None)
        if self.midi_timer is None and self.uart is not None:
            self.midi_timer = lv.timer_create(self._flush_midi, _MIDI_MS, None)
        if self.dj is not None:
            for idx in range(len(self.pad_buttons)):
                r, g, b = _PAD_COLORS[self.pad_button_states[idx]]
                self.set_button_color(idx, r, g, b)


    def onPause(self, screen):
        if self.timer:
            self.timer.delete()
            self.timer = None
        if self.midi_timer:
            self.midi_timer.delete()
            self.midi_timer = None
        if self.dj is not None:
            for idx in range(len(self.pad_buttons)):
                self.dj.set_led(idx, 0, 0, 0)


    def refresh(self, timer):
        if self.dj is None:
            return
        try:
            self._update_ui(self.dj.analog, self.dj.buttons)
        except Exception as e:
            print("DJ refresh error:", e)
