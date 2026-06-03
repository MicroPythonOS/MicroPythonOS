import lvgl as lv

from mpos import Activity, Intent, ConnectivityManager, DisplayMetrics, SharedPreferences, SettingsActivity
from fullscreen_qr import FullscreenQR
from nostr_service import NostrManager


class ShowNpubQRActivity(Activity):
    """Activity that computes npub from nsec and displays it as a QR code"""

    def onCreate(self):
        try:
            print("ShowNpubQRActivity.onCreate() called")
            prefs = self.getIntent().extras.get("prefs")
            print(f"Got prefs: {prefs}")
            nsec = prefs.get_string("nostr_nsec")
            print(f"Got nsec: {nsec[:20] if nsec else 'None'}...")

            if not nsec:
                print("ERROR: No nsec configured")
                error_screen = lv.obj()
                error_label = lv.label(error_screen)
                error_label.set_text("No nsec configured")
                error_label.center()
                self.setContentView(error_screen)
                return

            print("Importing PrivateKey...")
            from nostr.key import PrivateKey
            print("Computing npub from nsec...")
            if nsec.startswith("nsec1"):
                print("Using from_nsec()")
                private_key = PrivateKey.from_nsec(nsec)
            else:
                print("Using hex format")
                private_key = PrivateKey(bytes.fromhex(nsec))

            npub = private_key.public_key.bech32()
            print(f"Computed npub: {npub[:20]}...")

            print("Creating FullscreenQR intent...")
            intent = Intent(activity_class=FullscreenQR)
            intent.putExtra("receive_qr_data", npub)
            print(f"Starting FullscreenQR activity with npub: {npub[:20]}...")
            self.startActivity(intent)
        except Exception as e:
            print(f"ShowNpubQRActivity exception: {e}")
            error_screen = lv.obj()
            error_label = lv.label(error_screen)
            error_label.set_text(f"Error: {e}")
            error_label.center()
            self.setContentView(error_screen)
            import sys
            sys.print_exception(e)


class NostrApp(Activity):

    _manager = None
    events_label_current_font = 2
    events_label_fonts = [lv.font_montserrat_10, lv.font_unscii_8, lv.font_montserrat_16, lv.font_montserrat_24, lv.font_unscii_16, lv.font_montserrat_28]

    # screens:
    main_screen = None

    # widgets
    balance_label = None
    events_label = None

    def onCreate(self):
        self.prefs = SharedPreferences(self.appFullName)
        self.main_screen = lv.obj()
        self.main_screen.set_style_pad_all(10, lv.PART.MAIN)
        # Header line
        header_line = lv.line(self.main_screen)
        header_line.set_points([{'x':0,'y':35},{'x':200,'y':35}],2)
        header_line.add_flag(lv.obj.FLAG.CLICKABLE)
        # Header label showing which npub we're following
        self.balance_label = lv.label(self.main_screen)
        self.balance_label.set_text("")
        self.balance_label.align(lv.ALIGN.TOP_LEFT, 0, 0)
        self.balance_label.set_style_text_font(lv.font_montserrat_24, lv.PART.MAIN)
        self.balance_label.add_flag(lv.obj.FLAG.CLICKABLE)
        self.balance_label.set_width(DisplayMetrics.pct_of_width(100))
        # Events label
        self.events_label = lv.label(self.main_screen)
        self.events_label.set_text("")
        self.events_label.align_to(header_line,lv.ALIGN.OUT_BOTTOM_LEFT,0,10)
        self.update_events_label_font()
        self.events_label.set_width(DisplayMetrics.pct_of_width(100))
        self.events_label.add_flag(lv.obj.FLAG.CLICKABLE)
        self.events_label.add_event_cb(self.events_label_clicked,lv.EVENT.CLICKED,None)
        settings_button = lv.button(self.main_screen)
        settings_button.set_size(lv.pct(20), lv.pct(25))
        settings_button.align(lv.ALIGN.BOTTOM_RIGHT, 0, 0)
        settings_button.add_event_cb(self.settings_button_tap,lv.EVENT.CLICKED,None)
        settings_label = lv.label(settings_button)
        settings_label.set_text(lv.SYMBOL.SETTINGS)
        settings_label.set_style_text_font(lv.font_montserrat_24, lv.PART.MAIN)
        settings_label.center()
        self.setContentView(self.main_screen)

    def onStart(self, main_screen):
        self.main_ui_set_defaults()

    def onResume(self, main_screen):
        super().onResume(main_screen)
        self._manager = NostrManager.get_instance()
        cm = ConnectivityManager.get()
        cm.register_callback(self.network_changed)
        self.network_changed(cm.is_online())

    def onPause(self, main_screen):
        if self._manager:
            self._manager.set_events_updated_callback(None)
            self._manager.set_error_callback(None)
        cm = ConnectivityManager.get()
        cm.unregister_callback(self.network_changed)

    def network_changed(self, online):
        print("nostr_app.py network_changed, now:", "ONLINE" if online else "OFFLINE")
        if online:
            self.went_online()
        else:
            self.went_offline()

    def went_online(self):
        if self._manager and self._manager.is_running() and self._manager.is_connected():
            print("nostr manager is already running, nothing to do")
            return
        try:
            nsec = self.prefs.get_string("nostr_nsec")
            if not nsec:
                from nostr.key import PrivateKey
                random_key = PrivateKey()
                nsec = random_key.bech32()
                self.prefs.edit().put_string("nostr_nsec", nsec).commit()
                print(f"Generated random nsec: {nsec}")
            follow_npub = self.prefs.get_string("nostr_follow_npub")
            relay = self.prefs.get_string("nostr_relay")
        except Exception as e:
            self.error_cb(f"Couldn't read prefs: {e}")
            import sys
            sys.print_exception(e)
            return

        if not self._manager:
            self._manager = NostrManager.get_instance()

        if not self._manager.is_running():
            self._manager.start()

        self._manager.set_events_updated_callback(self.redraw_events_cb)
        self._manager.set_error_callback(self.error_cb)

        try:
            self._manager.configure_nostr(nsec, relay, follow_npub)
        except Exception as e:
            self.error_cb(f"Couldn't configure Nostr client: {e}")
            import sys
            sys.print_exception(e)
            return

        self.balance_label.set_text("Events from " + (follow_npub or "?")[:16] + "...")
        self.events_label.set_text("\nConnecting to relay.\n\nIf this takes too long, the relay might be down or something's wrong with the settings.")

    def went_offline(self):
        if self._manager:
            self._manager.set_events_updated_callback(None)
            self._manager.set_error_callback(None)
            # Don't stop the manager — it stays running and will reconnect when online
        self.events_label.set_text("WiFi is not connected, can't talk to relay...")

    def update_events_label_font(self):
        self.events_label.set_style_text_font(self.events_label_fonts[self.events_label_current_font], lv.PART.MAIN)

    def events_label_clicked(self, event):
        self.events_label_current_font = (self.events_label_current_font + 1) % len(self.events_label_fonts)
        self.update_events_label_font()

    def redraw_events_cb(self):
        events_text = ""
        mgr = NostrManager.get_instance()
        if mgr.events:
            for event in mgr.events:
                events_text += f"{str(event)}\n\n"
        else:
            events_text = "No events yet..."
        self.events_label.set_text(events_text)

    def error_cb(self, error):
        if self._manager and self._manager.is_running():
            self.events_label.set_text(str(error))

    def should_show_setting(self, setting):
        return True

    def settings_button_tap(self, event):
        intent = Intent(activity_class=SettingsActivity)
        intent.putExtra("prefs", self.prefs)
        intent.putExtra("settings", [
            {"title": "Nostr Private Key (nsec)", "key": "nostr_nsec", "placeholder": "nsec1...", "should_show": self.should_show_setting},
            {"title": "Nostr Follow Public Key (npub)", "key": "nostr_follow_npub", "placeholder": "npub1...", "should_show": self.should_show_setting},
            {"title": "Nostr Relay", "key": "nostr_relay", "placeholder": "wss://relay.example.com", "should_show": self.should_show_setting},
            {"title": "Show My Public Key (npub)", "key": "show_npub_qr", "ui": "activity", "activity_class": ShowNpubQRActivity, "dont_persist": True, "should_show": self.should_show_setting},
        ])
        self.startActivity(intent)

    def main_ui_set_defaults(self):
        self.balance_label.set_text("Welcome!")
        self.events_label.set_text(lv.SYMBOL.REFRESH)
