import gc
import lvgl as lv

from mpos import Activity, Intent, SharedPreferences, SettingsActivity
from mpos.ui.display_metrics import DisplayMetrics

from learn_ir import LearnIR

try:
    from machine import Pin
    from ir.ir_tx.nec import NEC
    from ir.ir_tx.sony import SONY_12

    simulation_mode = False
except Exception as e:
    print(f"Activating simulation mode because could not import Pin/NEC/SONY: {e}")
    simulation_mode = True
    Pin = None
    NEC = None
    SONY_12 = None


class IRRemote(Activity):
    SETTING_KEY = "ir_profile"
    DEFAULT_PROFILE = "Samsung"

    PROFILES = {
        "Samsung": {
            "protocol": "nec",
            "addr": 7,
            "power": [2, 2],
            "vol_up": [7, 7],
            "vol_down": [11, 11],
            "samsung": True,
        },
        "Optoma": {
            "protocol": "nec",
            "addr": 50,
            "power": [2],
            "vol_up": [17],
            "vol_down": [20],
            "samsung": False,
        },
        "Sony": {
            "protocol": "sony",
            "addr": 1,
            "power": [21],
            "vol_up": [18],
            "vol_down": [19],
        },
    }

    def onCreate(self):
        self.prefs = SharedPreferences(self.appFullName)
        self.nec = None
        self.sony = None
        self.ir_pin = None

        if not simulation_mode:
            try:
                self.ir_pin = Pin(2, Pin.OUT)
            except Exception as e:
                print(f"Failed to init IR pin, switching to simulation mode: {e}")
                self.ir_pin = None

        self.screen = lv.obj()
        self.screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)

        pad = DisplayMetrics.pct_of_height(4)
        self.screen.set_style_pad_all(pad, 0)
        self.screen.set_style_pad_gap(pad, 0)

        header_height = self._header_height(pad)
        self.header = lv.obj(self.screen)
        self.header.set_size(lv.pct(100), header_height)
        self.header.set_flex_flow(lv.FLEX_FLOW.ROW)
        self.header.set_flex_align(
            lv.FLEX_ALIGN.SPACE_BETWEEN,
            lv.FLEX_ALIGN.CENTER,
            lv.FLEX_ALIGN.CENTER,
        )
        self.header.set_style_pad_all(0, 0)

        self.setting_label = lv.label(self.header)
        self.setting_label.set_style_text_font(lv.font_montserrat_16, 0)

        self._settings_button = lv.button(self.header)
        settings_size = self._settings_button_size()
        self._settings_button.set_size(settings_size, settings_size)
        self._settings_button.add_event_cb(self._open_settings, lv.EVENT.CLICKED, None)
        settings_label = lv.label(self._settings_button)
        settings_label.set_text(lv.SYMBOL.SETTINGS)
        settings_label.set_style_text_font(lv.font_montserrat_20, lv.PART.MAIN)
        settings_label.center()

        button_height = DisplayMetrics.pct_of_height(20)
        button_width = DisplayMetrics.pct_of_width(92)

        self._make_button(self.screen, "On/Off", button_width, button_height, self._send_power)
        self._make_button(self.screen, "Vol+", button_width, button_height, self._send_vol_up)
        self._make_button(self.screen, "Vol-", button_width, button_height, self._send_vol_down)

        self.setContentView(self.screen)

        self._apply_profile()
        self._refresh_setting_label()

    def onResume(self, screen):
        super().onResume(screen)
        self._apply_profile()
        self._refresh_setting_label()

    def _open_settings(self, event):
        intent = Intent(activity_class=SettingsActivity)
        intent.putExtra("prefs", self.prefs)
        intent.putExtra(
            "settings",
            [
                {
                    "title": "IR Profile",
                    "key": self.SETTING_KEY,
                    "ui": "radiobuttons",
                    "ui_options": [(name, name) for name in self.PROFILES.keys()],
                    "default_value": self.DEFAULT_PROFILE,
                },
                {
                "title": "Learn IR",
                "key": "learn_ir",
                "dont_persist": True,
                "ui": "activity",
                "activity_class": LearnIR,
                "placeholder": "Receive and decode IR signals (needs receiver diode)",
                },
            ],
        )
        self.startActivity(intent)

    def _profile_name(self):
        name = self.prefs.get_string(self.SETTING_KEY, self.DEFAULT_PROFILE)
        return name if name in self.PROFILES else self.DEFAULT_PROFILE

    def _refresh_setting_label(self):
        self.setting_label.set_text(f"Setting: {self._profile_name()}")

    def _apply_profile(self):
        name = self._profile_name()
        profile = self.PROFILES.get(name, self.PROFILES[self.DEFAULT_PROFILE])

        if simulation_mode or not self.ir_pin:
            return

        try:
            if profile["protocol"] == "sony":
                if self.nec:
                    self._deinit_ir(self.nec)
                    self.nec = None
                if not self.sony:
                    self.sony = SONY_12(self.ir_pin)
            else:
                if self.sony:
                    self._deinit_ir(self.sony)
                    self.sony = None
                if not self.nec:
                    self.nec = NEC(self.ir_pin)
                self.nec.samsung = profile.get("samsung", False)
        except Exception as e:
            print(f"Failed to init IR protocol, switching to simulation mode: {e}")
            self.nec = None
            self.sony = None

    def _deinit_ir(self, driver):
        try:
            rmt = getattr(driver, "_rmt", None)
            if rmt and hasattr(rmt, "deinit"):
                rmt.deinit()
        except Exception as e:
            print(f"Failed to deinit IR driver: {e}")
        gc.collect()

    def _header_height(self, pad):
        height = DisplayMetrics.height()
        return max(44, int(height * 0.12))

    def _settings_button_size(self):
        min_dim = DisplayMetrics.min_dimension()
        return max(36, int(min_dim * 0.12))

    def _make_button(self, parent, label, width, height, callback):
        btn = lv.button(parent)
        btn.set_size(width, height)
        btn.add_event_cb(lambda e: callback(), lv.EVENT.CLICKED, None)
        lbl = lv.label(btn)
        lbl.set_text(label)
        lbl.center()
        lbl.set_style_text_font(lv.font_montserrat_24, 0)

    def _transmit(self, data):
        profile = self.PROFILES.get(self._profile_name(), self.PROFILES[self.DEFAULT_PROFILE])
        addr = profile["addr"]

        if simulation_mode or (not self.nec and not self.sony):
            print(
                f"Simulation mode: would transmit protocol={profile['protocol']} addr=0x{addr:02x} data=0x{data:02x}"
            )
            return

        if profile["protocol"] == "sony":
            self.sony.transmit(addr, data)
        else:
            self.nec.transmit(addr, data)

    def _send_vol_up(self):
        print("Sending volume up")
        for code in self.PROFILES[self._profile_name()]["vol_up"]:
            self._transmit(code)

    def _send_vol_down(self):
        print("Sending volume down")
        for code in self.PROFILES[self._profile_name()]["vol_down"]:
            self._transmit(code)

    def _send_power(self):
        print("Sending on/off")
        for code in self.PROFILES[self._profile_name()]["power"]:
            self._transmit(code)
