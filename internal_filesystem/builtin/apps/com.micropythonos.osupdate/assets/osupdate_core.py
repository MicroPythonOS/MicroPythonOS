import ujson
import time

from mpos import (
    AppManager,
    ConnectivityManager,
    TaskManager,
    DownloadManager,
    DeviceInfo,
    BuildInfo,
    NotificationManager,
    Notification,
    Intent,
)


class UpdateState:
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
    CHUNK_SIZE = 4096

    def __init__(self, partition_module=None, connectivity_manager=None, download_manager=None):
        self.partition_module = partition_module
        self.connectivity_manager = connectivity_manager
        self.download_manager = download_manager if download_manager else DownloadManager
        self.simulate = False

        self.is_paused = False
        self.bytes_written_so_far = 0
        self.total_size_expected = 0

        self._current_partition = None
        self._block_index = 0
        self._chunk_buffer = b''
        self._should_continue = True
        self._progress_callback = None

        if self.partition_module is None:
            try:
                from esp32 import Partition
                self.partition_module = Partition
            except ImportError:
                print("UpdateDownloader: Partition module not available, will simulate")
                self.simulate = True

    def _setup_partition(self):
        if not self.simulate and self._current_partition is None:
            from mpos.partitions import get_next_update_partition
            self._current_partition = get_next_update_partition(
                partition_module=self.partition_module
            )
            print(f"UpdateDownloader: Writing to partition: {self._current_partition}")

    async def _process_chunk(self, chunk):
        if not self._should_continue:
            return

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

        self._total_bytes_received += len(chunk)

        self._chunk_buffer += chunk

        while len(self._chunk_buffer) >= self.CHUNK_SIZE:
            block = self._chunk_buffer[:self.CHUNK_SIZE]
            self._chunk_buffer = self._chunk_buffer[self.CHUNK_SIZE:]

            if not self.simulate:
                self._current_partition.writeblocks(self._block_index, block)

            self._block_index += 1
            self.bytes_written_so_far += len(block)

    async def _flush_buffer(self):
        if self._chunk_buffer:
            remaining = len(self._chunk_buffer)
            padded = self._chunk_buffer + b'\xFF' * (self.CHUNK_SIZE - remaining)
            print(f"UpdateDownloader: Padding final chunk from {remaining} to {self.CHUNK_SIZE} bytes")

            if not self.simulate:
                self._current_partition.writeblocks(self._block_index, padded)

            self.bytes_written_so_far += self.CHUNK_SIZE
            self._chunk_buffer = b''

            if self._progress_callback and self.total_size_expected > 0:
                percent = (self.bytes_written_so_far / self.total_size_expected) * 100
                await self._progress_callback(min(percent, 100.0))

    async def download_and_install(self, url, progress_callback=None, speed_callback=None, should_continue_callback=None):
        result = {
            'success': False,
            'bytes_written': 0,
            'total_size': 0,
            'error': None,
            'paused': False
        }

        self._progress_callback = progress_callback
        self._should_continue = True
        self._total_bytes_received = 0

        try:
            self._setup_partition()

            self._block_index = self.bytes_written_so_far // self.CHUNK_SIZE

            headers = None
            if self.bytes_written_so_far > 0:
                headers = {'Range': f'bytes={self.bytes_written_so_far}-'}
                print(f"UpdateDownloader: Resuming from byte {self.bytes_written_so_far} (last complete block)")

            dm = self.download_manager

            async def chunk_handler(chunk):
                if should_continue_callback and not should_continue_callback():
                    self._should_continue = False
                    raise Exception("Download cancelled by user")
                await self._process_chunk(chunk)

            if self.bytes_written_so_far == 0:
                self.total_size_expected = 0

            print(f"UpdateDownloader: Starting async download from {url}")
            success = await dm.download_url(
                url,
                chunk_callback=chunk_handler,
                progress_callback=progress_callback,
                speed_callback=speed_callback,
                headers=headers
            )

            if success:
                await self._flush_buffer()

                result['success'] = True
                result['bytes_written'] = self.bytes_written_so_far
                result['total_size'] = self.bytes_written_so_far

                if self._progress_callback:
                    await self._progress_callback(100.0)

                self.is_paused = False
                self.bytes_written_so_far = 0
                self.total_size_expected = 0
                self._current_partition = None
                self._block_index = 0
                self._chunk_buffer = b''
                self._total_bytes_received = 0

                print(f"UpdateDownloader: Download complete ({result['bytes_written']} bytes)")
            else:
                result['error'] = "Download failed"
                result['bytes_written'] = self.bytes_written_so_far
                result['total_size'] = self.total_size_expected

        except Exception as e:
            error_msg = str(e)
            print(f"error_msg: {error_msg}")

            if "cancelled" in error_msg.lower():
                result['error'] = error_msg
                result['bytes_written'] = self.bytes_written_so_far
                result['total_size'] = self.total_size_expected
            elif DownloadManager.is_network_error(e):
                print(f"UpdateDownloader: Network error ({e}), pausing download")

                if self._chunk_buffer:
                    buffer_len = len(self._chunk_buffer)
                    print(f"UpdateDownloader: Discarding {buffer_len} bytes from buffer (will re-download on resume)")
                    self._chunk_buffer = b''

                self.is_paused = True
                result['paused'] = True
                result['bytes_written'] = self.bytes_written_so_far
                result['total_size'] = self.total_size_expected
                print(f"UpdateDownloader: Will resume from byte {self.bytes_written_so_far} (last complete block)")
            else:
                result['error'] = error_msg
                result['bytes_written'] = self.bytes_written_so_far
                result['total_size'] = self.total_size_expected
                print(f"UpdateDownloader: Error during download: {e}")

        return result

    def set_boot_partition_and_restart(self):
        if self.simulate:
            print("UpdateDownloader: Simulating restart (desktop mode)")
            return

        try:
            from mpos.partitions import get_next_update_partition
            next_partition = get_next_update_partition(
                partition_module=self.partition_module
            )
            next_partition.set_boot()
            print("UpdateDownloader: Boot partition set, restarting...")

            import machine
            machine.reset()
        except Exception as e:
            print(f"UpdateDownloader: Error setting boot partition: {e}")
            raise


class UpdateChecker:

    def __init__(self, download_manager=None, json_module=None):
        self.download_manager = download_manager if download_manager else DownloadManager
        self.json = json_module if json_module else ujson

    def get_update_url(self, hardware_id):
        return f"https://updates.micropythonos.com/osupdate_{hardware_id}.json"

    async def fetch_update_info(self, hardware_id):
        url = self.get_update_url(hardware_id)
        print(f"UpdateChecker: fetching {url}")

        try:
            response_data = await self.download_manager.download_url(url)

            try:
                update_data = self.json.loads(response_data)
            except Exception as e:
                raise ValueError(f"Invalid JSON in update file: {e}")

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
        return AppManager.compare_versions(remote_version, current_version) > 0


def _get_version_comparison(remote_version, current_version):
    is_newer = AppManager.compare_versions(remote_version, current_version)
    is_older = AppManager.compare_versions(current_version, remote_version)
    if is_newer > 0:
        return "newer"
    elif is_older > 0:
        return "older"
    return "same"


def round_up_to_multiple(n, multiple):
    return ((n + multiple - 1) // multiple) * multiple


class UpdateManager:
    _instance = None

    BOOT_INITIAL_DELAY = 120 # how long to wait after startup to check for updates
    BOOT_CHECK_INTERVAL = 60 * 60 * 24 # how often to check for updates
    WIFI_WAIT_TIMEOUT = 300
    WIFI_CHECK_INTERVAL = 2

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        if UpdateManager._instance is not None:
            raise RuntimeError("Use UpdateManager.get_instance()")
        self.update_checker = UpdateChecker()
        self.update_downloader = UpdateDownloader()
        self.current_state = UpdateState.IDLE
        self.connectivity_manager = None
        self._update_info = None
        self._state_callback = None
        self._running = False
        self._check_in_progress = False
        self._suppress_notifications = False

    def set_state_callback(self, callback):
        self._state_callback = callback

    def clear_state_callback(self):
        self._state_callback = None

    @property
    def suppress_notifications(self):
        return self._suppress_notifications

    @suppress_notifications.setter
    def suppress_notifications(self, value):
        self._suppress_notifications = bool(value)

    def set_state(self, new_state):
        print(f"UpdateManager: state change {self.current_state} -> {new_state}")
        self.current_state = new_state
        if self._state_callback:
            self._state_callback(new_state)

    def get_state(self):
        return self.current_state

    def get_update_info(self):
        return self._update_info

    def _network_changed(self, online):
        print(f"UpdateManager: network_changed, now: {'ONLINE' if online else 'OFFLINE'}")
        if not online:
            if self.current_state == UpdateState.IDLE or self.current_state == UpdateState.CHECKING_UPDATE:
                self.set_state(UpdateState.WAITING_WIFI)
            elif self.current_state == UpdateState.ERROR:
                self.set_state(UpdateState.WAITING_WIFI)
        else:
            if self.current_state == UpdateState.IDLE or self.current_state == UpdateState.WAITING_WIFI:
                self.set_state(UpdateState.CHECKING_UPDATE)
                TaskManager.create_task(self.check_for_update())
            elif self.current_state == UpdateState.ERROR:
                print("UpdateManager: Retrying update check after network came back online")
                self.set_state(UpdateState.CHECKING_UPDATE)
                TaskManager.create_task(self.check_for_update())

    def _notify_update_available(self):
        if self._suppress_notifications:
            print("UpdateManager: suppressing notification because OSUpdate is in foreground")
            return
        info = self._update_info or {}
        version = info.get("version")
        details = "Tap to open OS updater"
        if version:
            details = "Version " + str(version) + " is available"

        NotificationManager.notify(
            Notification(
                notification_id="osupdate.update_available",
                icon="M:builtin/apps/com.micropythonos.osupdate/res/mipmap-mdpi/icon_64x64.png",
                title="OS update available",
                text=details,
                priority=Notification.PRIORITY_HIGH,
                intent=Intent(app_fullname="com.micropythonos.osupdate"),
                auto_cancel=True,
                app_fullname="com.micropythonos.osupdate",
            )
        )

    def _clear_update_available_notification(self):
        NotificationManager.cancel("osupdate.update_available")

    def start(self):
        self._running = True
        self.connectivity_manager = ConnectivityManager.get()
        self.connectivity_manager.register_callback(self._network_changed)
        TaskManager.create_task(self._run_loop())

    async def _run_loop(self):
        await TaskManager.sleep(self.BOOT_INITIAL_DELAY)

        while self._running:
            if self._check_in_progress:
                await TaskManager.sleep(1)
                continue

            if self.connectivity_manager.is_online():
                await self.check_for_update()
                if self.current_state == UpdateState.UPDATE_AVAILABLE:
                    self._notify_update_available()
            else:
                print("UpdateManager: offline, skipping check")

            for _ in range(self.BOOT_CHECK_INTERVAL):
                if not self._running:
                    return
                await TaskManager.sleep(1)

    def stop(self):
        print("UpdateManager: stopping")
        self._running = False
        if self.connectivity_manager:
            self.connectivity_manager.unregister_callback(self._network_changed)

    def check_for_update_now(self):
        """Kick off a one-off update check if none is already in progress."""
        if self._check_in_progress:
            return
        TaskManager.create_task(self.check_for_update())

    async def check_for_update(self):
        if self._check_in_progress:
            return
        self._check_in_progress = True
        try:
            self.set_state(UpdateState.CHECKING_UPDATE)
            hwid = DeviceInfo.hardware_id
            update_info = await self.update_checker.fetch_update_info(hwid)
            comparison = _get_version_comparison(
                update_info["version"],
                BuildInfo.version.release
            )
            self._update_info = {
                "version": update_info["version"],
                "download_url": update_info["download_url"],
                "changelog": update_info["changelog"],
                "comparison": comparison,
            }
            if comparison == "newer":
                self.set_state(UpdateState.UPDATE_AVAILABLE)
                self._notify_update_available()
            else:
                self.set_state(UpdateState.NO_UPDATE)
                self._clear_update_available_notification()
        except ValueError:
            self.set_state(UpdateState.ERROR)
            self._clear_update_available_notification()
        except RuntimeError:
            self.set_state(UpdateState.ERROR)
            self._clear_update_available_notification()
        except Exception as e:
            print(f"UpdateManager.check_for_update got exception: {e}")
            if DownloadManager.is_network_error(e):
                print("UpdateManager: Network error while checking for updates, waiting for WiFi")
                self.set_state(UpdateState.WAITING_WIFI)
            else:
                self.set_state(UpdateState.ERROR)
            self._clear_update_available_notification()
        finally:
            self._check_in_progress = False

    async def start_download(self, url, progress_callback=None, speed_callback=None, should_continue_callback=None):
        while True:
            if should_continue_callback and not should_continue_callback():
                return {
                    'success': False,
                    'cancelled': True,
                    'bytes_written': self.update_downloader.bytes_written_so_far,
                    'total_size': self.update_downloader.total_size_expected,
                }

            result = await self.update_downloader.download_and_install(
                url,
                progress_callback=progress_callback,
                speed_callback=speed_callback,
                should_continue_callback=should_continue_callback
            )

            if result['success']:
                self.set_state(UpdateState.COMPLETED)
                return result

            if result.get('paused'):
                bytes_written = result.get('bytes_written', 0)
                total_size = result.get('total_size', 0)
                percent = (bytes_written / total_size * 100) if total_size > 0 else 0
                print(f"UpdateManager: Download paused at {percent:.1f}% ({bytes_written}/{total_size} bytes)")
                self.set_state(UpdateState.DOWNLOAD_PAUSED)

                ok = await self._wait_for_wifi_retry(should_continue_callback)
                if not ok:
                    return result
                self.set_state(UpdateState.DOWNLOADING)
                continue

            self.set_state(UpdateState.ERROR)
            return result

    async def _wait_for_wifi_retry(self, should_continue_callback=None):
        print("UpdateManager: Waiting for network to return...")
        elapsed = 0

        while elapsed < self.WIFI_WAIT_TIMEOUT:
            if should_continue_callback and not should_continue_callback():
                print("UpdateManager: User cancelled while waiting for wifi")
                return False
            if self.connectivity_manager and self.connectivity_manager.is_online():
                print("UpdateManager: Network reconnected, waiting for stabilization...")
                await TaskManager.sleep(2)
                print("UpdateManager: Resuming download")
                return True
            await TaskManager.sleep(self.WIFI_CHECK_INTERVAL)
            elapsed += self.WIFI_CHECK_INTERVAL

        print("UpdateManager: Timed out waiting for network")
        return False
