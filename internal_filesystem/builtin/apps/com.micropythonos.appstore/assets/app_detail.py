import os
import json
import lvgl as lv

from mpos import Activity, DownloadManager, PackageManager, TaskManager

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

    # Received from the Intent extras:
    app = None
    appstore = None

    @staticmethod
    def _apply_default_styles(widget, border=0, radius=0, pad=0):
        """Apply common default styles to reduce repetition"""
        widget.set_style_border_width(border, 0)
        widget.set_style_radius(radius, 0)
        widget.set_style_pad_all(pad, 0)

    def _cleanup_temp_file(self, path="tmp/temp.mpk"):
        """Safely remove temporary file"""
        try:
            os.remove(path)
        except Exception:
            pass

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
        print("Creating app detail screen...")
        self.app = self.getIntent().extras.get("app")
        self.appstore = self.getIntent().extras.get("appstore")
        app_detail_screen = lv.obj()
        app_detail_screen.set_style_pad_all(5, 0)
        app_detail_screen.set_size(lv.pct(100), lv.pct(100))
        app_detail_screen.set_pos(0, 40)
        app_detail_screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)

        headercont = lv.obj(app_detail_screen)
        self._apply_default_styles(headercont)
        headercont.set_flex_flow(lv.FLEX_FLOW.ROW)
        headercont.set_size(lv.pct(100), lv.SIZE_CONTENT)
        headercont.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        icon_spacer = lv.image(headercont)
        icon_spacer.set_size(64, 64)
        if self.app.icon_data:
            image_dsc = lv.image_dsc_t({
                'data_size': len(self.app.icon_data),
                'data': self.app.icon_data
            })
            icon_spacer.set_src(image_dsc)
        else:
            icon_spacer.set_src(lv.SYMBOL.IMAGE)
        detail_cont = lv.obj(headercont)
        self._apply_default_styles(detail_cont)
        detail_cont.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        detail_cont.set_size(lv.pct(75), lv.SIZE_CONTENT)
        detail_cont.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        name_label = lv.label(detail_cont)
        name_label.set_text(self.app.name)
        name_label.set_style_text_font(lv.font_montserrat_24, 0)
        self.publisher_label = lv.label(detail_cont)
        if self.app.publisher:
            self.publisher_label.set_text(self.app.publisher)
        else:
            self.publisher_label.set_text("Unknown publisher")
        self.publisher_label.set_style_text_font(lv.font_montserrat_16, 0)

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
        self.version_label.set_style_text_font(lv.font_montserrat_12, 0)
        self.version_label.align_to(self.install_button, lv.ALIGN.OUT_BOTTOM_MID, 0, lv.pct(5))
        self.long_desc_label = lv.label(app_detail_screen)
        self.long_desc_label.align_to(self.version_label, lv.ALIGN.OUT_BOTTOM_MID, 0, lv.pct(5))
        if self.app.long_description:
            self.long_desc_label.set_text(self.app.long_description)
        else:
            self.long_desc_label.set_text(self.app.short_description)
        self.long_desc_label.set_style_text_font(lv.font_montserrat_12, 0)
        self.long_desc_label.set_width(lv.pct(100))
        print("Loading app detail screen...")
        self.setContentView(app_detail_screen)

    def onResume(self, screen):
        backend_type = self.appstore.get_backend_type_from_settings()
        if backend_type == self.appstore._BACKEND_API_BADGEHUB:
            TaskManager.create_task(self.fetch_and_set_app_details())
        else:
            print("No need to fetch app details as the github app index already contains all the app data.")

    def add_action_buttons(self, buttoncont, app):
        buttoncont.clean()
        print(f"Adding (un)install button for url: {self.app.download_url}")
        self.install_button = lv.button(buttoncont)
        self.install_button.add_event_cb(lambda e, a=self.app: self.toggle_install(a), lv.EVENT.CLICKED, None)
        self.install_button.set_size(lv.pct(100), 40)
        self.install_label = lv.label(self.install_button)
        self.install_label.center()
        self.set_install_label(self.app.fullname)
        if app.version and PackageManager.is_update_available(self.app.fullname, app.version):
            self.install_button.set_size(lv.pct(47), 40) # make space for update button
            print("Update available, adding update button.")
            self.update_button = lv.button(buttoncont)
            self.update_button.set_size(lv.pct(47), 40)
            self.update_button.add_event_cb(lambda e, a=self.app: self.update_button_click(a), lv.EVENT.CLICKED, None)
            update_label = lv.label(self.update_button)
            update_label.set_text("Update")
            update_label.center()

    async def fetch_and_set_app_details(self):
        await self.fetch_badgehub_app_details(self.app)
        print(f"app has version: {self.app.version}")
        self.version_label.set_text(self.app.version)
        self.long_desc_label.set_text(self.app.long_description)
        self.publisher_label.set_text(self.app.publisher)
        self.add_action_buttons(self.buttoncont, self.app)

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
        builtin_app = PackageManager.is_builtin_app(app_fullname)
        overridden_builtin_app = PackageManager.is_overridden_builtin_app(app_fullname)
        if not overridden_builtin_app:
            is_installed = PackageManager.is_installed_by_name(app_fullname)
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
        print(f"Install button clicked for {app_obj}")
        download_url = app_obj.download_url
        fullname = app_obj.fullname
        print(f"With {download_url} and fullname {fullname}")
        label_text = self.install_label.get_text()
        if label_text == self.action_label_install:
            print("Starting install task...")
            TaskManager.create_task(self.download_and_install(app_obj, f"apps/{fullname}"))
        elif label_text == self.action_label_uninstall or label_text == self.action_label_restore:
            print("Starting uninstall task...")
            TaskManager.create_task(self.uninstall_app(fullname))
    
    def update_button_click(self, app_obj):
        download_url = app_obj.download_url
        fullname = app_obj.fullname
        print(f"Update button clicked for {download_url} and fullname {fullname}")
        self.update_button.add_flag(lv.obj.FLAG.HIDDEN)
        self.install_button.set_size(lv.pct(100), 40)
        TaskManager.create_task(self.download_and_install(app_obj, f"apps/{fullname}"))

    async def uninstall_app(self, app_fullname):
        self.install_button.add_state(lv.STATE.DISABLED)
        self.install_label.set_text("Please wait...")
        self._show_progress_bar()
        await self._update_progress(21)
        await self._update_progress(42)
        PackageManager.uninstall_app(app_fullname)
        await self._update_progress(100, wait=False)
        self._hide_progress_bar()
        self.set_install_label(app_fullname)
        self.install_button.remove_state(lv.STATE.DISABLED)
        if PackageManager.is_builtin_app(app_fullname):
            self.update_button.remove_flag(lv.obj.FLAG.HIDDEN)
            self.install_button.set_size(lv.pct(47), 40) # if a builtin app was removed, then it was overridden, and a new version is available, so make space for update button

    async def pcb(self, percent):
        print(f"pcb called: {percent}")
        scaled_percent_start = 5 # before 5% is preparation
        scaled_percent_finished = 60 # after 60% is unzip
        scaled_percent_diff = scaled_percent_finished - scaled_percent_start
        scale = 100 / scaled_percent_diff # 100 / 55 = 1.81
        scaled_percent = round(percent / scale)
        scaled_percent += scaled_percent_start
        self.progress_bar.set_value(scaled_percent, True)

    async def download_and_install(self, app_obj, dest_folder):
        zip_url = app_obj.download_url
        app_fullname = app_obj.fullname
        download_url_size = getattr(app_obj, "download_url_size", None)
        temp_zip_path = "tmp/temp.mpk"
        self.install_button.add_state(lv.STATE.DISABLED)
        self.install_label.set_text("Please wait...")
        self._show_progress_bar()
        await self._update_progress(5)
        # Download the .mpk file to temporary location
        self._cleanup_temp_file(temp_zip_path)
        try:
            os.mkdir("tmp")
        except Exception:
            pass
        print(f"Downloading .mpk file from: {zip_url} to {temp_zip_path}")
        try:
            result = await DownloadManager.download_url(zip_url, outfile=temp_zip_path, total_size=download_url_size, progress_callback=self.pcb)
            if result is not True:
                print("Download failed...") # Would be good to show an error to the user if this failed...
            else:
                print("Downloaded .mpk file, size:", os.stat(temp_zip_path)[6], "bytes")
                # Install it:
                PackageManager.install_mpk(temp_zip_path, dest_folder) # 60 until 90 percent is the unzip but no progress there...
                await self._update_progress(90, wait=False)
        except Exception as e:
            print(f"Download failed with exception: {e}")
            if DownloadManager.is_network_error(e):
                self.install_label.set_text(f"Network error - check WiFi")
            else:
                self.install_label.set_text(f"Download failed: {str(e)[:30]}")
            self.install_button.remove_state(lv.STATE.DISABLED)
            self._hide_progress_bar()
            self._cleanup_temp_file(temp_zip_path)
            return
        # Make sure there's no leftover file filling the storage:
        self._cleanup_temp_file(temp_zip_path)
        # Success:
        await self._update_progress(100, wait=False)
        self._hide_progress_bar()
        self.set_install_label(app_fullname)
        self.install_button.remove_state(lv.STATE.DISABLED)

    async def fetch_badgehub_app_details(self, app_obj):
        details_url = self.appstore.get_backend_details_url_from_settings() + "/" + app_obj.fullname
        try:
            response = await DownloadManager.download_url(details_url)
        except Exception as e:
            print(f"Could not download app details from {details_url}: {e}")
            if DownloadManager.is_network_error(e):
                print("Network error while fetching app details")
            return
        print(f"Got response text: {response[0:20]}")
        try:
            parsed = json.loads(response)
            #print(f"parsed json: {parsed}")
            print("Using short_description as long_description because backend doesn't support it...")
            app_obj.long_description = app_obj.short_description
            print("Finding version number...")
            try:
                version = parsed.get("version")
            except Exception as e:
                print(f"Could not get version object from appdetails: {e}")
                return
            print(f"got version object: {version}")
            # Find .mpk download URL:
            try:
                files = version.get("files")
                for file in files:
                    print(f"parsing file: {file}")
                    ext = file.get("ext").lower()
                    print(f"file has extension: {ext}")
                    if ext == ".mpk":
                        app_obj.download_url = file.get("url")
                        app_obj.download_url_size = file.get("size_of_content")
                        break # only one .mpk per app is supported
            except Exception as e:
                print(f"Could not get files from version: {e}")
            try:
                app_metadata = version.get("app_metadata")
            except Exception as e:
                print(f"Could not get app_metadata object from version object: {e}")
                return
            try:
                app_obj.publisher = app_metadata.get("author")
            except Exception as e:
                print(f"Could not get author from version object: {e}")
            try:
                app_version = app_metadata.get("version")
                print(f"what: {version.get('app_metadata')}")
                print(f"app has app_version: {app_version}")
                app_obj.version = app_version
            except Exception as e:
                print(f"Could not get version from app_metadata: {e}")
        except Exception as e:
            err = f"ERROR: could not parse app details JSON: {e}"
            print(err)
            self.appstore.please_wait_label.set_text(err)
            return
