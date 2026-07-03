import json
import logging

import lvgl as lv

from mpos import Activity, DownloadManager, AppManager, TaskManager

logger = logging.getLogger(__name__)

class AppDetail(Activity):

    action_label_install = "Install"
    action_label_uninstall = "Uninstall"
    action_label_restore = "Restore Built-in"
    action_label_nothing = "Disable" # This could mark builtin apps as "Disabled" somehow and also allow for "Enable" then

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
        installed = AppManager.is_installed_by_name(self.app.fullname)
        if installed:
            self._open_button.remove_flag(lv.obj.FLAG.HIDDEN)
        else:
            self._open_button.add_flag(lv.obj.FLAG.HIDDEN)

    def _set_icon_widget(self):
        if self.app.icon_data:
            dsc = lv.image_dsc_t({
                'data_size': len(self.app.icon_data),
                'data': self.app.icon_data
            })
            self.app._icon_dsc = dsc
            self.app._icon_buf = None
        else:
            dsc, buf = self.appstore._generate_raw_app_icon(self.app.fullname)
            self.app._icon_dsc = dsc
            self.app._icon_buf = buf
        self.icon_image.set_src(dsc)

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

    @staticmethod
    def _extract_main_executable(app_metadata):
        """Return the executable filename marked as main in app_metadata.

        BadgeHub may set one file as the main executable via the
        ``application`` field.  When present, that exact file must be
        downloaded, even if several versions are available.
        """
        if not isinstance(app_metadata, dict):
            return None

        application = app_metadata.get("application")
        if isinstance(application, dict):
            executable = application.get("executable")
            if executable:
                return executable
        elif isinstance(application, list):
            for entry in application:
                if isinstance(entry, dict):
                    executable = entry.get("executable")
                    if executable:
                        return executable

        executable = app_metadata.get("executable")
        if executable:
            return executable

        return None

    @staticmethod
    def _find_download_file(files, preferred_exts, app_version=None, main_executable=None):
        """Pick the best download file from a BadgeHub version object.

        Priority:
        1. The file explicitly named in ``main_executable``.
        2. The ``.mpk``/``.zip`` whose basename ends with ``_<app_version>``.
        3. The first matching file as a safe fallback.
        """
        candidates = []
        for file in files:
            if __debug__: logger.debug("parsing file: %s", file)
            ext = file.get("ext")
            if ext is None:
                continue
            ext = str(ext).lower()
            if __debug__: logger.debug("file has extension: %s", ext)
            if ext in preferred_exts:
                candidates.append(file)

        if not candidates:
            return None

        if main_executable:
            main_lower = str(main_executable).lower()
            for file in candidates:
                full_path = file.get("full_path", "")
                name = file.get("name", "")
                if str(full_path).lower() == main_lower or str(name).lower() == main_lower:
                    return file

        if app_version is not None:
            version_marker = "_{}.mpk".format(app_version)
            version_name_marker = "_{}".format(app_version)
            for file in candidates:
                full_path = file.get("full_path", "")
                name = file.get("name", "")
                if str(full_path).lower().endswith(version_marker):
                    return file
                if str(name).lower().endswith(version_name_marker):
                    return file

        return candidates[0]

    def onCreate(self):
        if __debug__: logger.debug("creating app detail screen")
        self.app = self.getIntent().extras.get("app")
        self.appstore = self.getIntent().extras.get("appstore")
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
        if self.app.publisher:
            self.publisher_label.set_text(self.app.publisher)
        else:
            self.publisher_label.set_text("Unknown publisher")
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
        if self.app.version:
            self.version_label.set_text(f"Latest version: {self.app.version}") # would be nice to make this bold if this is newer than the currently installed one
        else:
            self.version_label.set_text(f"Unknown version")
        self.version_label.set_style_text_font(lv.font_montserrat_12, lv.PART.MAIN)
        self.version_label.align_to(self.install_button, lv.ALIGN.OUT_BOTTOM_MID, 0, lv.pct(5))
        self.long_desc_label = lv.label(app_detail_screen)
        self.long_desc_label.align_to(self.version_label, lv.ALIGN.OUT_BOTTOM_MID, 0, lv.pct(5))
        if self.app.long_description:
            self.long_desc_label.set_text(self.app.long_description)
        else:
            self.long_desc_label.set_text(self.app.short_description)
        self.long_desc_label.set_style_text_font(lv.font_montserrat_12, lv.PART.MAIN)
        self.long_desc_label.set_width(lv.pct(100))

        self._open_button = lv.button(app_detail_screen)
        self._apply_default_styles(self._open_button)
        self._open_button.set_size(60, 42)
        self._open_button.align(lv.ALIGN.TOP_RIGHT, -4, 0)
        self._open_button.add_flag(lv.obj.FLAG.FLOATING)
        self._open_button.add_event_cb(lambda e, a=self.app: self._open_app(a.fullname), lv.EVENT.CLICKED, None)
        open_label = lv.label(self._open_button)
        open_label.set_text("Open")
        open_label.set_style_text_font(lv.font_montserrat_16, lv.PART.MAIN)
        open_label.center()

        if __debug__: logger.debug("loading app detail screen")
        self.setContentView(app_detail_screen)

    def onResume(self, screen):
        self._sync_open_button()
        if not self.app.icon_data and self.app.icon_url and not self._icon_download_started:
            self._icon_download_started = True
            TaskManager.create_task(self._download_icon())
        backend_type = self.appstore.get_backend_type_from_settings()
        if backend_type == self.appstore._BACKEND_API_BADGEHUB:
            TaskManager.create_task(self.fetch_and_set_app_details())
        else:
            if __debug__: logger.debug("no need to fetch app details (index already complete)")

    def add_action_buttons(self, buttoncont, app):
        buttoncont.clean()
        if __debug__: logger.debug("adding (un)install button for url: %s", self.app.download_url)
        self.install_button = lv.button(buttoncont)
        self.install_button.set_style_margin_all(5, lv.PART.MAIN) # without margin, the focus board isnt visible
        self.install_button.add_event_cb(lambda e, a=self.app: self.toggle_install(a), lv.EVENT.CLICKED, None)
        self.install_button.set_size(lv.pct(100), 40)
        self.install_label = lv.label(self.install_button)
        self.install_label.center()
        self.set_install_label(self.app.fullname)
        if app.version and AppManager.is_update_available(self.app.fullname, app.version):
            self.install_button.set_size(lv.pct(47), 40) # make space for update button
            if __debug__: logger.debug("update available, adding update button")
            self.update_button = lv.button(buttoncont)
            self.update_button.set_size(lv.pct(47), 40)
            self.update_button.add_event_cb(lambda e, a=self.app: self.update_button_click(a), lv.EVENT.CLICKED, None)
            update_label = lv.label(self.update_button)
            update_label.set_text("Update")
            update_label.center()

    async def fetch_and_set_app_details(self):
        await self.fetch_badgehub_app_details(self.app)
        if __debug__: logger.debug("app has version: %s", self.app.version)
        self.version_label.set_text(self.app.version)
        self.long_desc_label.set_text(self.app.long_description)
        self.publisher_label.set_text(self.app.publisher)
        self.add_action_buttons(self.buttoncont, self.app)
        self._sync_open_button()

    def set_install_label(self, app_fullname):
        # Figure out whether to show:
        # - "install" option if not installed
        # - "update" option if already installed and new version
        # - "uninstall" option if already installed and not builtin
        # - "restore builtin" option if it's an overridden builtin app
        # So:
        # - install, uninstall and restore builtin can be same button, always shown
        # - update is separate button, only shown if already installed and new version
        is_installed = True
        update_available = False
        builtin_app = AppManager.is_builtin_app(app_fullname)
        overridden_builtin_app = AppManager.is_overridden_builtin_app(app_fullname)
        if not overridden_builtin_app:
            is_installed = AppManager.is_installed_by_name(app_fullname)
        if is_installed:
            if builtin_app:
                if overridden_builtin_app:
                    action_label = self.action_label_restore
                else:
                    action_label = self.action_label_nothing
            else:
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
            if __debug__: logger.debug("starting install task")
            TaskManager.create_task(self.download_and_install(app_obj, f"apps/{fullname}"))
        elif label_text == self.action_label_uninstall or label_text == self.action_label_restore:
            if __debug__: logger.debug("starting uninstall task")
            TaskManager.create_task(self.uninstall_app(fullname))
    
    def update_button_click(self, app_obj):
        download_url = app_obj.download_url
        fullname = app_obj.fullname
        if __debug__: logger.debug("update button clicked for %s and fullname %s", download_url, fullname)
        self.update_button.add_flag(lv.obj.FLAG.HIDDEN)
        self.install_button.set_size(lv.pct(100), 40)
        TaskManager.create_task(self.download_and_install(app_obj, f"apps/{fullname}"))

    async def uninstall_app(self, app_fullname):
        self.install_button.add_state(lv.STATE.DISABLED)
        self.install_label.set_text("Please wait...")
        self._show_progress_bar()
        await self._update_progress(21)
        await self._update_progress(42)
        AppManager.uninstall_app(app_fullname)
        await self._update_progress(100, wait=False)
        self._hide_progress_bar()
        self.set_install_label(app_fullname)
        self._sync_open_button()
        self.install_button.remove_state(lv.STATE.DISABLED)
        self._trigger_update_recheck()
        if AppManager.is_builtin_app(app_fullname):
            self.update_button.remove_flag(lv.obj.FLAG.HIDDEN)
            self.install_button.set_size(lv.pct(47), 40) # if a builtin app was removed, then it was overridden, and a new version is available, so make space for update button

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
        self.install_button.add_state(lv.STATE.DISABLED)
        self.install_label.set_text("Please wait...")
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
            self._hide_progress_bar()
            return
        # TODO: report the install if badgehub /report/install is fixed
        await self._update_progress(100, wait=False)
        self._hide_progress_bar()
        self.set_install_label(app_fullname)
        self._sync_open_button()
        self.install_button.remove_state(lv.STATE.DISABLED)
        # Notify AppUpdateManager that an app was installed so it can refresh its state
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
        details_url = self.appstore.get_backend_details_url_from_settings() + "/" + app_obj.fullname
        try:
            response = await DownloadManager.download_url(details_url)
        except Exception as e:
            logger.warning("could not download app details from %s: %s", details_url, e)
            if DownloadManager.is_network_error(e):
                if __debug__: logger.debug("network error while fetching app details")
            return
        if __debug__: logger.debug("fetched app details response: %s", response[:42])
        try:
            parsed = json.loads(response)
            if __debug__: logger.debug("finding version number")
            try:
                version = parsed.get("version")
            except Exception as e:
                logger.warning("could not get version from app details: %s", e)
                return
            if __debug__: logger.debug("got version object: %s", version)

            try:
                app_metadata = version.get("app_metadata")
            except Exception as e:
                logger.warning("could not get app_metadata from version: %s", e)
                return

            # version
            try:
                app_version = app_metadata.get("version")
                if __debug__: logger.debug("app has app_version: %s", app_version)
                app_obj.version = app_version
            except Exception as e:
                logger.warning("could not get version from app_metadata: %s", e)

            # Find .mpk download URL, preferring the explicitly-marked main
            # executable and then matching the displayed version.
            try:
                files = version.get("files")
                main_executable = self._extract_main_executable(app_metadata)
                download_file = self._find_download_file(
                    files,
                    [".mpk", ".zip"],
                    app_version=app_version,
                    main_executable=main_executable,
                )
                if download_file:
                    app_obj.download_url = download_file.get("url")
                    app_obj.download_url_size = download_file.get("size_of_content")
                    if __debug__: logger.debug("selected download file for %s: %s", app_obj.fullname, download_file.get("full_path"))
            except Exception as e:
                logger.warning("could not get files from version: %s", e)

            # publisher / author:
            try:
                app_obj.publisher = app_metadata.get("author")
            except Exception as e:
                logger.warning("could not get author from version: %s", e)
            # long_description
            try:
                app_obj.long_description = app_metadata.get("long_description")
            except Exception as e:
                logger.warning("could not get long_description from version: %s", e)
        except Exception as e:
            err = f"ERROR: could not parse app details JSON: {e}"
            logger.error(err)
            self.appstore.please_wait_label.set_text(err)
            return
