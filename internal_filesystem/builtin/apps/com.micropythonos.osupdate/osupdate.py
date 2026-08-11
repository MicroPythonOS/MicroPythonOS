import logging

import lvgl as lv

from mpos import Activity, DisplayMetrics, TaskManager, BuildInfo, add_focus_highlight

logger = logging.getLogger(__name__)


class OSUpdate(Activity):

    # Widgets:
    status_label = None
    install_button = None
    check_again_button = None
    main_screen = None
    changelog_container = None
    progress_container = None
    progress_label = None
    progress_bar = None
    speed_label = None

    _downloading = False
    _cancel_requested = False

    def __init__(self):
        super().__init__()
        self._um = None

    def _ensure_update_manager(self):
        if self._um is None:
            from osupdate_core import UpdateManager
            self._um = UpdateManager.get_instance()

    def onCreate(self):
        self._ensure_update_manager()

        self.main_screen = lv.obj()
        self.main_screen.set_style_pad_all(DisplayMetrics.pct_of_width(2), lv.PART.MAIN)

        self.current_version_label = lv.label(self.main_screen)
        self.current_version_label.align(lv.ALIGN.TOP_LEFT, 0, 0)
        self.current_version_label.set_text(f"Installed OS version: {BuildInfo.version.release}")
        self.current_version_label.set_width(lv.pct(75))
        self.current_version_label.set_long_mode(lv.label.LONG_MODE.WRAP)

        button_row = lv.obj(self.main_screen)
        button_row.set_width(lv.pct(100))
        button_row.set_height(lv.SIZE_CONTENT)
        button_row.set_style_border_width(0, lv.PART.MAIN)
        button_row.set_flex_flow(lv.FLEX_FLOW.ROW)
        button_row.set_style_pad_all(5, lv.PART.MAIN)
        button_row.align_to(self.current_version_label, lv.ALIGN.OUT_BOTTOM_LEFT, 0, DisplayMetrics.pct_of_height(1))

        self.install_button = lv.button(button_row)
        self.install_button.add_state(lv.STATE.DISABLED)
        self.install_button.set_flex_grow(3)
        self.install_button.add_event_cb(lambda e: self.install_button_click(), lv.EVENT.CLICKED, None)
        install_label = lv.label(self.install_button)
        install_label.set_text("No update")
        install_label.center()

        self.check_again_button = lv.button(button_row)
        self.check_again_button.set_flex_grow(1)
        self.check_again_button.add_event_cb(lambda e: self.check_again_click(), lv.EVENT.CLICKED, None)
        self.check_again_button.add_flag(lv.obj.FLAG.HIDDEN)
        check_again_label = lv.label(self.check_again_button)
        check_again_label.set_text("Refresh")
        check_again_label.center()

        self.status_label = lv.label(self.main_screen)
        self.status_label.set_text("")
        self.status_label.set_width(lv.pct(100))
        self.status_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.status_label.align_to(button_row, lv.ALIGN.OUT_BOTTOM_LEFT, 0, DisplayMetrics.pct_of_height(2))

        self.changelog_container = lv.obj(self.main_screen)
        self.changelog_container.set_width(lv.pct(100))
        self.changelog_container.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        self.changelog_container.set_style_pad_all(4, lv.PART.MAIN)
        self.changelog_container.align_to(self.status_label, lv.ALIGN.OUT_BOTTOM_LEFT, 0, DisplayMetrics.pct_of_height(1))
        self.changelog_container.set_height(DisplayMetrics.pct_of_height(60))
        self.changelog_container.add_flag(lv.obj.FLAG.HIDDEN)
        self.changelog_container.add_flag(lv.obj.FLAG.SCROLLABLE)
        self.setContentView(self.main_screen)

    def onResume(self, screen):
        super().onResume(screen)
        from osupdate_core import UpdateState
        self._ensure_update_manager()
        self._um.set_state_callback(self._on_um_state_change)
        self._um.suppress_notifications = True
        current_state = self._um.get_state()
        if current_state == UpdateState.IDLE:
            if self._um.connectivity_manager and not self._um.connectivity_manager.is_online():
                self._um.set_state(UpdateState.WAITING_WIFI)
            else:
                self._um.check_for_update_now()
        self._sync_ui(self._um.get_state())

    def onPause(self, screen):
        self._um.clear_state_callback()
        self._um.suppress_notifications = False
        super().onPause(screen)

    def _on_um_state_change(self, state):
        if self.has_foreground():
            self._sync_ui(state)

    def _sync_ui(self, state):
        from osupdate_core import UpdateState

        self.changelog_container.add_flag(lv.obj.FLAG.HIDDEN)

        if state == UpdateState.IDLE:
            self.status_label.set_text("Checking for OS updates...")
            self.check_again_button.remove_flag(lv.obj.FLAG.HIDDEN)
            self.install_button.add_state(lv.STATE.DISABLED)
        elif state == UpdateState.WAITING_WIFI:
            self.status_label.set_text("Waiting for WiFi connection...")
            self.check_again_button.add_flag(lv.obj.FLAG.HIDDEN)
        elif state == UpdateState.CHECKING_UPDATE:
            self.status_label.set_text("Checking for OS updates...")
            self.check_again_button.remove_flag(lv.obj.FLAG.HIDDEN)
        elif state == UpdateState.UPDATE_AVAILABLE:
            info = self._um.get_update_info()
            self._update_install_button(info["comparison"] if info else "newer")
            if info:
                self.status_label.set_text(
                    f"Update version: {info['version']}\n"
                    "Update version is newer.\n\n"
                    "Details:"
                )
                self._populate_changelog(info["changelog"])
                self.changelog_container.remove_flag(lv.obj.FLAG.HIDDEN)
                self._reposition_changelog()
            else:
                self.status_label.set_text("Update available!")
            self.check_again_button.add_flag(lv.obj.FLAG.HIDDEN)
            lv.group_focus_obj(self.install_button)
        elif state == UpdateState.NO_UPDATE:
            info = self._um.get_update_info()
            self._update_install_button(info["comparison"] if info else "same")
            if info:
                self.status_label.set_text(
                    f"Version: {info['version']}\n"
                    f"This version is {info['comparison']}.\n\n"
                    "Details:"
                )
                self._populate_changelog(info["changelog"])
                self.changelog_container.remove_flag(lv.obj.FLAG.HIDDEN)
                self._reposition_changelog()
            else:
                self.status_label.set_text("No updates available.")
            self.check_again_button.add_flag(lv.obj.FLAG.HIDDEN)
            lv.group_focus_obj(self.install_button)
        elif state == UpdateState.DOWNLOADING:
            self.status_label.set_text("Update in progress.\nNavigating away will cancel the update.")
            self.check_again_button.add_flag(lv.obj.FLAG.HIDDEN)
        elif state == UpdateState.DOWNLOAD_PAUSED:
            self.status_label.set_text("Download paused - waiting for WiFi...")
            self.check_again_button.add_flag(lv.obj.FLAG.HIDDEN)
        elif state == UpdateState.ERROR:
            self.status_label.set_text("Failed to check for updates. Check your connection and tap 'Check Again' to retry.")
            self.check_again_button.remove_flag(lv.obj.FLAG.HIDDEN)

    def _populate_changelog(self, changelog_text):
        while self.changelog_container.get_child_count() > 0:
            self.changelog_container.get_child(0).delete()

        if not changelog_text:
            return

        for line in changelog_text.split("\n"):
            label = lv.label(self.changelog_container)
            label.set_text(line if line else " ")
            label.set_width(lv.pct(100))
            label.set_long_mode(lv.label.LONG_MODE.WRAP)
            add_focus_highlight(label)

    def _reposition_changelog(self):
        if not self.changelog_container or self.changelog_container.has_flag(lv.obj.FLAG.HIDDEN):
            return
        ref = self.progress_container or self.status_label
        self.changelog_container.align_to(ref, lv.ALIGN.OUT_BOTTOM_LEFT, 0, DisplayMetrics.pct_of_height(1))
        remaining = DisplayMetrics.height() - self.changelog_container.get_y() - DisplayMetrics.pct_of_height(2)
        if remaining < 0:
            remaining = 0
        self.changelog_container.set_height(remaining)

    def _update_install_button(self, comparison):
        if comparison == "newer":
            text = "Install new version"
        elif comparison == "older":
            text = "Install old version"
        else:
            text = "Install same version"
        install_label = self.install_button.get_child(0)
        install_label.set_text(text)
        install_label.center()
        self.install_button.remove_state(lv.STATE.DISABLED)

    def install_button_click(self):
        if self._downloading:
            self._cancel_requested = True
            return

        info = self._um.get_update_info()
        if not info:
            if __debug__: logger.debug("install clicked but no update info")
            return

        url = info["download_url"]
        if __debug__: logger.debug("install button click for url %s", url)

        self._downloading = True
        self._cancel_requested = False

        install_label = self.install_button.get_child(0)
        install_label.set_text("Cancel update")
        install_label.center()

        self.progress_container = lv.obj(self.main_screen)
        self.progress_container.set_width(lv.pct(100))
        self.progress_container.set_height(lv.SIZE_CONTENT)
        self.progress_container.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        self.progress_container.set_style_pad_all(5, lv.PART.MAIN)
        self.progress_container.set_style_border_width(0, lv.PART.MAIN)
        self.progress_container.align_to(self.status_label, lv.ALIGN.OUT_BOTTOM_LEFT, 0, DisplayMetrics.pct_of_height(1))

        self.progress_label = lv.label(self.progress_container)
        self.progress_label.set_text("OS Update: 0.00%")

        self.speed_label = lv.label(self.progress_container)
        self.speed_label.set_text("Speed: -- KB/s")

        self.progress_bar = lv.bar(self.progress_container)
        self.progress_bar.set_size(lv.pct(80), DisplayMetrics.pct_of_height(6))
        self.progress_bar.set_range(0, 100)
        self.progress_bar.set_value(0, False)

        self._reposition_changelog()

        TaskManager.create_task(self._run_download(url))

    def check_again_click(self):
        if __debug__: logger.debug("Check Again button clicked")
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

    def _hide_progress(self):
        if self.progress_container:
            self.progress_container.add_flag(lv.obj.FLAG.HIDDEN)
        self._reposition_changelog()

    def _should_continue(self):
        return self.has_foreground() and not self._cancel_requested

    def _restore_install_button(self):
        info = self._um.get_update_info()
        comparison = info["comparison"] if info else "newer"
        self._update_install_button(comparison)

    async def _run_download(self, url):
        result = await self._um.start_download(
            url,
            progress_callback=self.async_progress_callback,
            speed_callback=self.async_speed_callback,
            should_continue_callback=self._should_continue
        )

        self._downloading = False
        self._cancel_requested = False

        if not self.has_foreground():
            self._hide_progress()
            return

        if result['success']:
            self.status_label.set_text("Update finished! Restarting...")
            await TaskManager.sleep(5)
            try:
                from osupdate_core import UpdateManager
                UpdateManager.get_instance().update_downloader.set_boot_partition_and_restart()
            except Exception as e:
                logger.error("Failed to set boot partition: %s", e)
                from osupdate_core import format_set_boot_error
                raw_error, friendly_message = format_set_boot_error(e)
                self.status_label.set_text(
                    f"Update failed to activate.\n\n"
                    f"Raw error: {raw_error}\n\n"
                    f"{friendly_message}"
                )
                self._restore_install_button()
                self._hide_progress()
            return

        self._hide_progress()
        self._restore_install_button()

        bytes_written = result.get('bytes_written', 0)
        total_size = result.get('total_size', 0)

        if result.get('timeout'):
            self.status_label.set_text(
                f"Network timeout during download.\n"
                f"{bytes_written}/{total_size} bytes written."
            )
            return

        if result.get('cancelled'):
            self.status_label.set_text(
                f"Update cancelled by user.\n\n"
                f"{bytes_written}/{total_size} bytes downloaded."
            )
            return

        error_msg = result.get('error', 'Unknown error')
        self.status_label.set_text(self._get_user_friendly_error(Exception(error_msg)))

    async def async_progress_callback(self, percent):
        if self.has_foreground() and self.progress_bar:
            self.progress_bar.set_value(int(percent), True)
            self.progress_label.set_text(f"OS Update: {percent:.2f}%")
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
