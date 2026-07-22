import logging

import lvgl as lv

from mpos import Activity, DownloadManager, AppManager, TaskManager
from blurhash import blurhash_to_image_dsc, generate_raw_app_icon

logger = logging.getLogger(__name__)

class AppDetail(Activity):

    action_label_install = "Install"
    action_label_uninstall = "Uninstall"

    # Widgets:
    install_button = None
    update_button = None
    progress_bar = None
    install_label = None
    long_desc_label = None
    version_label = None
    buttoncont = None
    publisher_label = None
    _open_button = None
    icon_image = None
    _icon_download_started = False

    # Received from the Intent extras:
    app = None
    appstore = None

    def _open_app(self, app_fullname):
        AppManager.start_app(app_fullname)

    def _sync_open_button(self):
        if self._open_button is None:
            return
        if AppManager.is_installed_by_name(self.app.fullname):
            self._open_button.remove_flag(lv.obj.FLAG.HIDDEN)
        else:
            self._open_button.add_flag(lv.obj.FLAG.HIDDEN)

    def _set_icon_widget(self):
        if self.app.icon_data:
            dsc = lv.image_dsc_t({
                'data_size': len(self.app.icon_data),
                'data': self.app.icon_data
            })
            scale = 256
            buf = None
        else:
            dsc, buf = blurhash_to_image_dsc(self.app.blur_hash, 16, 16)
            if dsc is None:
                dsc, buf = generate_raw_app_icon(self.app.fullname, 64)
                scale = 256
            else:
                scale = 4 * 256
        self.app._icon_dsc = dsc
        self.app._icon_buf = buf
        self.icon_image.set_src(dsc)
        self.icon_image.set_scale(scale)

    async def _download_icon(self):
        if not self.app.icon_url:
            return
        if __debug__: logger.debug("downloading icon for %s from %s", self.app.fullname, self.app.icon_url)
        try:
            self.app.icon_data = await TaskManager.wait_for(DownloadManager.download_url(self.app.icon_url), 5)
        except Exception as e:
            if __debug__: logger.debug("download of %s failed: %s", self.app.icon_url, e)
            self._icon_download_started = False
            return
        if self.app.icon_data:
            self._set_icon_widget()
            try:
                self.appstore._set_icon_widget(self.app)
            except Exception as e:
                if __debug__: logger.debug("could not update list icon for %s: %s", self.app.fullname, e)

    @staticmethod
    def _apply_default_styles(widget, border=0, radius=0, pad=0):
        """Apply common default styles to reduce repetition"""
        widget.set_style_border_width(border, lv.PART.MAIN)
        widget.set_style_radius(radius, lv.PART.MAIN)
        widget.set_style_pad_all(pad, lv.PART.MAIN)

    async def _update_progress(self, value, wait=True):
        """Update progress bar with optional wait"""
        self.progress_bar.set_value(value, wait)
        if wait:
            await TaskManager.sleep(1)

    def _show_progress_bar(self):
        """Show progress bar and reset to 0"""
        self.progress_bar.remove_flag(lv.obj.FLAG.HIDDEN)
        self.progress_bar.set_value(0, False)

    def _hide_progress_bar(self):
        """Hide progress bar and reset to 0"""
        self.progress_bar.set_value(0, False)
        self.progress_bar.add_flag(lv.obj.FLAG.HIDDEN)

    def onCreate(self):
        if __debug__: logger.debug("creating app detail screen")
        self.app = self.getIntent().extras.get("app")
        self.appstore = self.getIntent().extras.get("appstore")
        self._action_in_progress = False
        app_detail_screen = lv.obj()
        app_detail_screen.set_style_pad_all(5, lv.PART.MAIN)
        app_detail_screen.set_size(lv.pct(100), lv.pct(100))
        app_detail_screen.set_pos(0, 40)
        app_detail_screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)

        headercont = lv.obj(app_detail_screen)
        self._apply_default_styles(headercont)
        headercont.set_flex_flow(lv.FLEX_FLOW.ROW)
        headercont.set_size(lv.pct(100), lv.SIZE_CONTENT)
        headercont.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        self.icon_image = lv.image(headercont)
        self.icon_image.set_size(64, 64)
        self._set_icon_widget()
        detail_cont = lv.obj(headercont)
        self._apply_default_styles(detail_cont)
        detail_cont.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        detail_cont.set_size(lv.pct(75), lv.SIZE_CONTENT)
        detail_cont.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        name_label = lv.label(detail_cont)
        name_label.set_text(self.app.name)
        name_label.set_style_text_font(lv.font_montserrat_24, lv.PART.MAIN)
        self.publisher_label = lv.label(detail_cont)
        self.publisher_label.set_text(self.app.publisher or "Loading details...")
        self.publisher_label.set_style_text_font(lv.font_montserrat_16, lv.PART.MAIN)

        self.progress_bar = lv.bar(app_detail_screen)
        self.progress_bar.set_width(lv.pct(100))
        self.progress_bar.set_range(0, 100)
        self.progress_bar.add_flag(lv.obj.FLAG.HIDDEN)
        # Always have this button:
        self.buttoncont = lv.obj(app_detail_screen)
        self._apply_default_styles(self.buttoncont)
        self.buttoncont.set_flex_flow(lv.FLEX_FLOW.ROW)
        self.buttoncont.set_size(lv.pct(100), lv.SIZE_CONTENT)
        self.buttoncont.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        self.add_action_buttons(self.buttoncont, self.app)
        # version label:
        self.version_label = lv.label(app_detail_screen)
        self.version_label.set_width(lv.pct(100))
        self.version_label.set_text(self.app.version and f"Latest version: {self.app.version}" or "Loading details...")
        self.version_label.set_style_text_font(lv.font_montserrat_12, lv.PART.MAIN)
        self.version_label.align_to(self.install_button, lv.ALIGN.OUT_BOTTOM_MID, 0, lv.pct(5))
        self.long_desc_label = lv.label(app_detail_screen)
        self.long_desc_label.align_to(self.version_label, lv.ALIGN.OUT_BOTTOM_MID, 0, lv.pct(5))
        self.long_desc_label.set_text(self.app.long_description or self.app.short_description or "Loading details...")
        self.long_desc_label.set_style_text_font(lv.font_montserrat_12, lv.PART.MAIN)
        self.long_desc_label.set_width(lv.pct(100))

        if __debug__: logger.debug("loading app detail screen")
        self.setContentView(app_detail_screen)

    def onResume(self, screen):
        self._sync_open_button()
        backend_type = self.appstore.get_backend_type_from_settings()
        if backend_type == self.appstore._BACKEND_API_BADGEHUB:
            TaskManager.create_task(self.fetch_and_set_app_details())
        else:
            if __debug__: logger.debug("no need to fetch app details (index already complete)")
            self._start_icon_download()

    def _start_icon_download(self):
        if not self.app.icon_data and self.app.icon_url and not self._icon_download_started:
            self._icon_download_started = True
            lv.timer_create(lambda t: (t.delete(), TaskManager.create_task(self._download_icon())), 500, None)

    def add_action_buttons(self, buttoncont, app):
        buttoncont.clean()
        if __debug__: logger.debug("adding (un)install button for url: %s", self.app.download_url)
        self.install_button = lv.button(buttoncont)
        self.install_button.set_style_margin_all(5, lv.PART.MAIN)
        self.install_button.set_flex_grow(1)
        self.install_button.add_event_cb(lambda e, a=self.app: self.toggle_install(a), lv.EVENT.CLICKED, None)
        self.install_label = lv.label(self.install_button)
        self.install_label.center()
        self.set_install_label(self.app.fullname)
        self.update_button = None
        if app.version and AppManager.is_update_available(self.app.fullname, app.version):
            if __debug__: logger.debug("update available, adding update button")
            self.update_button = lv.button(buttoncont)
            self.update_button.set_style_margin_all(5, lv.PART.MAIN)
            self.update_button.set_flex_grow(1)
            self.update_button.add_event_cb(lambda e, a=self.app: self.update_button_click(a), lv.EVENT.CLICKED, None)
            update_label = lv.label(self.update_button)
            update_label.set_text("Update")
            update_label.center()
        self._open_button = lv.button(buttoncont)
        self._open_button.set_style_margin_all(5, lv.PART.MAIN)
        self._open_button.set_size(lv.SIZE_CONTENT, 40)
        self._open_button.add_event_cb(lambda e, a=self.app: self._open_app(a.fullname), lv.EVENT.CLICKED, None)
        open_label = lv.label(self._open_button)
        open_label.set_text("Open")
        open_label.set_style_text_font(lv.font_montserrat_16, lv.PART.MAIN)
        open_label.center()
        self._sync_open_button()

    async def fetch_and_set_app_details(self):
        await self.fetch_badgehub_app_details(self.app)
        if __debug__: logger.debug("app has version: %s", self.app.version)
        self.version_label.set_text(self.app.version)
        self.long_desc_label.set_text(self.app.long_description)
        self.publisher_label.set_text(self.app.publisher)
        if not self._action_in_progress:
            self.add_action_buttons(self.buttoncont, self.app)
        self._sync_open_button()
        self._start_icon_download()

    def set_install_label(self, app_fullname):
        if AppManager.is_installed_by_name(app_fullname):
            action_label = self.action_label_uninstall
        else:
            action_label = self.action_label_install
        self.install_label.set_text(action_label)

    def toggle_install(self, app_obj):
        if __debug__: logger.debug("install button clicked for %s", app_obj)
        download_url = app_obj.download_url
        fullname = app_obj.fullname
        if __debug__: logger.debug("with %s and fullname %s", download_url, fullname)
        label_text = self.install_label.get_text()
        if label_text == self.action_label_install:
            if not download_url:
                if __debug__: logger.debug("no download_url yet, ignoring")
                return
            if __debug__: logger.debug("starting install task")
            self._action_in_progress = True
            self.install_button.add_state(lv.STATE.DISABLED)
            self.install_label.set_text("Please wait...")
            TaskManager.create_task(self.download_and_install(app_obj, f"apps/{fullname}"))
        elif label_text == self.action_label_uninstall:
            if __debug__: logger.debug("starting uninstall task")
            self._action_in_progress = True
            self.install_button.add_state(lv.STATE.DISABLED)
            self.install_label.set_text("Please wait...")
            TaskManager.create_task(self.uninstall_app(fullname))
    
    def update_button_click(self, app_obj):
        download_url = app_obj.download_url
        fullname = app_obj.fullname
        if __debug__: logger.debug("update button clicked for %s and fullname %s", download_url, fullname)
        self._action_in_progress = True
        self.update_button.add_flag(lv.obj.FLAG.HIDDEN)
        self.install_button.add_state(lv.STATE.DISABLED)
        self.install_label.set_text("Please wait...")
        TaskManager.create_task(self.download_and_install(app_obj, f"apps/{fullname}"))

    async def uninstall_app(self, app_fullname):
        self._show_progress_bar()
        await self._update_progress(21)
        await self._update_progress(42)
        AppManager.uninstall_app(app_fullname)
        await self._update_progress(100, wait=False)
        self._hide_progress_bar()
        self._action_in_progress = False
        self.add_action_buttons(self.buttoncont, self.app)
        self._trigger_update_recheck()

    async def pcb(self, percent):
        if __debug__: logger.debug("pcb: %s", percent)
        scaled_percent_start = 5 # before 5% is preparation
        scaled_percent_finished = 60 # after 60% is unzip
        scaled_percent_diff = scaled_percent_finished - scaled_percent_start
        scale = 100 / scaled_percent_diff # 100 / 55 = 1.81
        scaled_percent = round(percent / scale)
        scaled_percent += scaled_percent_start
        self.progress_bar.set_value(scaled_percent, True)

    async def download_and_install(self, app_obj, dest_folder):
        app_fullname = app_obj.fullname
        download_url_size = getattr(app_obj, "download_url_size", None)
        self._show_progress_bar()
        await self._update_progress(5)
        try:
            await AppManager.download_and_install_package(
                app_obj.download_url,
                app_fullname,
                download_url_size=download_url_size,
                progress_callback=self.pcb,
            )
        except Exception as e:
            logger.error("download failed: %s", e)
            if DownloadManager.is_network_error(e):
                self.install_label.set_text(f"Network error - check WiFi")
            elif "Not enough free space" in str(e):
                self.install_label.set_text(f"Not enough space")
            else:
                self.install_label.set_text(f"Download failed: {str(e)[:30]}")
            self.install_button.remove_state(lv.STATE.DISABLED)
            self._action_in_progress = False
            self._hide_progress_bar()
            return
        backend_type = self.appstore.get_backend_type_from_settings()
        if backend_type == self.appstore._BACKEND_API_BADGEHUB:
            revision = getattr(app_obj, "revision", None)
            if revision is not None:
                from appstore_core import report_badgehub_install
                TaskManager.create_task(report_badgehub_install(app_obj.fullname, revision))
        await self._update_progress(100, wait=False)
        self._hide_progress_bar()
        self._action_in_progress = False
        self.add_action_buttons(self.buttoncont, self.app)
        self._trigger_update_recheck()

    def _trigger_update_recheck(self):
        """Ask AppUpdateManager to re-evaluate which apps need updates.

        Called after a successful install or uninstall so the notification and
        AppStore banner stay in sync without requiring a full app-index download.
        """
        try:
            AppManager.refresh_apps()
            from appstore_core import AppUpdateManager
            TaskManager.create_task(AppUpdateManager.get_instance().check_for_updates())
        except Exception as e:
            logger.warning("could not schedule update recheck: %s", e)

    async def fetch_badgehub_app_details(self, app_obj):
        from appstore_core import fetch_badgehub_project_details
        details_url = self.appstore.get_backend_details_url_from_settings() + "/" + app_obj.fullname
        result = await fetch_badgehub_project_details(details_url)
        if not result:
            return
        if result.get("version"):
            app_obj.version = result["version"]
        if result.get("download_url"):
            app_obj.download_url = result["download_url"]
            app_obj.download_url_size = result.get("download_url_size")
        if result.get("publisher"):
            app_obj.publisher = result["publisher"]
        if result.get("long_description"):
            app_obj.long_description = result["long_description"]
        if result.get("revision") is not None:
            app_obj.revision = result["revision"]
