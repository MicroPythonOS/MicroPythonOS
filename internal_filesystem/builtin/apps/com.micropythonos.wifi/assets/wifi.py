import os
import time
import lvgl as lv
import _thread

from mpos.apps import Activity, Intent
from mpos.ui.keyboard import MposKeyboard

import mpos.config
from mpos.net.wifi_service import WifiService

class WiFi(Activity):

    prefs = None
    saved_access_points={}
    last_tried_ssid = ""
    last_tried_result = ""
    have_network = True
    try:
        import network
    except Exception as e:
        have_network = False

    scan_button_scan_text = "Rescan"
    scan_button_scanning_text = "Scanning..."

    scanned_ssids=[]
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
        self.aplist=lv.list(main_screen)
        self.aplist.set_size(lv.pct(100),lv.pct(75))
        self.aplist.align(lv.ALIGN.TOP_MID,0,0)
        self.error_label=lv.label(main_screen)
        self.error_label.set_text("THIS IS ERROR TEXT THAT WILL BE SET LATER")
        self.error_label.align_to(self.aplist, lv.ALIGN.OUT_BOTTOM_MID,0,0)
        self.error_label.add_flag(lv.obj.FLAG.HIDDEN)
        self.add_network_button=lv.button(main_screen)
        self.add_network_button.set_size(lv.SIZE_CONTENT,lv.pct(15))
        self.add_network_button.align(lv.ALIGN.BOTTOM_LEFT,0,0)
        self.add_network_button.add_event_cb(self.add_network_callback,lv.EVENT.CLICKED,None)
        self.add_network_button_label=lv.label(self.add_network_button)
        self.add_network_button_label.set_text("Add network")
        self.add_network_button_label.center()
        self.scan_button=lv.button(main_screen)
        self.scan_button.set_size(lv.SIZE_CONTENT,lv.pct(15))
        self.scan_button.align(lv.ALIGN.BOTTOM_RIGHT,0,0)
        self.scan_button.add_event_cb(self.scan_cb,lv.EVENT.CLICKED,None)
        self.scan_button_label=lv.label(self.scan_button)
        self.scan_button_label.set_text(self.scan_button_scan_text)
        self.scan_button_label.center()
        self.setContentView(main_screen)

    def onResume(self, screen):
        print("wifi.py onResume")
        super().onResume(screen)

        if not self.prefs:
            self.prefs = mpos.config.SharedPreferences("com.micropythonos.system.wifiservice")

        self.saved_access_points = self.prefs.get_dict("access_points")
        print(f"loaded access points from preferences: {self.saved_access_points}")
        if len(self.scanned_ssids) == 0:
            if WifiService.wifi_busy == False:
                WifiService.wifi_busy = True
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
        print("scan_networks: Scanning for Wi-Fi networks")
        if self.have_network:
            wlan=network.WLAN(network.STA_IF)
            if not wlan.isconnected(): # restart WiFi hardware in case it's in a bad state
                wlan.active(False)
                wlan.active(True)
        try:
            if self.have_network:
                networks = wlan.scan()
                self.scanned_ssids = list(set(n[0].decode() for n in networks))
            else:
                time.sleep(1)
                self.scanned_ssids = ["Home WiFi", "Pretty Fly for a Wi Fi", "Winternet is coming", "The Promised LAN"]
            print(f"scan_networks: Found networks: {self.scanned_ssids}")
        except Exception as e:
            print(f"scan_networks: Scan failed: {e}")
            self.show_error("Wi-Fi scan failed")
        # scan done:
        self.busy_scanning = False
        WifiService.wifi_busy = False
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
        print("refresh_list: Clearing current list")
        self.aplist.clean() # this causes an issue with lost taps if an ssid is clicked that has been removed
        print("refresh_list: Populating list with scanned networks")
        for ssid in set(self.scanned_ssids + list(ssid for ssid in self.saved_access_points)):
            if len(ssid) < 1 or len(ssid) > 32:
                print(f"Skipping too short or long SSID: {ssid}")
                continue
            print(f"refresh_list: Adding SSID: {ssid}")
            button=self.aplist.add_button(None,ssid)
            button.add_event_cb(lambda e, s=ssid: self.select_ssid_cb(s),lv.EVENT.CLICKED,None)
            status = ""
            if self.have_network:
                wlan=network.WLAN(network.STA_IF)
                if wlan.isconnected() and wlan.config('essid')==ssid:
                    status="connected"
            if status != "connected":
                if self.last_tried_ssid == ssid: # implies not connected because not wlan.isconnected()
                    status = self.last_tried_result
                elif ssid in self.saved_access_points:
                    status="saved"
            label=lv.label(button)
            label.set_text(status)
            label.align(lv.ALIGN.RIGHT_MID,0,0)

    def add_network_callback(self, event):
        print(f"add_network_callback clicked")
        intent = Intent(activity_class=EditNetwork)
        intent.putExtra("selected_ssid", None)
        self.startActivityForResult(intent, self.edit_network_result_callback)

    def scan_cb(self, event):
        print("scan_cb: Scan button clicked, refreshing list")
        self.start_scan_networks()

    def select_ssid_cb(self,ssid):
        print(f"select_ssid_cb: SSID selected: {ssid}")
        intent = Intent(activity_class=EditNetwork)
        intent.putExtra("selected_ssid", ssid)
        intent.putExtra("known_password", self.findSavedPassword(ssid))
        self.startActivityForResult(intent, self.edit_network_result_callback)
        
    def edit_network_result_callback(self, result):
        print(f"EditNetwork finished, result: {result}")
        if result.get("result_code") is True:
            data = result.get("data")
            if data:
                ssid = data.get("ssid")
                editor = self.prefs.edit()
                forget = data.get("forget")
                if forget:
                    try:
                        del self.saved_access_points[ssid]
                        editor.put_dict("access_points", self.saved_access_points)
                        editor.commit()
                        self.refresh_list()
                    except Exception as e:
                        print(f"WARNING: could not forget access point, maybe it wasn't remembered in the first place: {e}")
                else: # save or update
                    password = data.get("password")
                    hidden = data.get("hidden")
                    self.setPassword(ssid, password, hidden)
                    editor.put_dict("access_points", self.saved_access_points)
                    editor.commit()
                    print(f"access points: {self.saved_access_points}")
                    self.start_attempt_connecting(ssid, password)

    def start_attempt_connecting(self, ssid, password):
        print(f"start_attempt_connecting: Attempting to connect to SSID '{ssid}' with password '{password}'")
        self.scan_button.add_state(lv.STATE.DISABLED)
        self.scan_button_label.set_text("Connecting...")
        if self.busy_connecting:
            print("Not attempting connect because busy_connecting.")
        else:
            self.busy_connecting = True
            _thread.stack_size(mpos.apps.good_stack_size())
            _thread.start_new_thread(self.attempt_connecting_thread, (ssid,password))

    def attempt_connecting_thread(self, ssid, password):
        print(f"attempt_connecting_thread: Attempting to connect to SSID '{ssid}' with password '{password}'")
        result="connected"
        try:
            if self.have_network:
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
                print("Warning: not trying to connect because not self.have_network, just waiting a bit...")
                time.sleep(5)
        except Exception as e:
            print(f"attempt_connecting: Connection error: {e}")
            result=f"{e}"
            self.show_error("Connecting to {ssid} failed!")
        print(f"Connecting to {ssid} got result: {result}")
        self.last_tried_ssid = ssid
        self.last_tried_result = result
        # also do a time sync, otherwise some apps (Nostr Wallet Connect) won't work:
        if self.have_network and wlan.isconnected():
            mpos.time.sync_time()
        self.busy_connecting=False
        self.update_ui_threadsafe_if_foreground(self.scan_button_label.set_text, self.scan_button_scan_text)
        self.update_ui_threadsafe_if_foreground(self.scan_button.remove_state, lv.STATE.DISABLED)
        self.update_ui_threadsafe_if_foreground(self.refresh_list)

    def findSavedPassword(self, ssid):
        ap = self.saved_access_points.get(ssid)
        if ap:
            return ap.get("password")
        return None

    def setPassword(self, ssid, password, hidden=False):
        ap = self.saved_access_points.get(ssid)
        if ap:
            ap["password"] = password
            if hidden is True:
                ap["hidden"] = True
            return
        # if not found, then add it:
        self.saved_access_points[ssid] = { "password": password, "hidden": hidden }


class EditNetwork(Activity):

    selected_ssid = None

    # Widgets:
    ssid_ta = None
    password_ta=None
    hidden_cb = None
    keyboard=None
    connect_button=None
    cancel_button=None

    def onCreate(self):
        password_page=lv.obj()
        password_page.set_style_pad_all(0, lv.PART.MAIN)
        password_page.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        self.selected_ssid = self.getIntent().extras.get("selected_ssid")
        known_password = self.getIntent().extras.get("known_password")

        # SSID:
        if self.selected_ssid is None:
            print("No ssid selected, the user should fill it out.")
            label=lv.label(password_page)
            label.set_text(f"Network name:")
            self.ssid_ta=lv.textarea(password_page)
            self.ssid_ta.set_width(lv.pct(90))
            self.ssid_ta.set_style_margin_left(5, lv.PART.MAIN)
            self.ssid_ta.set_one_line(True)
            self.ssid_ta.set_placeholder_text("Enter the SSID")
            self.keyboard=MposKeyboard(password_page)
            self.keyboard.set_textarea(self.ssid_ta)
            self.keyboard.add_flag(lv.obj.FLAG.HIDDEN)
            
        # Password:
        label=lv.label(password_page)
        if self.selected_ssid is None:
            label.set_text("Password:")
        else:
            label.set_text(f"Password for '{self.selected_ssid}':")
        self.password_ta=lv.textarea(password_page)
        self.password_ta.set_width(lv.pct(90))
        self.password_ta.set_style_margin_left(5, lv.PART.MAIN)
        self.password_ta.set_one_line(True)
        if known_password:
            self.password_ta.set_text(known_password)
        self.password_ta.set_placeholder_text("Password")
        self.keyboard=MposKeyboard(password_page)
        self.keyboard.set_textarea(self.password_ta)
        self.keyboard.add_flag(lv.obj.FLAG.HIDDEN)

        # Hidden network:
        self.hidden_cb = lv.checkbox(password_page)
        self.hidden_cb.set_text("Hidden network (always try connecting)")
        self.hidden_cb.set_style_margin_left(5, lv.PART.MAIN)

        # Action buttons:
        buttons = lv.obj(password_page)
        buttons.set_width(lv.pct(100))
        buttons.set_height(lv.SIZE_CONTENT)
        buttons.set_style_bg_opa(lv.OPA.TRANSP, 0)
        buttons.set_style_border_width(0, lv.PART.MAIN)
        # Delete button
        if self.selected_ssid:
            self.forget_button=lv.button(buttons)
            self.forget_button.align(lv.ALIGN.LEFT_MID, 0, 0)
            self.forget_button.add_event_cb(self.forget_cb, lv.EVENT.CLICKED, None)
            label=lv.label(self.forget_button)
            label.set_text("Forget")
            label.center()
        # Close button
        self.cancel_button=lv.button(buttons)
        self.cancel_button.center()
        self.cancel_button.add_event_cb(lambda *args: self.finish(), lv.EVENT.CLICKED, None)
        label=lv.label(self.cancel_button)
        label.set_text("Close")
        label.center()
        # Connect button
        self.connect_button = lv.button(buttons)
        self.connect_button.align(lv.ALIGN.RIGHT_MID, 0, 0)
        self.connect_button.add_event_cb(self.connect_cb,lv.EVENT.CLICKED,None)
        label=lv.label(self.connect_button)
        label.set_text("Connect")
        label.center()

        self.setContentView(password_page)

    def connect_cb(self, event):
        # Validate the form
        if self.selected_ssid is None:
            new_ssid = self.ssid_ta.get_text()
            if not new_ssid:
                self.ssid_ta.set_style_bg_color(lv.color_hex(0xff8080), 0)
                return
            else:
                self.selected_ssid = new_ssid
        # If a password is filled, then it should be at least 8 characters:
        pwd = self.password_ta.get_text()
        if len(pwd) > 0 and len(pwd) < 8:
            self.password_ta.set_style_bg_color(lv.color_hex(0xff8080), 0)
            return

        # Return the result
        hidden_checked = True if self.hidden_cb.get_state() & lv.STATE.CHECKED else False
        self.setResult(True, {"ssid": self.selected_ssid, "password": pwd, "hidden": hidden_checked})
        self.finish()

    def forget_cb(self, event):
        self.setResult(True, {"ssid": self.selected_ssid, "forget": True})
        self.finish()
