import lvgl as lv

from mpos import Activity, DisplayMetrics, TaskManager, BuildInfo


class OSUpdate(Activity):

    # Widgets:
    status_label = None
    install_button = None
    check_again_button = None
    main_screen = None
    progress_label = None
    progress_bar = None
    speed_label = None

    def __init__(self):
        super().__init__()
        self._download_in_progress = False
        self._um = None

    def _ensure_update_manager(self):
        if self._um is None:
            from osupdate_core import UpdateManager
            self._um = UpdateManager.get_instance()

    def onCreate(self):
        self._ensure_update_manager()

        self.main_screen = lv.obj()
        self.main_screen.set_style_pad_all(DisplayMetrics.pct_of_width(2), lv.PART.MAIN)

        lv.group_get_default().add_obj(self.main_screen)

        self.current_version_label = lv.label(self.main_screen)
        self.current_version_label.align(lv.ALIGN.TOP_LEFT, 0, 0)
        self.current_version_label.set_text(f"Installed OS version: {BuildInfo.version.release}")
        self.current_version_label.set_width(lv.pct(75))
        self.current_version_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.install_button = lv.button(self.main_screen)
        self.install_button.align(lv.ALIGN.TOP_RIGHT, 0, 0)
        self.install_button.add_state(lv.STATE.DISABLED)
        self.install_button.set_size(lv.SIZE_CONTENT, lv.pct(25))
        self.install_button.add_event_cb(lambda e: self.install_button_click(), lv.EVENT.CLICKED, None)
        install_label = lv.label(self.install_button)
        install_label.set_text("No\nUpdate")
        install_label.center()

        self.check_again_button = lv.button(self.main_screen)
        self.check_again_button.align(lv.ALIGN.BOTTOM_MID, 0, -10)
        self.check_again_button.set_size(lv.SIZE_CONTENT, lv.pct(15))
        self.check_again_button.add_event_cb(lambda e: self.check_again_click(), lv.EVENT.CLICKED, None)
        self.check_again_button.add_flag(lv.obj.FLAG.HIDDEN)
        check_again_label = lv.label(self.check_again_button)
        check_again_label.set_text("Check Again")
        check_again_label.center()

        self.status_label = lv.label(self.main_screen)
        self.status_label.align_to(self.current_version_label, lv.ALIGN.OUT_BOTTOM_LEFT, 0, DisplayMetrics.pct_of_height(5))
        self.setContentView(self.main_screen)

    def onResume(self, screen):
        from osupdate_core import UpdateState

        super().onResume(screen)
        self._ensure_update_manager()
        self._um.set_state_callback(self._on_um_state_change)
        self._um.suppress_notifications = True
        current_state = self._um.get_state()
        self._sync_ui(current_state)

        if current_state == UpdateState.IDLE:
            self._um.check_for_update_now()

    def onPause(self, screen):
        self._um.clear_state_callback()
        self._um.suppress_notifications = False
        super().onPause(screen)

    def _on_um_state_change(self, state):
        if self.has_foreground():
            self._sync_ui(state)

    def _sync_ui(self, state):
        from osupdate_core import UpdateState

        if state == UpdateState.IDLE:
            self.status_label.set_text("Checking for OS updates...")
            self.check_again_button.remove_flag(lv.obj.FLAG.HIDDEN)
            self.install_button.add_state(lv.STATE.DISABLED)
        elif state == UpdateState.WAITING_WIFI:
            self.status_label.set_text("Waiting for WiFi connection...")
            self.check_again_button.add_flag(lv.obj.FLAG.HIDDEN)
        elif state == UpdateState.CHECKING_UPDATE:
            self.status_label.set_text("Checking for OS updates...")
            self.check_again_button.add_flag(lv.obj.FLAG.HIDDEN)
        elif state == UpdateState.UPDATE_AVAILABLE:
            info = self._um.get_update_info()
            self._update_install_button(info["comparison"] if info else "newer")
            if info:
                self.status_label.set_text(
                    f"Update version: {info['version']}\n"
                    "Update version is newer.\n\n"
                    f"Details:\n\n{info['changelog']}"
                )
            else:
                self.status_label.set_text("Update available!")
            self.check_again_button.add_flag(lv.obj.FLAG.HIDDEN)
        elif state == UpdateState.NO_UPDATE:
            info = self._um.get_update_info()
            self._update_install_button(info["comparison"] if info else "same")
            if info:
                self.status_label.set_text(
                    f"Version: {info['version']}\n"
                    f"This version is {info['comparison']}.\n\n"
                    f"Details:\n\n{info['changelog']}"
                )
            else:
                self.status_label.set_text("No updates available.")
            self.check_again_button.add_flag(lv.obj.FLAG.HIDDEN)
        elif state == UpdateState.DOWNLOADING:
            self.status_label.set_text("Update in progress.\nNavigate away to cancel.")
            self.check_again_button.add_flag(lv.obj.FLAG.HIDDEN)
        elif state == UpdateState.DOWNLOAD_PAUSED:
            self.status_label.set_text("Download paused - waiting for WiFi...")
            self.check_again_button.add_flag(lv.obj.FLAG.HIDDEN)
        elif state == UpdateState.ERROR:
            self.check_again_button.remove_flag(lv.obj.FLAG.HIDDEN)

    def _update_install_button(self, comparison):
        if comparison == "newer":
            text = "Install\nnew\nversion"
        elif comparison == "older":
            text = "Install\nold\nversion"
        else:
            text = "Reinstall\nsame\nversion"
        install_label = self.install_button.get_child(0)
        install_label.set_text(text)
        install_label.center()
        self.install_button.remove_state(lv.STATE.DISABLED)

    def install_button_click(self):
        info = self._um.get_update_info()
        if not info:
            print("Install button clicked but no update info available")
            return

        url = info["download_url"]
        print(f"install_button_click for url {url}")

        self.install_button.add_state(lv.STATE.DISABLED)
        self._download_in_progress = True

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

        TaskManager.create_task(self._run_download(url))

    def check_again_click(self):
        print("OSUpdate: Check Again button clicked")
        self.check_again_button.add_flag(lv.obj.FLAG.HIDDEN)
        self._um.check_for_update_now()

    def _get_user_friendly_error(self, error):
        error_str = str(error).lower()

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

        elif "invalid json" in error_str or "syntax error" in error_str:
            return ("Server returned invalid data.\n\n"
                   "The update server may be experiencing issues.\n"
                   "Try again later.")
        elif "missing required fields" in error_str:
            return ("Update information is incomplete.\n\n"
                   "The update server may be experiencing issues.\n"
                   "Try again later.")

        elif "enospc" in error_str or "no space" in error_str:
            return ("Not enough storage space.\n\n"
                   "Free up space and try again.")

        else:
            return f"An error occurred:\n{str(error)}\n\nPlease try again."

    async def _run_download(self, url):
        result = await self._um.start_download(
            url,
            progress_callback=self.async_progress_callback,
            speed_callback=self.async_speed_callback,
            should_continue_callback=self.has_foreground
        )

        self._download_in_progress = False

        if not self.has_foreground():
            return

        if result['success']:
            self.status_label.set_text("Update finished! Restarting...")
            await TaskManager.sleep(5)
            from osupdate_core import UpdateManager
            UpdateManager.get_instance().update_downloader.set_boot_partition_and_restart()
            return

        bytes_written = result.get('bytes_written', 0)
        total_size = result.get('total_size', 0)

        if result.get('timeout'):
            msg = (f"Network timeout during download.\n"
                   f"{bytes_written}/{total_size} bytes written.\n"
                   "Press 'Update OS' to retry.")
            self.status_label.set_text(msg)
            self.install_button.remove_state(lv.STATE.DISABLED)
            return

        if result.get('cancelled'):
            msg = (f"Update cancelled by user.\n\n"
                   f"{bytes_written}/{total_size} bytes downloaded.\n"
                   "Press 'Update OS' to resume.")
            self.status_label.set_text(msg)
            self.install_button.remove_state(lv.STATE.DISABLED)
            return

        error_msg = result.get('error', 'Unknown error')
        friendly_msg = self._get_user_friendly_error(Exception(error_msg))
        progress_info = f"\n\nProgress: {bytes_written}/{total_size} bytes"
        if bytes_written > 0:
            progress_info += "\n\nPress 'Update OS' to resume."
        self.status_label.set_text(friendly_msg + progress_info)
        self.install_button.remove_state(lv.STATE.DISABLED)

    async def async_progress_callback(self, percent):
        if self.has_foreground() and self.progress_bar:
            self.progress_bar.set_value(int(percent), True)
            self.progress_label.set_text(f"OTA Update: {percent:.2f}%")
        await TaskManager.sleep_ms(50)

    async def async_speed_callback(self, bytes_per_second):
        if bytes_per_second >= 1024 * 1024:
            speed_str = f"{bytes_per_second / (1024 * 1024):.1f} MB/s"
        elif bytes_per_second >= 1024:
            speed_str = f"{bytes_per_second / 1024:.1f} KB/s"
        else:
            speed_str = f"{bytes_per_second:.0f} B/s"

        if self.has_foreground() and self.speed_label:
            self.speed_label.set_text(f"Speed: {speed_str}")
