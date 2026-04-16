import lvgl as lv

from mpos import Activity
from mpos.ui.display_metrics import DisplayMetrics

try:
    from machine import Pin
    from ir.ir_tx.nec import NEC
    simulation_mode = False
except Exception as e:
    print(f"Activating simulation mode because could not import Pin/NEC: {e}")
    simulation_mode = True
    Pin = None
    NEC = None


class IRRemote(Activity):
    def onCreate(self):
        self.nec = None
        self.addr = 0x707

        if not simulation_mode:
            try:
                self.ir_pin = Pin(2, Pin.OUT)
                self.nec = NEC(self.ir_pin)
                self.nec.samsung = True
            except Exception as e:
                print(f"Failed to init IR, switching to simulation mode: {e}")
                self.nec = None

        screen = lv.obj()
        screen.set_size(lv.pct(100), lv.pct(100))
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        pad = self._pad()
        screen.set_style_pad_all(pad, 0)
        screen.set_style_pad_gap(pad, 0)

        button_height = self._button_height(pad)
        button_width = self._button_width(pad)

        self._make_button(screen, "On/Off", button_width, button_height, self._send_power)
        self._make_button(screen, "Vol+", button_width, button_height, self._send_vol_up)
        self._make_button(screen, "Vol-", button_width, button_height, self._send_vol_down)

        self.setContentView(screen)

    def _pad(self):
        min_dim = DisplayMetrics.min_dimension()
        if min_dim is None:
            return 10
        return max(6, int(min_dim * 0.04))

    def _button_width(self, pad):
        width = DisplayMetrics.width()
        if width is None:
            return lv.pct(100)
        return max(40, int(width - pad * 2))

    def _button_height(self, pad):
        height = DisplayMetrics.height()
        if height is None:
            return lv.pct(30)
        available = height - pad * 4
        return max(40, int(available / 3))

    def _make_button(self, parent, label, width, height, callback):
        btn = lv.button(parent)
        btn.set_size(width, height)
        btn.add_event_cb(lambda e: callback(), lv.EVENT.CLICKED, None)
        lbl = lv.label(btn)
        lbl.set_text(label)
        lbl.center()
        lbl.set_style_text_font(lv.font_montserrat_24, 0)

    def _transmit(self, data):
        if not self.nec:
            print(
                f"Simulation mode: would transmit addr=0x{self.addr:03x} data=0x{data:02x}"
            )
            return
        self.nec.transmit(self.addr, data)

    def _send_vol_up(self):
        print("Sending volume up")
        self._transmit(0x07)

    def _send_vol_down(self):
        print("Sending volume down")
        self._transmit(0x0B)

    def _send_power(self):
        print("Sending on/off")
        #self._transmit(0xE6)
        #self._transmit(0xE6)
        self._transmit(0x02)
