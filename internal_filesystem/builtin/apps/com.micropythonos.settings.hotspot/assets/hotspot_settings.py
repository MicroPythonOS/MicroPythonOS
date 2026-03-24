import lvgl as lv

from mpos import Activity, DisplayMetrics, Intent, SettingsActivity, SharedPreferences, WifiService


class HotspotSettings(Activity):
    """
    Hotspot configuration app.

    Uses SettingsActivity to render and edit hotspot preferences stored under
    com.micropythonos.settings.hotspot.
    """

    DEFAULTS = {
        "ssid": "MicroPythonOS",
        "password": "",
        "authmode": "none",
    }

    status_label = None
    action_button = None
    action_label = None
    settings_button = None
    prefs = None

    def onCreate(self):
        self.prefs = SharedPreferences("com.micropythonos.settings.hotspot", defaults=self.DEFAULTS)
        self.ui_prefs = SharedPreferences("com.micropythonos.settings.hotspot")
        screen = lv.obj()
        screen.set_style_border_width(0, lv.PART.MAIN)
        screen.set_style_pad_all(DisplayMetrics.pct_of_width(3), lv.PART.MAIN)
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)

        header = lv.label(screen)
        header.set_text("Hotspot")
        header.set_style_text_font(lv.font_montserrat_20, lv.PART.MAIN)

        self.status_label = lv.label(screen)
        self.status_label.set_style_text_font(lv.font_montserrat_14, lv.PART.MAIN)
        self.status_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.status_label.set_width(lv.pct(100))

        button_row = lv.obj(screen)
        button_row.set_width(lv.pct(100))
        button_row.set_height(lv.SIZE_CONTENT)
        button_row.set_style_border_width(0, lv.PART.MAIN)
        button_row.set_style_pad_all(10, lv.PART.MAIN)
        button_row.set_flex_flow(lv.FLEX_FLOW.ROW)
        button_row.set_style_flex_main_place(lv.FLEX_ALIGN.SPACE_BETWEEN, lv.PART.MAIN)

        self.action_button = lv.button(button_row)
        self.action_button.set_size(lv.pct(45), lv.SIZE_CONTENT)
        self.action_button.add_event_cb(self.toggle_hotspot_button, lv.EVENT.CLICKED, None)
        self.action_label = lv.label(self.action_button)
        self.action_label.center()

        self.settings_button = lv.button(button_row)
        self.settings_button.set_size(lv.pct(45), lv.SIZE_CONTENT)
        self.settings_button.add_event_cb(self.open_settings, lv.EVENT.CLICKED, None)
        settings_label = lv.label(self.settings_button)
        settings_label.set_text("Settings")
        settings_label.center()

        self.setContentView(screen)

    def onResume(self, screen):
        super().onResume(screen)
        self.refresh_status()

    def refresh_status(self):
        is_running = WifiService.is_hotspot_enabled()
        state_text = "Running" if is_running else "Stopped"
        ssid = self.prefs.get_string("ssid", self.DEFAULTS["ssid"])
        authmode = self.prefs.get_string("authmode", None)
        security_text = self._format_security_label(authmode)
        self.status_label.set_text(
            f"Status: {state_text}\nHotspot name: {ssid}\nSecurity: {security_text}"
        )
        button_text = "Stop" if is_running else "Start"
        self.action_label.set_text(button_text)
        self.action_label.center()

    def toggle_hotspot_button(self, event):
        if WifiService.is_hotspot_enabled():
            WifiService.disable_hotspot()
        else:
            WifiService.enable_hotspot()
        self.refresh_status()

    def open_settings(self, event):
        intent = Intent(activity_class=SettingsActivity)
        intent.putExtra("prefs", self.ui_prefs)
        intent.putExtra("settings", self._settings_entries())
        self.startActivity(intent)

    def _settings_entries(self):
        return [
            {
                "title": "Network Name (SSID)",
                "key": "ssid",
                "placeholder": "Hotspot SSID",
                "default_value": self.DEFAULTS["ssid"],
            },
            {
                "title": "Password",
                "key": "password",
                "placeholder": "Leave empty for open network",
                "default_value": self.DEFAULTS["password"],
                "should_show": self.should_show_password,
            },
            {
                "title": "Auth Mode",
                "key": "authmode",
                "ui": "dropdown",
                "ui_options": [
                    ("None", "none"),
                    ("WPA2", "wpa2"),
                ],
                "default_value": self.DEFAULTS["authmode"],
                "changed_callback": self.toggle_hotspot,
            },
        ]

    def toggle_hotspot(self, new_value):
        if WifiService.is_hotspot_enabled():
            WifiService.enable_hotspot()
        self.refresh_status()

    def should_show_password(self, setting):
        authmode = self.prefs.get_string("authmode", None)
        if authmode is None:
            authmode = self.DEFAULTS["authmode"]
        return authmode != "none"

    def _format_security_label(self, authmode):
        labels = {
            "none": "None",
            "wpa2": "WPA2",
        }
        return labels.get(authmode, "WPA2")

