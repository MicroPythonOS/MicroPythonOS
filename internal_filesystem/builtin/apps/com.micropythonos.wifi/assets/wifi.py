import ujson
import os
import time
import lvgl as lv
import _thread

from mpos.apps import Activity, Intent

import mpos.config
import mpos.ui.anim
import mpos.ui.theme
import mpos.wifi

have_network = True
try:
    import network
except Exception as e:
    have_network = False

# Global variables because they're used by multiple Activities:
access_points={}
last_tried_ssid = ""
last_tried_result = ""

# This is basically the wifi settings app
class WiFi(Activity):

    scan_button_scan_text = "Rescan"
    scan_button_scanning_text = "Scanning..."

    ssids=[]
    busy_scanning = False
    busy_connecting = False
    error_timer = None

    # Widgets:
    aplist = None
    error_label = None
    scan_button = None
    scan_button_label = None

    def onCreate(self):
        print("wifi.py onCreate")
        main_screen = lv.obj()
        main_screen.set_style_pad_all(15, 0)
        print("create_ui: Creating list widget")
        self.aplist=lv.list(main_screen)
        self.aplist.set_size(lv.pct(100),lv.pct(75))
        self.aplist.align(lv.ALIGN.TOP_MID,0,0)
        print("create_ui: Creating error label")
        self.error_label=lv.label(main_screen)
        self.error_label.set_text("THIS IS ERROR TEXT THAT WILL BE SET LATER")
        self.error_label.align_to(self.aplist, lv.ALIGN.OUT_BOTTOM_MID,0,0)
        self.error_label.add_flag(lv.obj.FLAG.HIDDEN)
        print("create_ui: Creating Scan button")
        self.scan_button=lv.button(main_screen)
        self.scan_button.set_size(lv.SIZE_CONTENT,lv.pct(15))
        self.scan_button.align(lv.ALIGN.BOTTOM_MID,0,0)
        self.scan_button_label=lv.label(self.scan_button)
        self.scan_button_label.set_text(self.scan_button_scan_text)
        self.scan_button_label.center()
        self.scan_button.add_event_cb(self.scan_cb,lv.EVENT.CLICKED,None)
        self.setContentView(main_screen)

    def onResume(self, screen):
        print("wifi.py onResume")
        super().onResume(screen)
        global access_points
        access_points = mpos.config.SharedPreferences("com.micropythonos.system.wifiservice").get_dict("access_points")
        if len(self.ssids) == 0:
            if mpos.wifi.WifiService.wifi_busy == False:
                mpos.wifi.WifiService.wifi_busy = True
                self.start_scan_networks()
            else:
                self.show_error("Wifi is busy, please try again later.")

    def show_error(self, message):
        # Schedule UI updates because different thread
        print(f"show_error: Displaying error: {message}")
        self.update_ui_threadsafe_if_foreground(self.error_label.set_text, message)
        self.update_ui_threadsafe_if_foreground(self.error_label.remove_flag, lv.obj.FLAG.HIDDEN)
        self.error_timer = lv.timer_create(self.hide_error,5000,None)
        self.error_timer.set_repeat_count(1)

    def hide_error(self, timer):
        self.update_ui_threadsafe_if_foreground(self.error_label.add_flag,lv.obj.FLAG.HIDDEN)

    def scan_networks_thread(self):
        global have_network
        print("scan_networks: Scanning for Wi-Fi networks")
        if have_network:
            wlan=network.WLAN(network.STA_IF)
            if not wlan.isconnected(): # restart WiFi hardware in case it's in a bad state
                wlan.active(False)
                wlan.active(True)
        try:
            if have_network:
                networks = wlan.scan()
                self.ssids = list(set(n[0].decode() for n in networks))
            else:
                time.sleep(1)
                self.ssids = ["Home WiFi", "Pretty Fly for a Wi Fi", "Winternet is coming", "The Promised LAN"]
            print(f"scan_networks: Found networks: {self.ssids}")
        except Exception as e:
            print(f"scan_networks: Scan failed: {e}")
            self.show_error("Wi-Fi scan failed")
        # scan done:
        self.busy_scanning = False
        mpos.wifi.WifiService.wifi_busy = False
        self.update_ui_threadsafe_if_foreground(self.scan_button_label.set_text,self.scan_button_scan_text)
        self.update_ui_threadsafe_if_foreground(self.scan_button.remove_state, lv.STATE.DISABLED)
        self.update_ui_threadsafe_if_foreground(self.refresh_list)

    def start_scan_networks(self):
        if self.busy_scanning:
            print("Not scanning for networks because already busy_scanning.")
            return
        self.busy_scanning = True
        self.scan_button.add_state(lv.STATE.DISABLED)
        self.scan_button_label.set_text(self.scan_button_scanning_text)
        _thread.stack_size(mpos.apps.good_stack_size())
        _thread.start_new_thread(self.scan_networks_thread, ())

    def refresh_list(self):
        global have_network
        print("refresh_list: Clearing current list")
        self.aplist.clean() # this causes an issue with lost taps if an ssid is clicked that has been removed
        print("refresh_list: Populating list with scanned networks")
        for ssid in self.ssids:
            if len(ssid) < 1 or len(ssid) > 32:
                print(f"Skipping too short or long SSID: {ssid}")
                continue
            print(f"refresh_list: Adding SSID: {ssid}")
            button=self.aplist.add_button(None,ssid)
            button.add_event_cb(lambda e, s=ssid: self.select_ssid_cb(s),lv.EVENT.CLICKED,None)
            status = ""
            if have_network:
                wlan=network.WLAN(network.STA_IF)
                if wlan.isconnected() and wlan.config('essid')==ssid:
                    status="connected"
            if status != "connected":
                if last_tried_ssid == ssid: # implies not connected because not wlan.isconnected()
                    status=last_tried_result
                elif ssid in access_points:
                    status="saved"
            label=lv.label(button)
            label.set_text(status)
            label.align(lv.ALIGN.RIGHT_MID,0,0)

    def scan_cb(self, event):
        print("scan_cb: Scan button clicked, refreshing list")
        self.start_scan_networks()

    def select_ssid_cb(self,ssid):
        print(f"select_ssid_cb: SSID selected: {ssid}")
        intent = Intent(activity_class=PasswordPage)
        intent.putExtra("selected_ssid", ssid)
        self.startActivityForResult(intent, self.password_page_result_cb)
        
    def password_page_result_cb(self, result):
        print(f"PasswordPage finished, result: {result}")
        if result.get("result_code"):
            data = result.get("data")
            if data:
                self.start_attempt_connecting(data.get("ssid"), data.get("password"))

    def start_attempt_connecting(self, ssid, password):
        print(f"start_attempt_connecting: Attempting to connect to SSID '{ssid}' with password '{password}'")
        self.scan_button.add_state(lv.STATE.DISABLED)
        self.scan_button_label.set_text(f"Connecting to '{ssid}'")
        if self.busy_connecting:
            print("Not attempting connect because busy_connecting.")
        else:
            self.busy_connecting = True
            _thread.stack_size(mpos.apps.good_stack_size())
            _thread.start_new_thread(self.attempt_connecting_thread, (ssid,password))

    def attempt_connecting_thread(self, ssid, password):
        global last_tried_ssid, last_tried_result, have_network
        print(f"attempt_connecting_thread: Attempting to connect to SSID '{ssid}' with password '{password}'")
        result="connected"
        try:
            if have_network:
                wlan=network.WLAN(network.STA_IF)
                wlan.disconnect()
                wlan.connect(ssid,password)
                for i in range(10):
                    if wlan.isconnected():
                        print(f"attempt_connecting: Connected to {ssid} after {i+1} seconds")
                        break
                    print(f"attempt_connecting: Waiting for connection, attempt {i+1}/10")
                    time.sleep(1)
                if not wlan.isconnected():
                    result="timeout"
            else:
                print("Warning: not trying to connect because not have_network, just waiting a bit...")
                time.sleep(5)
        except Exception as e:
            print(f"attempt_connecting: Connection error: {e}")
            result=f"{e}"
            self.show_error("Connecting to {ssid} failed!")
        print(f"Connecting to {ssid} got result: {result}")
        last_tried_ssid = ssid
        last_tried_result = result
        # also do a time sync, otherwise some apps (Nostr Wallet Connect) won't work:
        if have_network and wlan.isconnected():
            mpos.time.sync_time()
        self.busy_connecting=False
        self.update_ui_threadsafe_if_foreground(self.scan_button_label.set_text, self.scan_button_scan_text)
        self.update_ui_threadsafe_if_foreground(self.scan_button.remove_state, lv.STATE.DISABLED)
        self.update_ui_threadsafe_if_foreground(self.refresh_list)



class PasswordPage(Activity):
    # Would be good to add some validation here so the password is not too short etc...

    selected_ssid = None

    # Widgets:
    password_ta=None
    keyboard=None
    connect_button=None
    cancel_button=None

    def onCreate(self):
        self.selected_ssid = self.getIntent().extras.get("selected_ssid")
        print("PasswordPage: Creating new password page")
        password_page=lv.obj()
        print(f"show_password_page: Creating label for SSID: {self.selected_ssid}")
        label=lv.label(password_page)
        label.set_text(f"Password for {self.selected_ssid}")
        label.align(lv.ALIGN.TOP_MID,0,5)
        print("PasswordPage: Creating password textarea")
        self.password_ta=lv.textarea(password_page)
        self.password_ta.set_width(lv.pct(90))
        self.password_ta.set_one_line(True)
        self.password_ta.align_to(label, lv.ALIGN.OUT_BOTTOM_MID, 0, 0)
        self.password_ta.add_event_cb(lambda *args: self.show_keyboard(), lv.EVENT.CLICKED, None)
        print("PasswordPage: Creating Connect button")
        self.connect_button=lv.button(password_page)
        self.connect_button.set_size(100,40)
        self.connect_button.align(lv.ALIGN.BOTTOM_LEFT,10,-40)
        self.connect_button.add_event_cb(self.connect_cb,lv.EVENT.CLICKED,None)
        label=lv.label(self.connect_button)
        label.set_text("Connect")
        label.center()
        print("PasswordPage: Creating Cancel button")
        self.cancel_button=lv.button(password_page)
        self.cancel_button.set_size(100,40)
        self.cancel_button.align(lv.ALIGN.BOTTOM_RIGHT,-10,-40)
        self.cancel_button.add_event_cb(self.cancel_cb,lv.EVENT.CLICKED,None)
        label=lv.label(self.cancel_button)
        label.set_text("Close")
        label.center()
        pwd = self.findSavedPassword(self.selected_ssid)
        if pwd:
            self.password_ta.set_text(pwd)
        self.password_ta.set_placeholder_text("Password")
        print("PasswordPage: Creating keyboard (hidden by default)")
        self.keyboard=lv.keyboard(password_page)
        self.keyboard.align(lv.ALIGN.BOTTOM_MID,0,0)
        self.keyboard.set_textarea(self.password_ta)
        self.keyboard.set_style_min_height(160, 0)
        mpos.ui.theme.fix_keyboard_button_style(self.keyboard)  # Fix button visibility in light mode
        self.keyboard.add_event_cb(lambda *args: self.hide_keyboard(), lv.EVENT.READY, None)
        self.keyboard.add_event_cb(lambda *args: self.hide_keyboard(), lv.EVENT.CANCEL, None)
        self.keyboard.add_flag(lv.obj.FLAG.HIDDEN)
        self.keyboard.add_event_cb(self.handle_keyboard_events, lv.EVENT.VALUE_CHANGED, None)
        print("PasswordPage: Loading password page")
        self.setContentView(password_page)

    def onStop(self, screen):
        self.hide_keyboard()

    def connect_cb(self, event):
        global access_points
        print("connect_cb: Connect button clicked")
        password=self.password_ta.get_text()
        print(f"connect_cb: Got password: {password}")
        self.setPassword(self.selected_ssid, password)
        print(f"connect_cb: Updated access_points: {access_points}")
        editor = mpos.config.SharedPreferences("com.micropythonos.system.wifiservice").edit()
        editor.put_dict("access_points", access_points)
        editor.commit()
        self.setResult(True, {"ssid": self.selected_ssid, "password": password})
        print("connect_cb: Restoring main_screen")
        self.finish()
    
    def cancel_cb(self, event):
        print("cancel_cb: Cancel button clicked")
        self.finish()

    def show_keyboard(self):
        self.connect_button.add_flag(lv.obj.FLAG.HIDDEN)
        self.cancel_button.add_flag(lv.obj.FLAG.HIDDEN)
        mpos.ui.anim.smooth_show(self.keyboard)
        focusgroup = lv.group_get_default()
        if focusgroup:
            focusgroup.focus_next() # move the focus to the keyboard to save the user a "next" button press (optional but nice)

    def hide_keyboard(self):
        mpos.ui.anim.smooth_hide(self.keyboard)
        self.connect_button.remove_flag(lv.obj.FLAG.HIDDEN)
        self.cancel_button.remove_flag(lv.obj.FLAG.HIDDEN)

    def handle_keyboard_events(self, event):
        target_obj=event.get_target_obj() # keyboard
        button = target_obj.get_selected_button()
        text = target_obj.get_button_text(button)
        #print(f"button {button} and text {text}")
        if text == lv.SYMBOL.NEW_LINE:
            print("Newline pressed, closing the keyboard...")
            self.hide_keyboard()

    @staticmethod
    def setPassword(ssid, password):
        global access_points
        ap = access_points.get(ssid)
        if ap:
            ap["password"] = password
            return
        # if not found, then add it:
        access_points[ssid] = { "password": password }

    @staticmethod
    def findSavedPassword(ssid):
        if not access_points:
            return None
        ap = access_points.get(ssid)
        if ap:
            return ap.get("password")
        return None
