import lvgl as lv

from mpos import Activity, Intent, SettingsActivity, SharedPreferences, WifiService


class Hotspot(SettingsActivity):
    """
    Hotspot configuration app.

    Uses SettingsActivity to render and edit hotspot preferences stored under
    com.micropythonos.system.hotspot.
    """

    DEFAULTS = {
        "enabled": False,
        "ssid": "MicroPythonOS",
        "password": "",
        "channel": 1,
        "hidden": False,
        "max_clients": 4,
        "authmode": None,
        "ip": "192.168.4.1",
        "netmask": "255.255.255.0",
        "gateway": "192.168.4.1",
        "dns": "8.8.8.8",
    }

    def getIntent(self):
        prefs = SharedPreferences("com.micropythonos.system.hotspot", defaults=self.DEFAULTS)
        intent = Intent()
        intent.putExtra("prefs", prefs)
        intent.putExtra(
            "settings",
            [
                {
                    "title": "Hotspot Enabled",
                    "key": "enabled",
                    "ui": "radiobuttons",
                    "ui_options": [("On", "True"), ("Off", "False")],
                    "changed_callback": self.toggle_hotspot,
                },
                {
                    "title": "Network Name (SSID)",
                    "key": "ssid",
                    "placeholder": "Hotspot SSID",
                },
                {
                    "title": "Password",
                    "key": "password",
                    "placeholder": "Leave empty for open network",
                },
                {
                    "title": "Channel",
                    "key": "channel",
                    "placeholder": "Wi-Fi channel, e.g. 1",
                },
                {
                    "title": "Hidden Network",
                    "key": "hidden",
                    "ui": "radiobuttons",
                    "ui_options": [("Visible", "False"), ("Hidden", "True")],
                    "changed_callback": self.toggle_hotspot,
                },
                {
                    "title": "Max Clients",
                    "key": "max_clients",
                    "placeholder": "Max connections, e.g. 4",
                },
                {
                    "title": "Auth Mode",
                    "key": "authmode",
                    "ui": "dropdown",
                    "ui_options": [
                        ("Auto", None),
                        ("Open", "open"),
                        ("WPA", "wpa"),
                        ("WPA2", "wpa2"),
                        ("WPA/WPA2", "wpa_wpa2"),
                    ],
                    "changed_callback": self.toggle_hotspot,
                },
                {
                    "title": "IP Address",
                    "key": "ip",
                    "placeholder": "Hotspot IP, e.g. 192.168.4.1",
                },
                {
                    "title": "Netmask",
                    "key": "netmask",
                    "placeholder": "Netmask, e.g. 255.255.255.0",
                },
                {
                    "title": "Gateway",
                    "key": "gateway",
                    "placeholder": "Gateway, e.g. 192.168.4.1",
                },
                {
                    "title": "DNS",
                    "key": "dns",
                    "placeholder": "DNS, e.g. 8.8.8.8",
                },
            ],
        )
        return intent

    def toggle_hotspot(self, new_value):
        enabled_value = self.prefs.get_string("enabled", "False")
        should_enable = str(enabled_value).lower() in ("true", "1", "yes", "on")
        if should_enable:
            WifiService.enable_hotspot()
        else:
            WifiService.disable_hotspot()
