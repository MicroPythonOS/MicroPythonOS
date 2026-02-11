import lvgl as lv
import ujson
import time

from mpos import Activity, AppManager, ConnectivityManager, TaskManager, DownloadManager, DisplayMetrics, DeviceInfo, BuildInfo

class OSUpdate(Activity):

    download_update_url = None

    # Widgets:
    status_label = None
    install_button = None
    check_again_button = None
    main_screen = None
    progress_label = None
    progress_bar = None
    speed_label = None

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
        self._update_ui_for_state()

    def onCreate(self):
        self.main_screen = lv.obj()
        self.main_screen.set_style_pad_all(DisplayMetrics.pct_of_width(2), lv.PART.MAIN)

        # Make the screen focusable so it can be scrolled with the arrow keys
        if focusgroup := lv.group_get_default():
            focusgroup.add_obj(self.main_screen)

        self.current_version_label = lv.label(self.main_screen)
        self.current_version_label.align(lv.ALIGN.TOP_LEFT,0,0)
        self.current_version_label.set_text(f"Installed OS version: {BuildInfo.version.release}")
        self.current_version_label.set_width(lv.pct(75))
        self.current_version_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.install_button = lv.button(self.main_screen)
        self.install_button.align(lv.ALIGN.TOP_RIGHT, 0, 0)
        self.install_button.add_state(lv.STATE.DISABLED) # button will be enabled if there is an update available
        self.install_button.set_size(lv.SIZE_CONTENT, lv.pct(25))
        self.install_button.add_event_cb(lambda e: self.install_button_click(), lv.EVENT.CLICKED, None)
        install_label = lv.label(self.install_button)
        install_label.set_text("No\nUpdate")
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
        self.status_label.align_to(self.current_version_label, lv.ALIGN.OUT_BOTTOM_LEFT, 0, DisplayMetrics.pct_of_height(5))
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
                TaskManager.create_task(self.show_update_info())
            elif self.current_state == UpdateState.ERROR:
                # Was in error state (possibly network error), retry now that network is back
                print("OSUpdate: Retrying update check after network came back online")
                self.set_state(UpdateState.CHECKING_UPDATE)
                TaskManager.create_task(self.show_update_info())
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

    async def show_update_info(self):
        hwid = DeviceInfo.hardware_id

        try:
            # Use UpdateChecker to fetch update info
            update_info = await self.update_checker.fetch_update_info(hwid)
            if self.has_foreground():
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
            if DownloadManager.is_network_error(e):
                # Network not available - wait for it to come back
                print("OSUpdate: Network error while checking for updates, waiting for WiFi")
                self.set_state(UpdateState.WAITING_WIFI)
            else:
                # Other unexpected error
                self.set_state(UpdateState.ERROR)
                self.status_label.set_text(self._get_user_friendly_error(e))
    
    def handle_update_info(self, version, download_url, changelog):
        self.download_update_url = download_url

        # Compare versions to determine button text and state
        current_version = BuildInfo.version.release
        
        # AppManager.compare_versions() returns 1 if ver1 > ver2, -1 if ver1 < ver2, 0 if equal
        # We need to check three cases: newer, same, or older
        is_newer = AppManager.compare_versions(version, current_version)
        is_older = AppManager.compare_versions(current_version, version)
        
        # Determine button text based on version comparison
        if is_newer > 0:
            # Update version > installed OS version
            button_text = "Install\nnew\nversion"
            label = "newer"
        elif is_older > 0:
            # Update version < installed OS version
            button_text = "Install\nold\nversion"
            label = "older"
        else:
            # Update version == installed OS version (neither is newer than the other)
            button_text = "Reinstall\nsame\nversion"
            label = "the same version"
        
        # Update button text and enable it
        install_label = self.install_button.get_child(0)
        install_label.set_text(button_text)
        install_label.center()
        self.install_button.remove_state(lv.STATE.DISABLED)
        
        self.status_label.set_text(f"Update version: {version}\nUpdate version is {label}.\n\nDetails:\n\n{changelog}")


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
        self.progress_label.align(lv.ALIGN.CENTER, 0, -15)
        
        self.speed_label = lv.label(self.main_screen)
        self.speed_label.set_text("Speed: -- KB/s")
        self.speed_label.align(lv.ALIGN.CENTER, 0, 10)
        
        self.progress_bar = lv.bar(self.main_screen)
        self.progress_bar.set_size(lv.pct(80), lv.pct(10))
        self.progress_bar.align(lv.ALIGN.BOTTOM_MID, 0, -50)
        self.progress_bar.set_range(0, 100)
        self.progress_bar.set_value(0, False)
        
        # Use TaskManager instead of _thread for async download
        TaskManager.create_task(self.perform_update())

    def check_again_click(self):
        """Handle 'Check Again' button click - retry update check."""
        print("OSUpdate: Check Again button clicked")
        self.check_again_button.add_flag(lv.obj.FLAG.HIDDEN)
        self.set_state(UpdateState.CHECKING_UPDATE)
        self.show_update_info()

    async def async_progress_callback(self, percent):
        """Async progress callback for DownloadManager.
        
        Args:
            percent: Progress percentage with 2 decimal places (0.00 - 100.00)
        """
        print(f"OTA Update: {percent:.2f}%")
        # UI updates are safe from async context in MicroPythonOS (runs on main thread)
        if self.has_foreground():
            self.progress_bar.set_value(int(percent), True)
            self.progress_label.set_text(f"OTA Update: {percent:.2f}%")
        await TaskManager.sleep_ms(50)

    async def async_speed_callback(self, bytes_per_second):
        """Async speed callback for DownloadManager.
        
        Args:
            bytes_per_second: Download speed in bytes per second
        """
        # Convert to human-readable format
        if bytes_per_second >= 1024 * 1024:
            speed_str = f"{bytes_per_second / (1024 * 1024):.1f} MB/s"
        elif bytes_per_second >= 1024:
            speed_str = f"{bytes_per_second / 1024:.1f} KB/s"
        else:
            speed_str = f"{bytes_per_second:.0f} B/s"
        
        print(f"Download speed: {speed_str}")
        if self.has_foreground() and self.speed_label:
            self.speed_label.set_text(f"Speed: {speed_str}")

    async def perform_update(self):
        """Download and install update using async patterns.

        Supports automatic pause/resume on wifi loss.
        """
        url = self.download_update_url
        
        try:
            # Loop to handle pause/resume cycles
            while self.has_foreground():
                # Use UpdateDownloader to handle the download (now async)
                result = await self.update_downloader.download_and_install(
                    url,
                    progress_callback=self.async_progress_callback,
                    speed_callback=self.async_speed_callback,
                    should_continue_callback=self.has_foreground
                )

                if result['success']:
                    # Update succeeded - set boot partition and restart
                    self.status_label.set_text("Update finished! Restarting...")
                    await TaskManager.sleep(5)
                    self.update_downloader.set_boot_partition_and_restart()
                    return

                elif result.get('paused', False):
                    # Download paused due to wifi loss
                    bytes_written = result.get('bytes_written', 0)
                    total_size = result.get('total_size', 0)
                    percent = (bytes_written / total_size * 100) if total_size > 0 else 0

                    print(f"OSUpdate: Download paused at {percent:.1f}% ({bytes_written}/{total_size} bytes)")
                    self.set_state(UpdateState.DOWNLOAD_PAUSED)

                    # Wait for wifi to return using async sleep
                    print("OSUpdate: Waiting for network to return...")
                    check_interval = 2  # Check every 2 seconds
                    max_wait = 300  # 5 minutes timeout
                    elapsed = 0

                    while elapsed < max_wait and self.has_foreground():
                        if self.connectivity_manager.is_online():
                            print("OSUpdate: Network reconnected, waiting for stabilization...")
                            await TaskManager.sleep(2)  # Let routing table and DNS fully stabilize
                            print("OSUpdate: Resuming download")
                            self.set_state(UpdateState.DOWNLOADING)
                            break  # Exit wait loop and retry download

                        await TaskManager.sleep(check_interval)
                        elapsed += check_interval

                    if elapsed >= max_wait:
                        # Timeout waiting for network
                        msg = f"Network timeout during download.\n{bytes_written}/{total_size} bytes written.\nPress 'Update OS' to retry."
                        self.status_label.set_text(msg)
                        self.install_button.remove_state(lv.STATE.DISABLED)
                        self.set_state(UpdateState.ERROR)
                        return

                    # If we're here, network is back - continue to next iteration to resume

                else:
                    # Update failed with error (not pause)
                    self._handle_update_error(result)
                    return

        except Exception as e:
            self._handle_update_exception(e)

    def _handle_update_error(self, result):
        print(f"Handle update error: {result}")
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
        self.status_label.set_text(msg)
        self.install_button.remove_state(lv.STATE.DISABLED)  # allow retry

    def _handle_update_exception(self, e):
        print(f"Handle update exception: {e}")
        msg = self._get_user_friendly_error(e) + "\n\nPress 'Update OS' to retry."
        self.set_state(UpdateState.ERROR)
        self.status_label.set_text(msg)
        self.install_button.remove_state(lv.STATE.DISABLED)  # allow retry

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
    """Handles downloading and installing OS updates using async DownloadManager."""

    # Chunk size for partition writes (must be 4096 for ESP32 flash)
    CHUNK_SIZE = 4096

    def __init__(self, partition_module=None, connectivity_manager=None, download_manager=None):
        """Initialize with optional dependency injection for testing.

        Args:
            partition_module: ESP32 Partition module (defaults to esp32.Partition if available)
            connectivity_manager: ConnectivityManager instance for checking network during download
            download_manager: DownloadManager instance for async downloads (defaults to DownloadManager class)
        """
        self.partition_module = partition_module
        self.connectivity_manager = connectivity_manager
        self.download_manager = download_manager if download_manager else DownloadManager
        self.simulate = False

        # Download state for pause/resume
        self.is_paused = False
        self.bytes_written_so_far = 0  # Bytes written to partition (in complete 4096-byte blocks)
        self.total_size_expected = 0

        # Internal state for chunk processing
        self._current_partition = None
        self._block_index = 0
        self._chunk_buffer = b''
        self._should_continue = True
        self._progress_callback = None

        # Try to import Partition if not provided
        if self.partition_module is None:
            try:
                from esp32 import Partition
                self.partition_module = Partition
            except ImportError:
                print("UpdateDownloader: Partition module not available, will simulate")
                self.simulate = True

    def _setup_partition(self):
        """Initialize the OTA partition for writing."""
        if not self.simulate and self._current_partition is None:
            current = self.partition_module(self.partition_module.RUNNING)
            self._current_partition = current.get_next_update()
            print(f"UpdateDownloader: Writing to partition: {self._current_partition}")

    async def _process_chunk(self, chunk):
        """Process a downloaded chunk - buffer and write to partition.
        
        Note: Progress reporting is handled by DownloadManager, not here.
        This method only handles buffering and writing to partition.
        
        Args:
            chunk: bytes data received from download
        """
        # Check if we should continue (user cancelled)
        if not self._should_continue:
            return
        
        # Check network connection
        if self.connectivity_manager:
            is_online = self.connectivity_manager.is_online()
        elif ConnectivityManager._instance:
            is_online = ConnectivityManager._instance.is_online()
        else:
            is_online = True

        if not is_online:
            print("UpdateDownloader: Network lost during chunk processing")
            self.is_paused = True
            raise OSError(-113, "Network lost during download")

        # Track total bytes received
        self._total_bytes_received += len(chunk)

        # Add chunk to buffer
        self._chunk_buffer += chunk

        # Write complete 4096-byte blocks
        while len(self._chunk_buffer) >= self.CHUNK_SIZE:
            block = self._chunk_buffer[:self.CHUNK_SIZE]
            self._chunk_buffer = self._chunk_buffer[self.CHUNK_SIZE:]

            if not self.simulate:
                self._current_partition.writeblocks(self._block_index, block)

            self._block_index += 1
            self.bytes_written_so_far += len(block)
        
        # Note: Progress is reported by DownloadManager via progress_callback parameter
        # We don't calculate progress here to avoid duplicate/incorrect progress updates

    async def _flush_buffer(self):
        """Flush remaining buffer with padding to complete the download."""
        if self._chunk_buffer:
            # Pad the last chunk to 4096 bytes
            remaining = len(self._chunk_buffer)
            padded = self._chunk_buffer + b'\xFF' * (self.CHUNK_SIZE - remaining)
            print(f"UpdateDownloader: Padding final chunk from {remaining} to {self.CHUNK_SIZE} bytes")

            if not self.simulate:
                self._current_partition.writeblocks(self._block_index, padded)

            self.bytes_written_so_far += self.CHUNK_SIZE
            self._chunk_buffer = b''

            # Final progress update
            if self._progress_callback and self.total_size_expected > 0:
                percent = (self.bytes_written_so_far / self.total_size_expected) * 100
                await self._progress_callback(min(percent, 100.0))

    async def download_and_install(self, url, progress_callback=None, speed_callback=None, should_continue_callback=None):
        """Download firmware and install to OTA partition using async DownloadManager.

        Supports pause/resume on wifi loss using HTTP Range headers.

        Args:
            url: URL to download firmware from
            progress_callback: Optional async callback function(percent: float)
                Called by DownloadManager with progress 0.00-100.00 (2 decimal places)
            speed_callback: Optional async callback function(bytes_per_second: float)
                Called periodically with download speed
            should_continue_callback: Optional callback function() -> bool
                Returns False to cancel download

        Returns:
            dict: Result with keys:
                - 'success': bool
                - 'bytes_written': int
                - 'total_size': int
                - 'error': str (if success=False)
                - 'paused': bool (if paused due to wifi loss)
        """
        result = {
            'success': False,
            'bytes_written': 0,
            'total_size': 0,
            'error': None,
            'paused': False
        }

        # Store callbacks for use in _process_chunk
        self._progress_callback = progress_callback
        self._should_continue = True
        self._total_bytes_received = 0

        try:
            # Setup partition
            self._setup_partition()

            # Initialize block index from resume position
            self._block_index = self.bytes_written_so_far // self.CHUNK_SIZE

            # Build headers for resume - use bytes_written_so_far (last complete block)
            # This ensures we re-download any partial/buffered data and overwrite any
            # potentially corrupted block from when the error occurred
            headers = None
            if self.bytes_written_so_far > 0:
                headers = {'Range': f'bytes={self.bytes_written_so_far}-'}
                print(f"UpdateDownloader: Resuming from byte {self.bytes_written_so_far} (last complete block)")

            # Get the download manager (use injected one for testing, or global)
            dm = self.download_manager

            # Create wrapper for chunk callback that checks should_continue
            async def chunk_handler(chunk):
                if should_continue_callback and not should_continue_callback():
                    self._should_continue = False
                    raise Exception("Download cancelled by user")
                await self._process_chunk(chunk)

            # For initial download, we need to get total size first
            # DownloadManager doesn't expose Content-Length directly, so we estimate
            if self.bytes_written_so_far == 0:
                # We'll update total_size_expected as we download
                # For now, set a placeholder that will be updated
                self.total_size_expected = 0

            # Download with streaming chunk callback
            # Progress and speed are reported by DownloadManager via callbacks
            print(f"UpdateDownloader: Starting async download from {url}")
            success = await dm.download_url(
                url,
                chunk_callback=chunk_handler,
                progress_callback=progress_callback,  # Let DownloadManager handle progress
                speed_callback=speed_callback,  # Let DownloadManager handle speed
                headers=headers
            )

            if success:
                # Flush any remaining buffered data
                await self._flush_buffer()

                result['success'] = True
                result['bytes_written'] = self.bytes_written_so_far
                result['total_size'] = self.bytes_written_so_far  # Actual size downloaded

                # Final 100% progress callback
                if self._progress_callback:
                    await self._progress_callback(100.0)

                # Reset state for next download
                self.is_paused = False
                self.bytes_written_so_far = 0
                self.total_size_expected = 0
                self._current_partition = None
                self._block_index = 0
                self._chunk_buffer = b''
                self._total_bytes_received = 0

                print(f"UpdateDownloader: Download complete ({result['bytes_written']} bytes)")
            else:
                # Download failed but not due to exception
                result['error'] = "Download failed"
                result['bytes_written'] = self.bytes_written_so_far
                result['total_size'] = self.total_size_expected

        except Exception as e:
            error_msg = str(e)
            print(f"error_msg: {error_msg}")

            # Check if cancelled by user
            if "cancelled" in error_msg.lower():
                result['error'] = error_msg
                result['bytes_written'] = self.bytes_written_so_far
                result['total_size'] = self.total_size_expected
            # Check if this is a network error that should trigger pause
            elif DownloadManager.is_network_error(e):
                print(f"UpdateDownloader: Network error ({e}), pausing download")
                
                # Clear buffer - we'll re-download this data on resume
                # This ensures we overwrite any potentially corrupted block
                if self._chunk_buffer:
                    buffer_len = len(self._chunk_buffer)
                    print(f"UpdateDownloader: Discarding {buffer_len} bytes from buffer (will re-download on resume)")
                    self._chunk_buffer = b''
                
                self.is_paused = True
                result['paused'] = True
                result['bytes_written'] = self.bytes_written_so_far  # Resume from last complete block
                result['total_size'] = self.total_size_expected
                print(f"UpdateDownloader: Will resume from byte {self.bytes_written_so_far} (last complete block)")
            else:
                # Non-network error
                result['error'] = error_msg
                result['bytes_written'] = self.bytes_written_so_far
                result['total_size'] = self.total_size_expected
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

    def __init__(self, download_manager=None, json_module=None):
        """Initialize with optional dependency injection for testing.

        Args:
            download_manager: DownloadManager instance (defaults to DownloadManager class)
            json_module: JSON parsing module (defaults to ujson)
        """
        self.download_manager = download_manager if download_manager else DownloadManager
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

    async def fetch_update_info(self, hardware_id):
        """Fetch and parse update information from server.

        Args:
            hardware_id: Hardware identifier string

        Returns:
            dict: Update info with keys 'version', 'download_url', 'changelog'
                  or None if error occurred

        Raises:
            ValueError: If JSON is malformed or missing required fields
            RuntimeError: If network request fails
        """
        url = self.get_update_url(hardware_id)
        print(f"OSUpdate: fetching {url}")

        try:
            # Use DownloadManager to fetch the JSON data
            response_data = await self.download_manager.download_url(url)

            # Parse JSON
            try:
                update_data = self.json.loads(response_data)
            except Exception as e:
                raise ValueError(f"Invalid JSON in update file: {e}")

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
        return AppManager.compare_versions(remote_version, current_version)


# Non-class functions:

def round_up_to_multiple(n, multiple):
    return ((n + multiple - 1) // multiple) * multiple
