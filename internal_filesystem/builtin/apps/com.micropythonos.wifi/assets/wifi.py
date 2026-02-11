import time
import lvgl as lv
import _thread

from mpos import Activity, Intent, MposKeyboard, WifiService, CameraActivity, DisplayMetrics, CameraManager, TaskManager

class WiFi(Activity):
    """
    WiFi settings app for MicroPythonOS.
    
    This is a pure UI layer - all WiFi operations are delegated to WifiService.
    """

    last_tried_ssid = ""
    last_tried_result = ""

    scan_button_scan_text = "Rescan"
    scan_button_scanning_text = "Scanning..."

    scanned_ssids = []
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
        main_screen.set_style_pad_all(15, lv.PART.MAIN)
        self.aplist = lv.list(main_screen)
        self.aplist.set_size(lv.pct(100), lv.pct(75))
        self.aplist.align(lv.ALIGN.TOP_MID, 0, 0)
        self.error_label = lv.label(main_screen)
        self.error_label.set_text("THIS IS ERROR TEXT THAT WILL BE SET LATER")
        self.error_label.align_to(self.aplist, lv.ALIGN.OUT_BOTTOM_MID, 0, 0)
        self.error_label.add_flag(lv.obj.FLAG.HIDDEN)
        self.add_network_button = lv.button(main_screen)
        self.add_network_button.set_size(lv.SIZE_CONTENT, lv.pct(15))
        self.add_network_button.align(lv.ALIGN.BOTTOM_LEFT, 0, 0)
        self.add_network_button.add_event_cb(self.add_network_callback, lv.EVENT.CLICKED, None)
        self.add_network_button_label = lv.label(self.add_network_button)
        self.add_network_button_label.set_text("Add network")
        self.add_network_button_label.center()
        self.scan_button = lv.button(main_screen)
        self.scan_button.set_size(lv.SIZE_CONTENT, lv.pct(15))
        self.scan_button.align(lv.ALIGN.BOTTOM_RIGHT, 0, 0)
        self.scan_button.add_event_cb(self.scan_cb, lv.EVENT.CLICKED, None)
        self.scan_button_label = lv.label(self.scan_button)
        self.scan_button_label.set_text(self.scan_button_scan_text)
        self.scan_button_label.center()
        self.setContentView(main_screen)

    def onResume(self, screen):
        print("wifi.py onResume")
        super().onResume(screen)

        # Ensure WifiService has loaded saved networks
        WifiService.get_saved_networks()

        if len(self.scanned_ssids) == 0:
            if not WifiService.is_busy():
                self.start_scan_networks()
            else:
                self.show_error("Wifi is busy, please try again later.")

    def show_error(self, message):
        # Schedule UI updates because different thread
        print(f"show_error: Displaying error: {message}")
        self.update_ui_threadsafe_if_foreground(self.error_label.set_text, message)
        self.update_ui_threadsafe_if_foreground(self.error_label.remove_flag, lv.obj.FLAG.HIDDEN)
        self.error_timer = lv.timer_create(self.hide_error, 5000, None)
        self.error_timer.set_repeat_count(1)

    def hide_error(self, timer):
        self.update_ui_threadsafe_if_foreground(self.error_label.add_flag, lv.obj.FLAG.HIDDEN)

    def scan_networks_thread(self):
        print("scan_networks: Scanning for Wi-Fi networks")
        try:
            self.scanned_ssids = WifiService.scan_networks()
            print(f"scan_networks: Found networks: {self.scanned_ssids}")
        except Exception as e:
            print(f"scan_networks: Scan failed: {e}")
            self.show_error("Wi-Fi scan failed")
        # scan done - WifiService.scan_networks() manages wifi_busy flag internally
        self.busy_scanning = False
        self.update_ui_threadsafe_if_foreground(self.scan_button_label.set_text, self.scan_button_scan_text)
        self.update_ui_threadsafe_if_foreground(self.scan_button.remove_state, lv.STATE.DISABLED)
        self.update_ui_threadsafe_if_foreground(self.refresh_list)

    def start_scan_networks(self):
        if self.busy_scanning:
            print("Not scanning for networks because already busy_scanning.")
            return
        self.busy_scanning = True
        self.scan_button.add_state(lv.STATE.DISABLED)
        self.scan_button_label.set_text(self.scan_button_scanning_text)
        _thread.stack_size(TaskManager.good_stack_size())
        _thread.start_new_thread(self.scan_networks_thread, ())

    def refresh_list(self):
        print("refresh_list: Clearing current list")
        self.aplist.clean()  # this causes an issue with lost taps if an ssid is clicked that has been removed
        print("refresh_list: Populating list with scanned networks")
        
        # Combine scanned SSIDs with saved networks
        saved_networks = WifiService.get_saved_networks()
        all_ssids = set(self.scanned_ssids + saved_networks)
        
        for ssid in all_ssids:
            if len(ssid) < 1 or len(ssid) > 32:
                print(f"Skipping too short or long SSID: {ssid}")
                continue
            print(f"refresh_list: Adding SSID: {ssid}")
            button = self.aplist.add_button(None, ssid)
            button.add_event_cb(lambda e, s=ssid: self.select_ssid_cb(s), lv.EVENT.CLICKED, None)
            
            # Determine status
            status = ""
            current_ssid = WifiService.get_current_ssid()
            if current_ssid == ssid:
                status = "connected"
            elif self.last_tried_ssid == ssid:
                # Show last connection attempt result
                status = self.last_tried_result
            elif ssid in saved_networks:
                status = "saved"
            
            label = lv.label(button)
            label.set_text(status)
            label.align(lv.ALIGN.RIGHT_MID, 0, 0)

    def add_network_callback(self, event):
        print(f"add_network_callback clicked")
        intent = Intent(activity_class=EditNetwork)
        intent.putExtra("selected_ssid", None)
        self.startActivityForResult(intent, self.edit_network_result_callback)

    def scan_cb(self, event):
        print("scan_cb: Scan button clicked, refreshing list")
        self.start_scan_networks()

    def select_ssid_cb(self, ssid):
        print(f"select_ssid_cb: SSID selected: {ssid}")
        intent = Intent(activity_class=EditNetwork)
        intent.putExtra("selected_ssid", ssid)
        intent.putExtra("known_password", WifiService.get_network_password(ssid))
        intent.putExtra("hidden", WifiService.get_network_hidden(ssid))
        self.startActivityForResult(intent, self.edit_network_result_callback)

    def edit_network_result_callback(self, result):
        print(f"EditNetwork finished, result: {result}")
        if result.get("result_code") is True:
            data = result.get("data")
            if data:
                ssid = data.get("ssid")
                forget = data.get("forget")
                if forget:
                    WifiService.forget_network(ssid)
                    self.refresh_list()
                else:
                    # Save or update the network
                    password = data.get("password")
                    hidden = data.get("hidden")
                    WifiService.save_network(ssid, password, hidden)
                    self.start_attempt_connecting(ssid, password)

    def start_attempt_connecting(self, ssid, password):
        print(f"start_attempt_connecting: Attempting to connect to SSID '{ssid}' with password '{password}'")
        self.scan_button.add_state(lv.STATE.DISABLED)
        self.scan_button_label.set_text("Connecting...")
        if self.busy_connecting:
            print("Not attempting connect because busy_connecting.")
        else:
            self.busy_connecting = True
            _thread.stack_size(TaskManager.good_stack_size())
            _thread.start_new_thread(self.attempt_connecting_thread, (ssid, password))

    def attempt_connecting_thread(self, ssid, password):
        print(f"attempt_connecting_thread: Attempting to connect to SSID '{ssid}'")
        result = "connected"
        try:
            if WifiService.attempt_connecting(ssid, password):
                result = "connected"
            else:
                result = "timeout"
        except Exception as e:
            print(f"attempt_connecting: Connection error: {e}")
            result = f"{e}"
            self.show_error(f"Connecting to {ssid} failed!")
        
        print(f"Connecting to {ssid} got result: {result}")
        self.last_tried_ssid = ssid
        self.last_tried_result = result
        
        # Note: Time sync is handled by WifiService.attempt_connecting()
        
        self.busy_connecting = False
        self.update_ui_threadsafe_if_foreground(self.scan_button_label.set_text, self.scan_button_scan_text)
        self.update_ui_threadsafe_if_foreground(self.scan_button.remove_state, lv.STATE.DISABLED)
        self.update_ui_threadsafe_if_foreground(self.refresh_list)


class EditNetwork(Activity):

    selected_ssid = None

    # Widgets:
    ssid_ta = None
    password_ta = None
    hidden_cb = None
    keyboard = None
    connect_button = None
    cancel_button = None
    forget_button = None

    action_button_label_forget = "Forget"
    action_button_label_scanqr = "Scan QR"

    def onCreate(self):
        password_page = lv.obj()
        password_page.set_style_pad_all(0, lv.PART.MAIN)
        password_page.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        self.selected_ssid = self.getIntent().extras.get("selected_ssid")
        known_password = self.getIntent().extras.get("known_password")
        known_hidden = self.getIntent().extras.get("hidden", False)

        # SSID:
        if self.selected_ssid is None:
            print("No ssid selected, the user should fill it out.")
            label = lv.label(password_page)
            label.set_text(f"Network name:")
            self.ssid_ta = lv.textarea(password_page)
            self.ssid_ta.set_width(lv.pct(100))
            self.ssid_ta.set_style_margin_left(DisplayMetrics.pct_of_width(2), lv.PART.MAIN)
            self.ssid_ta.set_style_margin_right(DisplayMetrics.pct_of_width(2), lv.PART.MAIN)
            self.ssid_ta.set_one_line(True)
            self.ssid_ta.set_placeholder_text("Enter the SSID")
            self.keyboard = MposKeyboard(password_page)
            self.keyboard.set_textarea(self.ssid_ta)
            self.keyboard.add_flag(lv.obj.FLAG.HIDDEN)

        # Password:
        label = lv.label(password_page)
        if self.selected_ssid is None:
            label.set_text("Password:")
        else:
            label.set_text(f"Password for '{self.selected_ssid}':")
        self.password_ta = lv.textarea(password_page)
        self.password_ta.set_width(lv.pct(100))
        self.password_ta.set_style_margin_left(DisplayMetrics.pct_of_width(2), lv.PART.MAIN)
        self.password_ta.set_style_margin_right(DisplayMetrics.pct_of_width(2), lv.PART.MAIN)
        self.password_ta.set_one_line(True)
        if known_password:
            self.password_ta.set_text(known_password)
        self.password_ta.set_placeholder_text("Password")
        self.keyboard = MposKeyboard(password_page)
        self.keyboard.set_textarea(self.password_ta)
        self.keyboard.add_flag(lv.obj.FLAG.HIDDEN)

        # Hidden network:
        self.hidden_cb = lv.checkbox(password_page)
        self.hidden_cb.set_text("Hidden network (always try connecting)")
        # doesnt work: self.hidden_cb.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.hidden_cb.set_style_margin_left(DisplayMetrics.pct_of_width(2), lv.PART.MAIN)
        if known_hidden:
            self.hidden_cb.set_state(lv.STATE.CHECKED, True)

        # Action buttons:
        buttons = lv.obj(password_page)
        buttons.set_width(lv.pct(100))
        buttons.set_height(lv.SIZE_CONTENT)
        buttons.set_style_bg_opa(lv.OPA.TRANSP, lv.PART.MAIN)
        buttons.set_style_border_width(0, lv.PART.MAIN)
        buttons.set_style_pad_all(0, lv.PART.MAIN)
        # Forget / Scan QR button
        self.forget_button = lv.button(buttons)
        self.forget_button.align(lv.ALIGN.LEFT_MID, 0, 0)
        self.forget_button.add_event_cb(self.forget_cb, lv.EVENT.CLICKED, None)
        label = lv.label(self.forget_button)
        label.center()
        if self.selected_ssid:
            label.set_text(self.action_button_label_forget)
        else:
            if CameraManager.has_camera():
                label.set_text(self.action_button_label_scanqr)
            else:
                self.forget_button.add_flag(lv.obj.FLAG.HIDDEN)
        # Close button
        self.cancel_button = lv.button(buttons)
        self.cancel_button.center()
        self.cancel_button.set_style_margin_top(5, lv.PART.MAIN)
        self.cancel_button.set_style_margin_bottom(5, lv.PART.MAIN)
        self.cancel_button.add_event_cb(lambda *args: self.finish(), lv.EVENT.CLICKED, None)
        label = lv.label(self.cancel_button)
        label.set_text("Close")
        label.center()
        # Connect button
        self.connect_button = lv.button(buttons)
        self.connect_button.align(lv.ALIGN.RIGHT_MID, 0, 0)
        self.connect_button.add_event_cb(self.connect_cb, lv.EVENT.CLICKED, None)
        label = lv.label(self.connect_button)
        label.set_text("Connect")
        label.center()

        self.setContentView(password_page)

    def connect_cb(self, event):
        # Validate the form
        if self.selected_ssid is None:
            new_ssid = self.ssid_ta.get_text()
            if not new_ssid:
                self.ssid_ta.set_style_bg_color(lv.color_hex(0xff8080), lv.PART.MAIN)
                return
            else:
                self.selected_ssid = new_ssid
        # If a password is filled, then it should be at least 8 characters:
        pwd = self.password_ta.get_text()
        if len(pwd) > 0 and len(pwd) < 8:
            self.password_ta.set_style_bg_color(lv.color_hex(0xff8080), lv.PART.MAIN)
            return

        # Return the result
        hidden_checked = True if self.hidden_cb.get_state() & lv.STATE.CHECKED else False
        self.setResult(True, {"ssid": self.selected_ssid, "password": pwd, "hidden": hidden_checked})
        self.finish()

    def forget_cb(self, event):
        label = self.forget_button.get_child(0)
        if not label:
            return
        action = label.get_text()
        print(f"{action} button clicked")
        if action == self.action_button_label_forget:
            print("Closing Activity")
            self.setResult(True, {"ssid": self.selected_ssid, "forget": True})
            self.finish()
        else:
            print("Opening CameraApp")
            self.startActivityForResult(Intent(activity_class=CameraActivity).putExtra("scanqr_intent", True), self.gotqr_result_callback)

    def gotqr_result_callback(self, result):
        print(f"QR capture finished, result: {result}")
        if result.get("result_code"):
            data = result.get("data")
            print(f"Setting textarea data: {data}")
            authentication_type, ssid, password, hidden = self.decode_wifi_qr_code(data)
            if ssid and self.ssid_ta: # not always present
                self.ssid_ta.set_text(ssid)
            if password:
                self.password_ta.set_text(password)
            if hidden is True:
                self.hidden_cb.set_state(lv.STATE.CHECKED, True)
            elif hidden is False:
                self.hidden_cb.remove_state(lv.STATE.CHECKED)

    @staticmethod
    def decode_wifi_qr_code(to_decode):
        """
        Decode a WiFi QR code string in the format:
        WIFI:T:WPA;S:SSID;P:PASSWORD;H:hidden;
        
        Returns: (authentication_type, ssid, password, hidden)
        """
        print(f"decoding {to_decode}")
        
        # Initialize return values
        authentication_type = "WPA"
        ssid = None
        password = None
        hidden = False
        
        try:
            # Remove the "WIFI:" prefix if present
            if to_decode.startswith("WIFI:"):
                to_decode = to_decode[5:]
            
            # Split by semicolon to get key-value pairs
            pairs = to_decode.split(";")
            
            for pair in pairs:
                if not pair:  # Skip empty strings
                    continue
                
                # Split by colon to get key and value
                if ":" not in pair:
                    continue
                
                key, value = pair.split(":", 1)
                
                if key == "T":
                    # Authentication type (WPA, WEP, nopass, etc.)
                    authentication_type = value
                elif key == "S":
                    # SSID (network name)
                    ssid = value
                elif key == "P":
                    # Password
                    password = value
                elif key == "H":
                    # Hidden network (true/false)
                    hidden = value.lower() in ("true", "1", "yes")
        
        except Exception as e:
            print(f"Error decoding WiFi QR code: {e}")
        
        return authentication_type, ssid, password, hidden