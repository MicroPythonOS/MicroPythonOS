import lvgl as lv

from mpos import Activity, Intent, ConnectivityManager, DisplayMetrics, FontManager, MposKeyboard, SharedPreferences, SettingsActivity
from fullscreen_qr import FullscreenQR
from nostr_service import NostrManager


# Hard-coded FRI3D NIP-28 public channel defaults.
# Channel creation event:
# nevent1qqsvcrczlp9uxaaucqah67m6qp6l5kkhwfgs2j0ycq5g9wsaszlk3wcpzamhxue69uhhyetvv9ujucm0wfc82mfwvdhk6tczyqvpzdc9flnqmagk39mrz8ct73xmuj756ts276fjthlwn75p4r9a5qcyqqqqq2sfhuvhp
CHANNEL_ID = "fccd56d3ce0b43d48c55851a8024e398b7a33b92de64976e374df69913fd482f"
CHANNEL_NAME = "fri3d"
CHANNEL_ABOUT = "Be excellent!"
DEFAULT_RELAY = "wss://relay.damus.io"


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

    # screens:
    main_screen = None

    # widgets
    title_label = None
    events_label = None
    input_textarea = None
    keyboard = None
    _channel_id = None

    def onCreate(self):
        self.prefs = SharedPreferences(self.appFullName)
        self.main_screen = lv.obj()
        self.main_screen.set_style_pad_all(0, lv.PART.MAIN)
        self.main_screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        #self.main_screen.remove_flag(lv.obj.FLAG.SCROLLABLE)

        # Header row
        header_row = lv.obj(self.main_screen)
        header_row.set_width(lv.pct(100))
        header_row.set_height(lv.SIZE_CONTENT)
        header_row.set_style_border_width(0, lv.PART.MAIN)
        header_row.set_style_pad_all(0, lv.PART.MAIN)
        header_row.set_flex_flow(lv.FLEX_FLOW.ROW)
        header_row.set_style_flex_main_place(lv.FLEX_ALIGN.SPACE_BETWEEN, lv.PART.MAIN)

        self.title_label = lv.label(header_row)
        self.title_label.set_text("")
        self.title_label.set_flex_grow(1)
        self.title_label.set_style_text_font(lv.font_montserrat_16, lv.PART.MAIN)
        self.title_label.center()

        settings_button = lv.button(header_row)
        settings_button.set_size(DisplayMetrics.pct_of_width(15), lv.SIZE_CONTENT)
        settings_button.add_event_cb(self.settings_button_tap, lv.EVENT.CLICKED, None)
        settings_label = lv.label(settings_button)
        settings_label.set_text(lv.SYMBOL.SETTINGS)
        settings_label.set_style_text_font(lv.font_montserrat_16, lv.PART.MAIN)
        settings_label.center()

        # Events label
        self.events_label = lv.label(self.main_screen)
        self.events_label.set_text("")
        self.events_label.set_flex_grow(1)
        self.events_label.set_width(lv.pct(100))
        self.events_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.events_label.set_style_text_font(FontManager.getFont(emoji=True), lv.PART.MAIN)

        # Input row
        input_row = lv.obj(self.main_screen)
        input_row.set_width(lv.pct(100))
        input_row.set_height(lv.SIZE_CONTENT)
        input_row.set_style_border_width(0, lv.PART.MAIN)
        input_row.set_style_pad_all(0, lv.PART.MAIN)
        input_row.set_flex_flow(lv.FLEX_FLOW.ROW)
        input_row.set_style_flex_main_place(lv.FLEX_ALIGN.SPACE_BETWEEN, lv.PART.MAIN)

        self.input_textarea = lv.textarea(input_row)
        self.input_textarea.set_one_line(True)
        self.input_textarea.set_width(lv.pct(75))
        self.input_textarea.set_placeholder_text("Type a message...")
        self.input_textarea.set_max_length(280)

        send_button = lv.button(input_row)
        send_button.set_size(lv.pct(15), lv.SIZE_CONTENT)
        send_button.add_event_cb(self.send_button_tap, lv.EVENT.CLICKED, None)
        send_label = lv.label(send_button)
        send_label.set_text(lv.SYMBOL.GPS)
        send_label.set_style_text_font(lv.font_montserrat_16, lv.PART.MAIN)
        send_label.center()

        # On-screen keyboard (hidden until the textarea is focused)
        self.keyboard = MposKeyboard(self.main_screen)
        self.keyboard.add_flag(lv.obj.FLAG.HIDDEN)
        self.keyboard.set_textarea(self.input_textarea)

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
            relay = self.prefs.get_string("nostr_relay") or DEFAULT_RELAY
            channel_id = self.prefs.get_string("nostr_channel_id") or CHANNEL_ID
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
            self._manager.configure_identity(nsec, relays=relay)
            if follow_npub:
                self._manager.subscribe_profile(follow_npub)
            self._manager.subscribe_channel(channel_id)
        except Exception as e:
            self.error_cb(f"Couldn't configure Nostr client: {e}")
            import sys
            sys.print_exception(e)
            return

        header_name = CHANNEL_NAME if channel_id == CHANNEL_ID else channel_id[:8]
        self.title_label.set_text(f"Channel: #{header_name}")
        self.events_label.set_text(
            "\nConnecting to relay.\n\nIf this takes too long, the relay might be down or something's wrong with the settings."
        )
        self._channel_id = channel_id

    def went_offline(self):
        if self._manager:
            self._manager.set_events_updated_callback(None)
            self._manager.set_error_callback(None)
            # Don't stop the manager — it stays running and will reconnect when online
        self.events_label.set_text("WiFi is not connected, can't talk to relay...")

    def send_button_tap(self, event):
        text = self.input_textarea.get_text().strip()
        if not text:
            return
        if not self._channel_id:
            self.error_cb("No channel configured")
            return
        try:
            NostrManager.get_instance().publish_channel_message(self._channel_id, text)
        except Exception as e:
            self.error_cb(f"Couldn't send message: {e}")
            import sys
            sys.print_exception(e)
            return
        self.input_textarea.set_text("")
        self.keyboard.add_flag(lv.obj.FLAG.HIDDEN)

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
            {"title": "Nostr Channel ID (optional)", "key": "nostr_channel_id", "placeholder": CHANNEL_ID, "should_show": self.should_show_setting},
            {"title": "Nostr Follow Public Key (npub, optional)", "key": "nostr_follow_npub", "placeholder": "npub1...", "should_show": self.should_show_setting},
            {"title": "Nostr Relay (optional)", "key": "nostr_relay", "placeholder": DEFAULT_RELAY, "should_show": self.should_show_setting},
            {"title": "Show My Public Key (npub)", "key": "show_npub_qr", "ui": "activity", "activity_class": ShowNpubQRActivity, "dont_persist": True, "should_show": self.should_show_setting},
        ])
        self.startActivity(intent)

    def main_ui_set_defaults(self):
        self.title_label.set_text(f"Channel: #{CHANNEL_NAME}")
        self.events_label.set_text(lv.SYMBOL.REFRESH)
