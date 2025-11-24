import lvgl as lv
import requests
import ujson
import time
import _thread

from mpos.apps import Activity
from mpos import PackageManager, ConnectivityManager
import mpos.info
import mpos.ui

class OSUpdate(Activity):

    download_update_url = None

    # Widgets:
    status_label = None
    install_button = None
    force_update = None
    check_again_button = None
    main_screen = None
    progress_label = None
    progress_bar = None

    # State management
    current_state = None

    def __init__(self):
        super().__init__()
        # Initialize business logic components with dependency injection
        self.update_checker = UpdateChecker()
        self.update_downloader = UpdateDownloader()
        self.current_state = UpdateState.IDLE
        self.connectivity_manager = None  # Will be initialized in onStart

    # This function gets called from both the main thread as the update_with_lvgl() thread
    def set_state(self, new_state):
        """Change app state and update UI accordingly."""
        print(f"OSUpdate: state change {self.current_state} -> {new_state}")
        self.current_state = new_state
        self.update_ui_threadsafe_if_foreground(self._update_ui_for_state) # Since called from both threads, be threadsafe

    def onCreate(self):
        self.main_screen = lv.obj()
        self.main_screen.set_style_pad_all(mpos.ui.pct_of_display_width(2), 0)

        # Make the screen focusable so it can be scrolled with the arrow keys
        if focusgroup := lv.group_get_default():
            focusgroup.add_obj(self.main_screen)

        self.current_version_label = lv.label(self.main_screen)
        self.current_version_label.align(lv.ALIGN.TOP_LEFT,0,0)
        self.current_version_label.set_text(f"Installed OS version: {mpos.info.CURRENT_OS_VERSION}")
        self.force_update = lv.checkbox(self.main_screen)
        self.force_update.set_text("Force Update")
        self.force_update.add_event_cb(lambda *args: self.force_update_clicked(), lv.EVENT.VALUE_CHANGED, None)
        #self.force_update.add_event_cb(lambda e: mpos.ui.print_event(e), lv.EVENT.ALL, None)
        self.force_update.align_to(self.current_version_label, lv.ALIGN.OUT_BOTTOM_LEFT, 0, mpos.ui.pct_of_display_height(5))
        self.install_button = lv.button(self.main_screen)
        self.install_button.align(lv.ALIGN.TOP_RIGHT, 0, 0)
        self.install_button.add_state(lv.STATE.DISABLED) # button will be enabled if there is an update available
        self.install_button.set_size(lv.SIZE_CONTENT, lv.pct(25))
        self.install_button.add_event_cb(lambda e: self.install_button_click(), lv.EVENT.CLICKED, None)
        install_label = lv.label(self.install_button)
        install_label.set_text("Update OS")
        install_label.center()

        # Check Again button (hidden initially, shown on errors)
        self.check_again_button = lv.button(self.main_screen)
        self.check_again_button.align(lv.ALIGN.BOTTOM_MID, 0, -10)
        self.check_again_button.set_size(lv.SIZE_CONTENT, lv.pct(15))
        self.check_again_button.add_event_cb(lambda e: self.check_again_click(), lv.EVENT.CLICKED, None)
        self.check_again_button.add_flag(lv.obj.FLAG.HIDDEN)  # Initially hidden
        check_again_label = lv.label(self.check_again_button)
        check_again_label.set_text("Check Again")
        check_again_label.center()

        self.status_label = lv.label(self.main_screen)
        self.status_label.align_to(self.force_update, lv.ALIGN.OUT_BOTTOM_LEFT, 0, mpos.ui.pct_of_display_height(5))
        self.setContentView(self.main_screen)

    def _update_ui_for_state(self):
        """Update UI elements based on current state."""
        if self.current_state == UpdateState.WAITING_WIFI:
            self.status_label.set_text("Waiting for WiFi connection...")
            self.check_again_button.add_flag(lv.obj.FLAG.HIDDEN)
        elif self.current_state == UpdateState.CHECKING_UPDATE:
            self.status_label.set_text("Checking for OS updates...")
            self.check_again_button.add_flag(lv.obj.FLAG.HIDDEN)
        elif self.current_state == UpdateState.DOWNLOADING:
            self.status_label.set_text("Update in progress.\nNavigate away to cancel.")
            self.check_again_button.add_flag(lv.obj.FLAG.HIDDEN)
        elif self.current_state == UpdateState.DOWNLOAD_PAUSED:
            self.status_label.set_text("Download paused - waiting for WiFi...")
            self.check_again_button.add_flag(lv.obj.FLAG.HIDDEN)
        elif self.current_state == UpdateState.ERROR:
            # Show "Check Again" button on errors
            self.check_again_button.remove_flag(lv.obj.FLAG.HIDDEN)

    def onResume(self, screen):
        """Register for connectivity callbacks when app resumes."""
        super().onResume(screen)
        # Get connectivity manager instance
        self.connectivity_manager = ConnectivityManager.get()
        self.connectivity_manager.register_callback(self.network_changed)
        # Start, based on network state:
        self.network_changed(self.connectivity_manager.is_online())

    def onPause(self, screen):
        """Unregister connectivity callbacks when app pauses."""
        if self.connectivity_manager:
            self.connectivity_manager.unregister_callback(self.network_changed)
        super().onPause(screen)

    def network_changed(self, online):
        """Callback when network connectivity changes.

        Args:
            online: True if network is online, False if offline
        """
        print(f"OSUpdate: network_changed, now: {'ONLINE' if online else 'OFFLINE'}")

        if not online:
            # Went offline
            if self.current_state == UpdateState.DOWNLOADING:
                # Download will automatically pause due to connectivity check
                pass
            elif self.current_state == UpdateState.IDLE or self.current_state == UpdateState.CHECKING_UPDATE:
                # Was checking for updates when network dropped
                self.set_state(UpdateState.WAITING_WIFI)
            elif self.current_state == UpdateState.ERROR:
                # Was in error state, might be network-related
                # Update UI to show we're waiting for network
                self.set_state(UpdateState.WAITING_WIFI)
        else:
            # Went online
            if self.current_state == UpdateState.IDLE or self.current_state == UpdateState.WAITING_WIFI:
                # Was waiting for network, now can check for updates
                self.set_state(UpdateState.CHECKING_UPDATE)
                self.schedule_show_update_info()
            elif self.current_state == UpdateState.ERROR:
                # Was in error state (possibly network error), retry now that network is back
                print("OSUpdate: Retrying update check after network came back online")
                self.set_state(UpdateState.CHECKING_UPDATE)
                self.schedule_show_update_info()
            elif self.current_state == UpdateState.DOWNLOAD_PAUSED:
                # Download was paused, will auto-resume in download thread
                pass

    def _get_user_friendly_error(self, error):
        """Convert technical errors into user-friendly messages with guidance."""
        error_str = str(error).lower()

        # HTTP errors
        if "404" in error_str:
            return ("Update information not found for your device.\n\n"
                   "This hardware may not yet be supported.\n"
                   "Check https://micropythonos.com for updates.")
        elif "500" in error_str or "502" in error_str or "503" in error_str:
            return ("Update server is temporarily unavailable.\n\n"
                   "Please try again in a few minutes.")
        elif "timeout" in error_str:
            return ("Connection timeout.\n\n"
                   "Check your internet connection and try again.")
        elif "connection refused" in error_str:
            return ("Cannot connect to update server.\n\n"
                   "Check your internet connection.")

        # JSON/Data errors
        elif "invalid json" in error_str or "syntax error" in error_str:
            return ("Server returned invalid data.\n\n"
                   "The update server may be experiencing issues.\n"
                   "Try again later.")
        elif "missing required fields" in error_str:
            return ("Update information is incomplete.\n\n"
                   "The update server may be experiencing issues.\n"
                   "Try again later.")

        # Storage errors
        elif "enospc" in error_str or "no space" in error_str:
            return ("Not enough storage space.\n\n"
                   "Free up space and try again.")

        # Generic errors
        else:
            return f"An error occurred:\n{str(error)}\n\nPlease try again."

    # Show update info with a delay, to ensure ordering of multiple lv.async_call()
    def schedule_show_update_info(self):
        timer = lv.timer_create(self.show_update_info, 150, None)
        timer.set_repeat_count(1)

    def show_update_info(self, timer=None):
        hwid = mpos.info.get_hardware_id()

        try:
            # Use UpdateChecker to fetch update info
            update_info = self.update_checker.fetch_update_info(hwid)
            self.handle_update_info(
                update_info["version"],
                update_info["download_url"],
                update_info["changelog"]
            )
        except ValueError as e:
            # JSON parsing or validation error (not network related)
            self.set_state(UpdateState.ERROR)
            self.status_label.set_text(self._get_user_friendly_error(e))
        except RuntimeError as e:
            # Network or HTTP error
            self.set_state(UpdateState.ERROR)
            self.status_label.set_text(self._get_user_friendly_error(e))
        except Exception as e:
            print(f"show_update_info got exception: {e}")
            # Check if this is a network connectivity error
            if self.update_downloader._is_network_error(e):
                # Network not available - wait for it to come back
                print("OSUpdate: Network error while checking for updates, waiting for WiFi")
                self.set_state(UpdateState.WAITING_WIFI)
            else:
                # Other unexpected error
                self.set_state(UpdateState.ERROR)
                self.status_label.set_text(self._get_user_friendly_error(e))
    
    def handle_update_info(self, version, download_url, changelog):
        self.download_update_url = download_url

        # Use UpdateChecker to determine if update is available
        is_newer = self.update_checker.is_update_available(version, mpos.info.CURRENT_OS_VERSION)

        if is_newer:
            label = "New"
            self.install_button.remove_state(lv.STATE.DISABLED)
        else:
            label = "No new"
            if (self.force_update.get_state() & lv.STATE.CHECKED):
                self.install_button.remove_state(lv.STATE.DISABLED)
        label += f" version: {version}\n\nDetails:\n\n{changelog}"
        self.status_label.set_text(label)


    def install_button_click(self):
        if not self.download_update_url:
            print("Install button clicked but download_update_url is unknown, returning...")
            return
        else:
            print(f"install_button_click for url {self.download_update_url}")

        self.install_button.add_state(lv.STATE.DISABLED)
        self.set_state(UpdateState.DOWNLOADING)

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
            _thread.start_new_thread(self.update_with_lvgl, (self.download_update_url,))
        except Exception as e:
            print("Could not start update_with_lvgl thread: ", e)

    def force_update_clicked(self):
        if self.download_update_url and (self.force_update.get_state() & lv.STATE.CHECKED):
            self.install_button.remove_state(lv.STATE.DISABLED)
        else:
            self.install_button.add_state(lv.STATE.DISABLED)

    def check_again_click(self):
        """Handle 'Check Again' button click - retry update check."""
        print("OSUpdate: Check Again button clicked")
        self.check_again_button.add_flag(lv.obj.FLAG.HIDDEN)
        self.set_state(UpdateState.CHECKING_UPDATE)
        self.schedule_show_update_info()

    def progress_callback(self, percent):
        print(f"OTA Update: {percent:.1f}%")
        self.update_ui_threadsafe_if_foreground(self.progress_bar.set_value, int(percent), True)
        self.update_ui_threadsafe_if_foreground(self.progress_label.set_text, f"OTA Update: {percent:.2f}%")
        time.sleep_ms(100)

    # Custom OTA update with LVGL progress
    def update_with_lvgl(self, url):
        """Download and install update in background thread.

        Supports automatic pause/resume on wifi loss.
        """
        try:
            # Loop to handle pause/resume cycles
            while self.has_foreground():
                # Use UpdateDownloader to handle the download
                result = self.update_downloader.download_and_install(
                    url,
                    progress_callback=self.progress_callback,
                    should_continue_callback=self.has_foreground
                )

                if result['success']:
                    # Update succeeded - set boot partition and restart
                    self.update_ui_threadsafe_if_foreground(self.status_label.set_text,"Update finished! Restarting...")
                    # Small delay to show the message
                    time.sleep(5)
                    self.update_downloader.set_boot_partition_and_restart()
                    return

                elif result.get('paused', False):
                    # Download paused due to wifi loss
                    bytes_written = result.get('bytes_written', 0)
                    total_size = result.get('total_size', 0)
                    percent = (bytes_written / total_size * 100) if total_size > 0 else 0

                    print(f"OSUpdate: Download paused at {percent:.1f}% ({bytes_written}/{total_size} bytes)")
                    self.set_state(UpdateState.DOWNLOAD_PAUSED)

                    # Wait for wifi to return
                    # ConnectivityManager will notify us via callback when network returns
                    print("OSUpdate: Waiting for network to return...")
                    check_interval = 2  # Check every 2 seconds
                    max_wait = 300  # 5 minutes timeout
                    elapsed = 0

                    while elapsed < max_wait and self.has_foreground():
                        if self.connectivity_manager.is_online():
                            print("OSUpdate: Network reconnected, waiting for stabilization...")
                            time.sleep(2)  # Let routing table and DNS fully stabilize
                            print("OSUpdate: Resuming download")
                            self.set_state(UpdateState.DOWNLOADING)
                            break  # Exit wait loop and retry download

                        time.sleep(check_interval)
                        elapsed += check_interval

                    if elapsed >= max_wait:
                        # Timeout waiting for network
                        msg = f"Network timeout during download.\n{bytes_written}/{total_size} bytes written.\nPress 'Update OS' to retry."
                        self.update_ui_threadsafe_if_foreground(self.status_label.set_text, msg)
                        self.update_ui_threadsafe_if_foreground(self.install_button.remove_state, lv.STATE.DISABLED)
                        self.set_state(UpdateState.ERROR)
                        return

                    # If we're here, network is back - continue to next iteration to resume

                else:
                    # Update failed with error (not pause)
                    error_msg = result.get('error', 'Unknown error')
                    bytes_written = result.get('bytes_written', 0)
                    total_size = result.get('total_size', 0)

                    if "cancelled" in error_msg.lower():
                        msg = ("Update cancelled by user.\n\n"
                              f"{bytes_written}/{total_size} bytes downloaded.\n"
                              "Press 'Update OS' to resume.")
                    else:
                        # Use friendly error message
                        friendly_msg = self._get_user_friendly_error(Exception(error_msg))
                        progress_info = f"\n\nProgress: {bytes_written}/{total_size} bytes"
                        if bytes_written > 0:
                            progress_info += "\n\nPress 'Update OS' to resume."
                        msg = friendly_msg + progress_info

                    self.set_state(UpdateState.ERROR)
                    self.update_ui_threadsafe_if_foreground(self.status_label.set_text, msg)
                    self.update_ui_threadsafe_if_foreground(self.install_button.remove_state, lv.STATE.DISABLED)  # allow retry
                    return

        except Exception as e:
            msg = self._get_user_friendly_error(e) + "\n\nPress 'Update OS' to retry."
            self.set_state(UpdateState.ERROR)
            self.update_ui_threadsafe_if_foreground(self.status_label.set_text, msg)
            self.update_ui_threadsafe_if_foreground(self.install_button.remove_state, lv.STATE.DISABLED)  # allow retry

# Business Logic Classes:

class UpdateState:
    """State machine states for OSUpdate app."""
    IDLE = "idle"
    WAITING_WIFI = "waiting_wifi"
    CHECKING_UPDATE = "checking_update"
    UPDATE_AVAILABLE = "update_available"
    NO_UPDATE = "no_update"
    DOWNLOADING = "downloading"
    DOWNLOAD_PAUSED = "download_paused"
    COMPLETED = "completed"
    ERROR = "error"

class UpdateDownloader:
    """Handles downloading and installing OS updates."""

    def __init__(self, requests_module=None, partition_module=None, connectivity_manager=None):
        """Initialize with optional dependency injection for testing.

        Args:
            requests_module: HTTP requests module (defaults to requests)
            partition_module: ESP32 Partition module (defaults to esp32.Partition if available)
            connectivity_manager: ConnectivityManager instance for checking network during download
        """
        self.requests = requests_module if requests_module else requests
        self.partition_module = partition_module
        self.connectivity_manager = connectivity_manager
        self.simulate = False

        # Download state for pause/resume
        self.is_paused = False
        self.bytes_written_so_far = 0
        self.total_size_expected = 0

        # Try to import Partition if not provided
        if self.partition_module is None:
            try:
                from esp32 import Partition
                self.partition_module = Partition
            except ImportError:
                print("UpdateDownloader: Partition module not available, will simulate")
                self.simulate = True

    def _is_network_error(self, exception):
        """Check if exception is a network connectivity error that should trigger pause.

        Args:
            exception: Exception to check

        Returns:
            bool: True if this is a recoverable network error
        """
        error_str = str(exception).lower()
        error_repr = repr(exception).lower()

        # Check for common network error codes and messages
        # -113 = ECONNABORTED (connection aborted)
        # -104 = ECONNRESET (connection reset by peer)
        # -110 = ETIMEDOUT (connection timed out)
        # -118 = EHOSTUNREACH (no route to host)
        network_indicators = [
            '-113', '-104', '-110', '-118',  # Error codes
            'econnaborted', 'econnreset', 'etimedout', 'ehostunreach',  # Error names
            'connection reset', 'connection aborted',  # Error messages
            'broken pipe', 'network unreachable', 'host unreachable'
        ]

        return any(indicator in error_str or indicator in error_repr
                  for indicator in network_indicators)

    def download_and_install(self, url, progress_callback=None, should_continue_callback=None):
        """Download firmware and install to OTA partition.

        Supports pause/resume on wifi loss using HTTP Range headers.

        Args:
            url: URL to download firmware from
            progress_callback: Optional callback function(percent: float)
            should_continue_callback: Optional callback function() -> bool
                Returns False to cancel download

        Returns:
            dict: Result with keys:
                - 'success': bool
                - 'bytes_written': int
                - 'total_size': int
                - 'error': str (if success=False)
                - 'paused': bool (if paused due to wifi loss)

        Raises:
            Exception: If download or installation fails
        """
        result = {
            'success': False,
            'bytes_written': 0,
            'total_size': 0,
            'error': None,
            'paused': False
        }

        try:
            # Get OTA partition
            next_partition = None
            if not self.simulate:
                current = self.partition_module(self.partition_module.RUNNING)
                next_partition = current.get_next_update()
                print(f"UpdateDownloader: Writing to partition: {next_partition}")

            # Start download (or resume if we have bytes_written_so_far)
            headers = {}
            if self.bytes_written_so_far > 0:
                headers['Range'] = f'bytes={self.bytes_written_so_far}-'
                print(f"UpdateDownloader: Resuming from byte {self.bytes_written_so_far}")

            response = self.requests.get(url, stream=True, headers=headers)

            # For initial download, get total size
            if self.bytes_written_so_far == 0:
                total_size = int(response.headers.get('Content-Length', 0))
                result['total_size'] = round_up_to_multiple(total_size, 4096)
                self.total_size_expected = result['total_size']
            else:
                # For resume, use the stored total size
                # (Content-Length will be the remaining bytes, not total)
                result['total_size'] = self.total_size_expected

            print(f"UpdateDownloader: Download target {result['total_size']} bytes")

            chunk_size = 4096
            bytes_written = self.bytes_written_so_far
            block_index = bytes_written // chunk_size

            while True:
                # Check if we should continue (user cancelled)
                if should_continue_callback and not should_continue_callback():
                    result['error'] = "Download cancelled by user"
                    response.close()
                    return result

                # Check network connection before reading
                if self.connectivity_manager:
                    is_online = self.connectivity_manager.is_online()
                elif ConnectivityManager._instance:
                    is_online = ConnectivityManager._instance.is_online()
                else:
                    is_online = True

                if not is_online:
                    print("UpdateDownloader: Network lost (pre-check), pausing download")
                    self.is_paused = True
                    self.bytes_written_so_far = bytes_written
                    result['paused'] = True
                    result['bytes_written'] = bytes_written
                    response.close()
                    return result

                # Read next chunk (may raise exception if network drops)
                try:
                    chunk = response.raw.read(chunk_size)
                except Exception as read_error:
                    # Check if this is a network error that should trigger pause
                    if self._is_network_error(read_error):
                        print(f"UpdateDownloader: Network error during read ({read_error}), pausing")
                        self.is_paused = True
                        self.bytes_written_so_far = bytes_written
                        result['paused'] = True
                        result['bytes_written'] = bytes_written
                        try:
                            response.close()
                        except:
                            pass
                        return result
                    else:
                        # Non-network error, re-raise
                        raise

                if not chunk:
                    break

                # Pad last chunk if needed
                if len(chunk) < chunk_size:
                    print(f"UpdateDownloader: Padding chunk {block_index} from {len(chunk)} to {chunk_size} bytes")
                    chunk = chunk + b'\xFF' * (chunk_size - len(chunk))

                # Write to partition
                if not self.simulate:
                    next_partition.writeblocks(block_index, chunk)

                bytes_written += len(chunk)
                self.bytes_written_so_far = bytes_written
                block_index += 1

                # Update progress
                if progress_callback and result['total_size'] > 0:
                    percent = (bytes_written / result['total_size']) * 100
                    progress_callback(percent)

                # Small delay to avoid hogging CPU
                time.sleep_ms(100)

            response.close()
            result['bytes_written'] = bytes_written

            # Check if complete
            if bytes_written >= result['total_size']:
                result['success'] = True
                self.is_paused = False
                self.bytes_written_so_far = 0  # Reset for next download
                self.total_size_expected = 0
                print(f"UpdateDownloader: Download complete ({bytes_written} bytes)")
            else:
                result['error'] = f"Incomplete download: {bytes_written} < {result['total_size']}"
                print(f"UpdateDownloader: {result['error']}")

        except Exception as e:
            # Check if this is a network error that should trigger pause
            if self._is_network_error(e):
                print(f"UpdateDownloader: Network error ({e}), pausing download")
                self.is_paused = True
                # Only update bytes_written_so_far if we actually wrote bytes in this attempt
                # Otherwise preserve the existing state (important for resume failures)
                if result.get('bytes_written', 0) > 0:
                    self.bytes_written_so_far = result['bytes_written']
                result['paused'] = True
                result['bytes_written'] = self.bytes_written_so_far
                result['total_size'] = self.total_size_expected  # Preserve total size for UI
            else:
                # Non-network error
                result['error'] = str(e)
                print(f"UpdateDownloader: Error during download: {e}")

        return result

    def set_boot_partition_and_restart(self):
        """Set the updated partition as boot partition and restart device.

        Only works on ESP32 hardware. On desktop, just prints a message.
        """
        if self.simulate:
            print("UpdateDownloader: Simulating restart (desktop mode)")
            return

        try:
            current = self.partition_module(self.partition_module.RUNNING)
            next_partition = current.get_next_update()
            next_partition.set_boot()
            print("UpdateDownloader: Boot partition set, restarting...")

            import machine
            machine.reset()
        except Exception as e:
            print(f"UpdateDownloader: Error setting boot partition: {e}")
            raise


class UpdateChecker:
    """Handles checking for OS updates from remote server."""

    def __init__(self, requests_module=None, json_module=None):
        """Initialize with optional dependency injection for testing.

        Args:
            requests_module: HTTP requests module (defaults to requests)
            json_module: JSON parsing module (defaults to ujson)
        """
        self.requests = requests_module if requests_module else requests
        self.json = json_module if json_module else ujson

    def get_update_url(self, hardware_id):
        """Determine the update JSON URL based on hardware ID.

        Args:
            hardware_id: Hardware identifier string

        Returns:
            str: Full URL to update JSON file
        """
        if hardware_id == "waveshare_esp32_s3_touch_lcd_2":
            # First supported device - no hardware ID in URL
            infofile = "osupdate.json"
        else:
            infofile = f"osupdate_{hardware_id}.json"
        return f"https://updates.micropythonos.com/{infofile}"

    def fetch_update_info(self, hardware_id):
        """Fetch and parse update information from server.

        Args:
            hardware_id: Hardware identifier string

        Returns:
            dict: Update info with keys 'version', 'download_url', 'changelog'
                  or None if error occurred

        Raises:
            ValueError: If JSON is malformed or missing required fields
            ConnectionError: If network request fails
        """
        url = self.get_update_url(hardware_id)
        print(f"OSUpdate: fetching {url}")

        try:
            response = self.requests.get(url)

            if response.status_code != 200:
                # Use RuntimeError instead of ConnectionError (not available in MicroPython)
                raise RuntimeError(
                    f"HTTP {response.status_code} while checking {url}"
                )

            # Parse JSON
            try:
                update_data = self.json.loads(response.text)
            except Exception as e:
                raise ValueError(f"Invalid JSON in update file: {e}")
            finally:
                response.close()

            # Validate required fields
            required_fields = ['version', 'download_url', 'changelog']
            missing_fields = [f for f in required_fields if f not in update_data]
            if missing_fields:
                raise ValueError(
                    f"Update file missing required fields: {', '.join(missing_fields)}"
                )

            print("Version:", update_data["version"])
            print("Download URL:", update_data["download_url"])
            print("Changelog:", update_data["changelog"])

            return update_data

        except Exception as e:
            print(f"Error fetching update info: {e}")
            raise

    def is_update_available(self, remote_version, current_version):
        """Check if remote version is newer than current version.

        Args:
            remote_version: Version string from update server
            current_version: Currently installed version string

        Returns:
            bool: True if remote version is newer
        """
        return PackageManager.compare_versions(remote_version, current_version)


# Non-class functions:

def round_up_to_multiple(n, multiple):
    return ((n + multiple - 1) // multiple) * multiple
