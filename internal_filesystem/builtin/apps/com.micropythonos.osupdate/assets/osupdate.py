import lvgl as lv
import requests
import ujson
import time
import _thread

from mpos.apps import Activity
import mpos.info
import mpos.ui

class OSUpdate(Activity):

    keep_running = True

    # Widgets:
    install_button = None
    main_screen = None
    progress_label = None
    progress_bar = None

    def onCreate(self):
        self.main_screen = lv.obj()
        self.main_screen.set_style_pad_all(mpos.ui.pct_of_display_width(2), 0)
        self.install_button = lv.button(self.main_screen)
        self.install_button.align(lv.ALIGN.TOP_RIGHT, 0, mpos.ui.topmenu.NOTIFICATION_BAR_HEIGHT)
        self.install_button.add_state(lv.STATE.DISABLED) # button will be enabled if there is an update available
        self.install_button.set_size(lv.SIZE_CONTENT, lv.pct(25))
        install_label = lv.label(self.install_button)
        install_label.set_text("Update OS")
        install_label.center()
        self.status_label = lv.label(self.main_screen)
        self.status_label.align(lv.ALIGN.TOP_LEFT,0,mpos.ui.topmenu.NOTIFICATION_BAR_HEIGHT)
        self.setContentView(self.main_screen)

    def onStart(self, screen):
        network_connected = True
        try:
            import network
            network_connected = network.WLAN(network.STA_IF).isconnected()
        except Exception as e:
            print("Warning: could not check WLAN status:", str(e))
        
        if not network_connected:
            self.status_label.set_text("Error: WiFi is not connected.")
        else:
            print("Showing update info...")
            self.show_update_info()

    def onStop(self, screen):
        self.keep_running = False # this is checked by the update_with_lvgl thread

    def show_update_info(self):
        self.status_label.set_text("Checking for OS updates...")
        url = "https://updates.micropythonos.com/osupdate.json"
        print(f"OSUpdate: fetching {url}")
        try:
            print("doing requests.get()")
            # Download the JSON
            response = requests.get(url)
            # Check if request was successful
            if response.status_code == 200:
                # Parse JSON
                osupdate = ujson.loads(response.text)
                # Access attributes
                version = osupdate["version"]
                download_url = osupdate["download_url"]
                changelog = osupdate["changelog"]
                # Print the values
                print("Version:", version)
                print("Download URL:", download_url)
                print("Changelog:", changelog)
                self.handle_update_info(version, download_url, changelog)
            else:
                print("Failed to download JSON. Status code:", response.status_code)
            # Close response
            response.close()
        except Exception as e:
            print("Error:", str(e))
    
    def handle_update_info(self, version, download_url, changelog):
        label = f"Installed OS version: {mpos.info.CURRENT_OS_VERSION}\n"
        if compare_versions(version, mpos.info.CURRENT_OS_VERSION):
        #if True: # for testing
            label += "Available new"
            self.install_button.remove_state(lv.STATE.DISABLED)
            self.install_button.add_event_cb(lambda e, u=download_url: self.install_button_click(u), lv.EVENT.CLICKED, None)
        else:
            label += "isn't older than latest"
        label += f" version: {version}\n\nDetails:\n\n{changelog}"
        self.status_label.set_text(label)


    def install_button_click(self, download_url):
        print(f"install_button_click for url {download_url}")
        self.install_button.add_state(lv.STATE.DISABLED) # button will be enabled if there is an update available
        self.status_label.set_text("Update in progress.\nNavigate away to cancel.")
        self.progress_label = lv.label(self.main_screen)
        self.progress_label.set_text("OS Update: 0.00%")
        self.progress_label.align(lv.ALIGN.CENTER, 0, 0)
        self.progress_bar = lv.bar(self.main_screen)
        self.progress_bar.set_size(200, 20)
        self.progress_bar.align(lv.ALIGN.BOTTOM_MID, 0, -50)
        self.progress_bar.set_range(0, 100)
        self.progress_bar.set_value(0, False)
        try:
            _thread.stack_size(mpos.apps.good_stack_size())
            _thread.start_new_thread(self.update_with_lvgl, (download_url,))
        except Exception as e:
            print("Could not start update_with_lvgl thread: ", e)

    def progress_callback(self, percent):
        print(f"OTA Update: {percent:.1f}%")
        lv.async_call(lambda l: self.progress_label.set_text(f"OTA Update: {percent:.2f}%"), None)
        lv.async_call(lambda l: self.progress_bar.set_value(int(percent), True), None)
        time.sleep_ms(100)

    # Custom OTA update with LVGL progress
    def update_with_lvgl(self, url):
        simulate = False
        try:
            from esp32 import Partition
            #current_partition = Partition(Partition.RUNNING)
            #print(f"Current partition: {current_partition}")
            #next_partition = current_partition.get_next_update()
            #print(f"Next partition: {next_partition}")
            current = Partition(Partition.RUNNING)
            next_partition = current.get_next_update()
            #import ota.update
            #import ota.status
            #ota.status.status()
        except Exception as e:
            print("Warning: could not import esp32.Partition, simulating update...")
            simulate = True
        response = requests.get(url, stream=True)
        total_size = int(response.headers.get('Content-Length', 0))
        bytes_written = 0
        chunk_size = 4096
        i = 0
        total_size = round_up_to_multiple(total_size, chunk_size)
        print(f"Starting OTA update of size: {total_size}")
        while self.keep_running: # stop if the user navigates away
            time.sleep_ms(100) # don't hog the CPU
            chunk = response.raw.read(chunk_size)
            if not chunk:
                print("No chunk, breaking...")
                break
            if len(chunk) < chunk_size:
                print(f"Padding chunk {i} from {len(chunk)} to {chunk_size} bytes")
                chunk = chunk + b'\xFF' * (chunk_size - len(chunk))
            print(f"Writing chunk {i} with length {len(chunk)}")
            if not simulate:
                next_partition.writeblocks(i, chunk)
            bytes_written += len(chunk)
            i += 1
            if total_size:
                self.progress_callback(bytes_written / total_size * 100)
        response.close()
        if bytes_written >= total_size and not simulate: # if the update was completely installed
            next_partition.set_boot()
            import machine
            machine.reset()
        # In case it didn't reset:
        lv.async_call(lambda l: self.status_label.set_text("Update finished! Please restart."), None)

# Non-class functions:

def round_up_to_multiple(n, multiple):
    return ((n + multiple - 1) // multiple) * multiple

def compare_versions(ver1: str, ver2: str) -> bool:
    """Compare two version numbers (e.g., '1.2.3' vs '4.5.6').
    Returns True if ver1 is greater than ver2, False otherwise."""
    print(f"Comparing versions: {ver1} vs {ver2}")
    v1_parts = [int(x) for x in ver1.split('.')]
    v2_parts = [int(x) for x in ver2.split('.')]
    print(f"Version 1 parts: {v1_parts}")
    print(f"Version 2 parts: {v2_parts}")
    for i in range(max(len(v1_parts), len(v2_parts))):
        v1 = v1_parts[i] if i < len(v1_parts) else 0
        v2 = v2_parts[i] if i < len(v2_parts) else 0
        print(f"Comparing part {i}: {v1} vs {v2}")
        if v1 > v2:
            print(f"{ver1} is greater than {ver2}")
            return True
        if v1 < v2:
            print(f"{ver1} is less than {ver2}")
            return False
    print(f"Versions are equal or {ver1} is not greater than {ver2}")
    return False
