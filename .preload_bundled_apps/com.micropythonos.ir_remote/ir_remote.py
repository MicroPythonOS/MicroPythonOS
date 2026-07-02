import gc
import logging
import lvgl as lv

from mpos import Activity, Intent, SharedPreferences, SettingsActivity, IRManager
from mpos.ui.display_metrics import DisplayMetrics

from learn_ir import LearnIR
from learn_nec_ir import LearnNECIR
from learn_blaster_ir import LearnBlasterIR
from learn_tcl_ir import LearnTCLIR

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

try:
    from machine import Pin
    from ir.ir_tx.nec import NEC
    from ir.ir_tx.sony import SONY_12
    from ir.ir_tx.tcl import TCL

    simulation_mode = False
    if __debug__: logger.debug("IR TX imports OK: Pin=%s NEC=%s SONY_12=%s TCL=%s", Pin, NEC, SONY_12, TCL)
except Exception as e:
    logger.error("Activating simulation mode because could not import Pin/NEC/SONY/TCL: %s", e)
    simulation_mode = True
    Pin = None
    NEC = None
    SONY_12 = None
    TCL = None


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
            "power": [129],
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
        "TCL": {
            "protocol": "tcl",
            "addr": 0x054F,
            "power": [0xAB],
            "vol_up": [0xAB],
            "vol_down": [0xAB],
            "freq": 38000,
        },
        "TCL36": {
            "protocol": "tcl",
            "addr": 0x054F,
            "power": [0xAB],
            "vol_up": [0xAB],
            "vol_down": [0xAB],
            "freq": 36000,
        },
    }

    def onCreate(self):
        if __debug__: logger.debug("onCreate: simulation_mode=%s", simulation_mode)
        self.prefs = SharedPreferences(self.appFullName)
        self.nec = None
        self.sony = None
        self.tcl = None
        self.ir_pin = None

        if not simulation_mode:
            try:
                self.ir_pin = IRManager.txPin
                if __debug__: logger.debug("onCreate: IRManager.txPin=%s", self.ir_pin)
            except Exception as e:
                logger.error("Failed to init IR pin, switching to simulation mode: %s", e)
                self.ir_pin = None
        if __debug__: logger.debug("onCreate: ir_pin=%s", self.ir_pin)

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

    def onPause(self, screen):
        try:
            self.ir_pin.value(0) # make sure it's low because some devices use a lot of power if left high accidentally
        except Exception as e:
            pass

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
                "title": "Print IR timings",
                "key": "learn_ir",
                "dont_persist": True,
                "ui": "activity",
                "activity_class": LearnIR,
                "placeholder": "Receive and decode IR signals (needs receiver diode)",
                },
                {
                "title": "Decode and print NEC IR",
                "key": "learn_nec_ir",
                "dont_persist": True,
                "ui": "activity",
                "activity_class": LearnNECIR,
                "placeholder": "Receive and decode NEC IR signals (needs receiver diode)",
                },
                {
                "title": "Decode and print Blaster IR",
                "key": "learn_blaster_ir",
                "dont_persist": True,
                "ui": "activity",
                "activity_class": LearnBlasterIR,
                "placeholder": "Receive and decode Blaster IR signals (needs receiver diode)",
                },
                {
                "title": "Decode and print TCL IR",
                "key": "learn_tcl_ir",
                "dont_persist": True,
                "ui": "activity",
                "activity_class": LearnTCLIR,
                "placeholder": "Receive and decode TCL TV IR signals (needs receiver diode)",
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
        if __debug__: logger.debug("_apply_profile: name=%s protocol=%s simulation=%s ir_pin=%s", name, profile.get("protocol"), simulation_mode, self.ir_pin)

        if simulation_mode or not self.ir_pin:
            logger.warning("_apply_profile: IR TX pin not configured; skipping (simulation=%s ir_pin=%s)", simulation_mode, self.ir_pin)
            return

        try:
            if profile["protocol"] == "sony":
                if self.nec:
                    self._deinit_ir(self.nec)
                    self.nec = None
                if self.tcl:
                    self._deinit_ir(self.tcl)
                    self.tcl = None
                if not self.sony:
                    if __debug__: logger.debug("_apply_profile: creating SONY_12 on pin %s", self.ir_pin)
                    self.sony = SONY_12(self.ir_pin)
                    if __debug__: logger.debug("_apply_profile: SONY_12 created: %s", self.sony)
            elif profile["protocol"] == "tcl":
                if self.nec:
                    self._deinit_ir(self.nec)
                    self.nec = None
                if self.sony:
                    self._deinit_ir(self.sony)
                    self.sony = None
                freq = profile.get("freq", 38000)
                if __debug__: logger.debug("_apply_profile: TCL freq=%s existing tcl=%s existing _freq=%s", freq, self.tcl, getattr(self.tcl, "_freq", None))
                if self.tcl and getattr(self.tcl, "_freq", None) != freq:
                    if __debug__: logger.debug("_apply_profile: freq changed, deiniting existing TCL")
                    self._deinit_ir(self.tcl)
                    self.tcl = None
                if not self.tcl:
                    if __debug__: logger.debug("_apply_profile: creating TCL(pin=%s, freq=%s)", self.ir_pin, freq)
                    self.tcl = TCL(self.ir_pin, freq=freq)
                    self.tcl._freq = freq
                    if __debug__: logger.debug("_apply_profile: TCL created: %s rmt=%s", self.tcl, getattr(self.tcl, "_rmt", None))
                else:
                    if __debug__: logger.debug("_apply_profile: reusing existing TCL driver")
            else:
                if self.sony:
                    self._deinit_ir(self.sony)
                    self.sony = None
                if self.tcl:
                    self._deinit_ir(self.tcl)
                    self.tcl = None
                if not self.nec:
                    if __debug__: logger.debug("_apply_profile: creating NEC on pin %s", self.ir_pin)
                    self.nec = NEC(self.ir_pin)
                    if __debug__: logger.debug("_apply_profile: NEC created: %s rmt=%s", self.nec, getattr(self.nec, "_rmt", None))
                self.nec.samsung = profile.get("samsung", False)
                if __debug__: logger.debug("_apply_profile: NEC samsung=%s", self.nec.samsung)
        except Exception as e:
            logger.error("_apply_profile: Failed to init IR protocol: %s", e)
            import sys
            sys.print_exception(e)
            self.nec = None
            self.sony = None
            self.tcl = None

    def _deinit_ir(self, driver):
        if __debug__: logger.debug("_deinit_ir: driver=%s", driver)
        try:
            rmt = getattr(driver, "_rmt", None)
            if __debug__: logger.debug("_deinit_ir: rmt=%s", rmt)
            if rmt and hasattr(rmt, "deinit"):
                rmt.deinit()
                if __debug__: logger.debug("_deinit_ir: rmt.deinit() done")
        except Exception as e:
            logger.error("_deinit_ir: Failed to deinit IR driver: %s", e)
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
        if __debug__: logger.debug("_transmit: protocol=%s addr=0x%x data=0x%x nec=%s sony=%s tcl=%s ir_pin=%s", profile["protocol"], addr, data, self.nec, self.sony, self.tcl, self.ir_pin)

        if simulation_mode or (not self.nec and not self.sony and not self.tcl):
            logger.warning("_transmit: no driver available (simulation=%s nec=%s sony=%s tcl=%s)", simulation_mode, self.nec, self.sony, self.tcl)
            return

        # On some boards (e.g. Fri3d 2024) the TX pin is shared with the battery
        # ADC, which reconfigures the GPIO as an ADC input after every reading.
        # Calling pin.init(Pin.OUT) alone is NOT enough: it reasserts CPU GPIO
        # routing in the GPIO matrix, which overrides the RMT routing set up when
        # the driver was constructed. The correct fix is to deinit and re-create
        # the driver so RMT re-acquires the pin via the GPIO matrix.
        if __debug__: logger.debug("_transmit: re-creating driver to re-acquire pin %s for RMT", self.ir_pin)
        self._deinit_ir(self.nec or self.sony or self.tcl)
        self.nec = self.sony = self.tcl = None
        self._apply_profile()
        if __debug__: logger.debug("_transmit: driver re-created nec=%s sony=%s tcl=%s", self.nec, self.sony, self.tcl)
        if not self.nec and not self.sony and not self.tcl:
            logger.warning("_transmit: driver re-creation failed, aborting transmit")
            return

        try:
            if profile["protocol"] == "sony":
                if __debug__: logger.debug("_transmit: calling sony.transmit(0x%x, 0x%x)", addr, data)
                self.sony.transmit(addr, data)
                if __debug__: logger.debug("_transmit: sony.transmit done")
            elif profile["protocol"] == "tcl":
                if __debug__: logger.debug("_transmit: calling tcl.transmit(0x%x, 0x%x) rmt=%s", addr, data, getattr(self.tcl, "_rmt", None))
                self.tcl.transmit(addr, data)
                if __debug__: logger.debug("_transmit: tcl.transmit done")
            else:
                if __debug__: logger.debug("_transmit: calling nec.transmit(0x%x, 0x%x) samsung=%s rmt=%s", addr, data, getattr(self.nec, "samsung", None), getattr(self.nec, "_rmt", None))
                self.nec.transmit(addr, data)
                if __debug__: logger.debug("_transmit: nec.transmit done")
        except Exception as e:
            logger.error("_transmit: transmit failed: %s", e)
            import sys
            sys.print_exception(e)

    def _send_vol_up(self):
        if __debug__: logger.debug("_send_vol_up: profile=%s", self._profile_name())
        for code in self.PROFILES[self._profile_name()]["vol_up"]:
            self._transmit(code)

    def _send_vol_down(self):
        if __debug__: logger.debug("_send_vol_down: profile=%s", self._profile_name())
        for code in self.PROFILES[self._profile_name()]["vol_down"]:
            self._transmit(code)

    def _send_power(self):
        if __debug__: logger.debug("_send_power: profile=%s", self._profile_name())
        for code in self.PROFILES[self._profile_name()]["power"]:
            self._transmit(code)
