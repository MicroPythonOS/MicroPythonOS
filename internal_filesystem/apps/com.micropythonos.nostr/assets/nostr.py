import lvgl as lv

from mpos import Activity, Intent, ConnectivityManager, MposKeyboard, pct_of_display_width, pct_of_display_height, SharedPreferences, SettingsActivity
from mpos.ui.anim import WidgetAnimator

from fullscreen_qr import FullscreenQR

class Nostr(Activity):

    wallet = None
    receive_qr_data = None
    destination = None
    balance_mode = 0  # 0=sats, 1=bits, 2=μBTC, 3=mBTC, 4=BTC
    payments_label_current_font = 2
    payments_label_fonts = [ lv.font_montserrat_10, lv.font_unscii_8, lv.font_montserrat_16, lv.font_montserrat_24, lv.font_unscii_16, lv.font_montserrat_28_compressed, lv.font_montserrat_40]

    # screens:
    main_screen = None

    # widgets
    balance_label = None
    receive_qr = None
    payments_label = None

    # activities
    fullscreenqr = FullscreenQR() # need a reference to be able to finish() it

    def onCreate(self):
        self.prefs = SharedPreferences("com.micropythonos.nostr")
        self.main_screen = lv.obj()
        self.main_screen.set_style_pad_all(10, 0)
        # This line needs to be drawn first, otherwise it's over the balance label and steals all the clicks!
        balance_line = lv.line(self.main_screen)
        balance_line.set_points([{'x':0,'y':35},{'x':200,'y':35}],2)
        balance_line.add_flag(lv.obj.FLAG.CLICKABLE)
        self.balance_label = lv.label(self.main_screen)
        self.balance_label.set_text("")
        self.balance_label.align(lv.ALIGN.TOP_LEFT, 0, 0)
        self.balance_label.set_style_text_font(lv.font_montserrat_24, 0)
        self.balance_label.add_flag(lv.obj.FLAG.CLICKABLE)
        self.balance_label.set_width(pct_of_display_width(75)) # 100 - receive_qr
        self.balance_label.add_event_cb(self.balance_label_clicked_cb,lv.EVENT.CLICKED,None)
        self.receive_qr = lv.qrcode(self.main_screen)
        self.receive_qr.set_size(pct_of_display_width(20)) # bigger QR results in simpler code (less error correction?)
        self.receive_qr.set_dark_color(lv.color_black())
        self.receive_qr.set_light_color(lv.color_white())
        self.receive_qr.align(lv.ALIGN.TOP_RIGHT,0,0)
        self.receive_qr.set_style_border_color(lv.color_white(), 0)
        self.receive_qr.set_style_border_width(1, 0);
        self.receive_qr.add_flag(lv.obj.FLAG.CLICKABLE)
        self.receive_qr.add_event_cb(self.qr_clicked_cb,lv.EVENT.CLICKED,None)
        self.payments_label = lv.label(self.main_screen)
        self.payments_label.set_text("")
        self.payments_label.align_to(balance_line,lv.ALIGN.OUT_BOTTOM_LEFT,0,10)
        self.update_payments_label_font()
        self.payments_label.set_width(pct_of_display_width(75)) # 100 - receive_qr
        self.payments_label.add_flag(lv.obj.FLAG.CLICKABLE)
        self.payments_label.add_event_cb(self.payments_label_clicked,lv.EVENT.CLICKED,None)
        settings_button = lv.button(self.main_screen)
        settings_button.set_size(lv.pct(20), lv.pct(25))
        settings_button.align(lv.ALIGN.BOTTOM_RIGHT, 0, 0)
        settings_button.add_event_cb(self.settings_button_tap,lv.EVENT.CLICKED,None)
        settings_label = lv.label(settings_button)
        settings_label.set_text(lv.SYMBOL.SETTINGS)
        settings_label.set_style_text_font(lv.font_montserrat_24, 0)
        settings_label.center()
        if False: # send button disabled for now, not implemented
            send_button = lv.button(self.main_screen)
            send_button.set_size(lv.pct(20), lv.pct(25))
            send_button.align_to(settings_button, lv.ALIGN.OUT_TOP_MID, 0, -pct_of_display_height(2))
            send_button.add_event_cb(self.send_button_tap,lv.EVENT.CLICKED,None)
            send_label = lv.label(send_button)
            send_label.set_text(lv.SYMBOL.UPLOAD)
            send_label.set_style_text_font(lv.font_montserrat_24, 0)
            send_label.center()
        self.setContentView(self.main_screen)

    def onStart(self, main_screen):
        self.main_ui_set_defaults()

    def onResume(self, main_screen):
        super().onResume(main_screen)
        cm = ConnectivityManager.get()
        cm.register_callback(self.network_changed)
        self.network_changed(cm.is_online())

    def onPause(self, main_screen):
        if self.wallet and self.destination != FullscreenQR:
            self.wallet.stop() # don't stop the wallet for the fullscreen QR activity
        self.destination = None
        cm = ConnectivityManager.get()
        cm.unregister_callback(self.network_changed)

    def network_changed(self, online):
        print("displaywallet.py network_changed, now:", "ONLINE" if online else "OFFLINE")
        if online:
            self.went_online()
        else:
            self.went_offline()

    def went_online(self):
        if self.wallet and self.wallet.is_running():
            print("wallet is already running, nothing to do") # might have come from the QR activity
            return
        try:
            from nostr_client import NostrClient
            self.wallet = NostrClient(self.prefs.get_string("nwc_url"))
            self.wallet.static_receive_code = self.prefs.get_string("nwc_static_receive_code")
            self.redraw_static_receive_code_cb()
        except Exception as e:
            self.error_cb(f"Couldn't initialize NWC Wallet because: {e}")
            import sys
            sys.print_exception(e)
            return
        self.balance_label.set_text(lv.SYMBOL.REFRESH)
        self.payments_label.set_text(f"\nConnecting to backend.\n\nIf this takes too long, it might be down or something's wrong with the settings.")
        # by now, self.wallet can be assumed
        self.wallet.start(self.balance_updated_cb, self.redraw_payments_cb, self.redraw_static_receive_code_cb, self.error_cb)

    def went_offline(self):
        if self.wallet:
            self.wallet.stop() # don't stop the wallet for the fullscreen QR activity
        self.payments_label.set_text(f"WiFi is not connected, can't talk to wallet...")

    def update_payments_label_font(self):
        self.payments_label.set_style_text_font(self.payments_label_fonts[self.payments_label_current_font], 0)

    def payments_label_clicked(self, event):
        self.payments_label_current_font = (self.payments_label_current_font + 1) % len(self.payments_label_fonts)
        self.update_payments_label_font()

    def float_to_string(self, value):
        # Format float to string with fixed-point notation, up to 6 decimal places
        s = "{:.8f}".format(value)
        # Remove trailing zeros and decimal point if no decimals remain
        return s.rstrip("0").rstrip(".")

    def display_balance(self, balance):
         #print(f"displaying balance {balance}")
         if self.balance_mode == 0:  # sats
             #balance_text = "丰 " + str(balance) # font doesnt support it
             balance_text = str(balance) + " sat"
             if balance > 1:
                 balance_text += "s"
         elif self.balance_mode == 1:  # bits (1 bit = 100 sats)
             balance_bits = balance / 100
             balance_text = self.float_to_string(balance_bits) + " bit"
             if balance_bits != 1:
                 balance_text += "s"
         elif self.balance_mode == 2:  # micro-BTC (1 μBTC = 100 sats)
             balance_ubtc = balance / 100
             balance_text = self.float_to_string(balance_ubtc) + " micro-BTC"
         elif self.balance_mode == 3:  # milli-BTC (1 mBTC = 100000 sats)
             balance_mbtc = balance / 100000
             balance_text = self.float_to_string(balance_mbtc) + " milli-BTC"
         elif self.balance_mode == 4:  # BTC (1 BTC = 100000000 sats)
             balance_btc = balance / 100000000
             #balance_text = "₿ " + str(balance) # font doesnt support it - although it should https://fonts.google.com/specimen/Montserrat
             balance_text = self.float_to_string(balance_btc) + " BTC"
         self.balance_label.set_text(balance_text)
         #print("done displaying balance")

    def balance_updated_cb(self, sats_added=0):
        print(f"balance_updated_cb(sats_added={sats_added})")
        if self.fullscreenqr.has_foreground():
            self.fullscreenqr.finish()
        balance = self.wallet.last_known_balance
        print(f"balance: {balance}")
    
    def redraw_payments_cb(self):
        # this gets called from another thread (the wallet) so make sure it happens in the LVGL thread using lv.async_call():
        self.payments_label.set_text(str(self.wallet.payment_list))

    def redraw_static_receive_code_cb(self):
        # this gets called from another thread (the wallet) so make sure it happens in the LVGL thread using lv.async_call():
        self.receive_qr_data = self.wallet.static_receive_code
        if self.receive_qr_data:
            self.receive_qr.update(self.receive_qr_data, len(self.receive_qr_data))
        else:
            print("Warning: redraw_static_receive_code_cb() was called while self.wallet.static_receive_code is None...")

    def error_cb(self, error):
        if self.wallet and self.wallet.is_running():
            self.payments_label.set_text(str(error))

    def should_show_setting(self, setting):
        return True

    def settings_button_tap(self, event):
        intent = Intent(activity_class=SettingsActivity)
        intent.putExtra("prefs", self.prefs)
        intent.putExtra("settings", [
            {"title": "LNBits URL", "key": "lnbits_url", "placeholder": "https://demo.lnpiggy.com", "should_show": self.should_show_setting},
            {"title": "LNBits Read Key", "key": "lnbits_readkey", "placeholder": "fd92e3f8168ba314dc22e54182784045", "should_show": self.should_show_setting},
            {"title": "Optional LN Address", "key": "lnbits_static_receive_code", "placeholder": "Will be fetched if empty.", "should_show": self.should_show_setting},
            {"title": "Nost Wallet Connect", "key": "nwc_url", "placeholder": "nostr+walletconnect://69effe7b...", "should_show": self.should_show_setting},
            {"title": "Optional LN Address", "key": "nwc_static_receive_code", "placeholder": "Optional if present in NWC URL.", "should_show": self.should_show_setting},
        ])
        self.startActivity(intent)

    def main_ui_set_defaults(self):
        self.balance_label.set_text("Welcome!")
        self.payments_label.set_text(lv.SYMBOL.REFRESH)

    def balance_label_clicked_cb(self, event):
         print("Balance clicked")
         self.balance_mode = (self.balance_mode + 1) % 5
         self.display_balance(self.wallet.last_known_balance)

    def qr_clicked_cb(self, event):
        print("QR clicked")
        if not self.receive_qr_data:
            return
        self.destination = FullscreenQR
        self.startActivity(Intent(activity_class=self.fullscreenqr).putExtra("receive_qr_data", self.receive_qr_data))
