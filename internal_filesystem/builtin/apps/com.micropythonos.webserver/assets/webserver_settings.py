import lvgl as lv

from mpos import Activity, DisplayMetrics, Intent, SettingsActivity, SharedPreferences, WebServer, WifiService


class WebServerSettings(Activity):
    status_label = None
    detail_label = None
    action_button = None
    action_label = None
    settings_button = None
    prefs = None

    def onCreate(self):
        self.prefs = SharedPreferences(WebServer.PREFS_NAMESPACE, defaults=WebServer.DEFAULTS)
        self.ui_prefs = SharedPreferences(WebServer.PREFS_NAMESPACE)
        screen = lv.obj()
        screen.set_style_border_width(0, lv.PART.MAIN)
        screen.set_style_pad_all(DisplayMetrics.pct_of_width(3), lv.PART.MAIN)
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)

        header = lv.label(screen)
        header.set_text("WebServer")
        header.set_style_text_font(lv.font_montserrat_20, lv.PART.MAIN)

        self.status_label = lv.label(screen)
        self.status_label.set_style_text_font(lv.font_montserrat_14, lv.PART.MAIN)
        self.status_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.status_label.set_width(lv.pct(100))

        self.detail_label = lv.label(screen)
        self.detail_label.set_style_text_font(lv.font_montserrat_12, lv.PART.MAIN)
        self.detail_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.detail_label.set_width(lv.pct(100))

        button_row = lv.obj(screen)
        button_row.set_width(lv.pct(100))
        button_row.set_height(lv.SIZE_CONTENT)
        button_row.set_style_border_width(0, lv.PART.MAIN)
        button_row.set_style_pad_all(0, lv.PART.MAIN)
        button_row.set_flex_flow(lv.FLEX_FLOW.ROW)
        button_row.set_style_flex_main_place(lv.FLEX_ALIGN.SPACE_BETWEEN, lv.PART.MAIN)

        self.action_button = lv.button(button_row)
        self.action_button.set_size(lv.pct(45), lv.SIZE_CONTENT)
        self.action_button.add_event_cb(self.toggle_webserver, lv.EVENT.CLICKED, None)
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
        status = WebServer.status()
        state_text = "Running" if status.get("started") else "Stopped"
        self.status_label.set_text(f"Status: {state_text}")
        autostart_text = "On" if status.get("autostart") else "Off"
        port = status.get("port")
        ip_address = WifiService.get_ipv4_address()
        if ip_address:
            url_text = f"http://{ip_address}:{port}"
        else:
            url_text = f"http://<wifi ip>:{port}"
        self.detail_label.set_text(f"URL: {url_text}\nAutostart: {autostart_text}")

        button_text = "Stop" if status.get("started") else "Start"
        self.action_label.set_text(button_text)
        self.action_label.center()

    def toggle_webserver(self, event):
        if WebServer.is_started():
            WebServer.stop()
        else:
            WebServer.start()
        self.refresh_status()

    def open_settings(self, event):
        intent = Intent(activity_class=SettingsActivity)
        intent.putExtra("prefs", self.ui_prefs)
        intent.putExtra(
            "settings",
            [
                {
                    "title": "Autostart",
                    "key": "autostart",
                    "ui": "radiobuttons",
                    "ui_options": [("On", "True"), ("Off", "False")],
                    "default_value": WebServer.DEFAULTS["autostart"],
                    "changed_callback": self.settings_changed,
                },
                {
                    "title": "Port",
                    "key": "port",
                    "placeholder": "WebServer port, e.g. 7890",
                    "default_value": WebServer.DEFAULTS["port"],
                    "changed_callback": self.settings_changed,
                },
                {
                    "title": "Password",
                    "key": "password",
                    "placeholder": "Max 9 characters",
                    "default_value": WebServer.DEFAULTS["password"],
                    "changed_callback": self.settings_changed,
                },
            ],
        )
        self.startActivity(intent)

    def settings_changed(self, new_value):
        WebServer.apply_settings(restart_if_running=True)
        self.refresh_status()
