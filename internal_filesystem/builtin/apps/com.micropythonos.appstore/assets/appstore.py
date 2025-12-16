import aiohttp
import lvgl as lv
import json
import requests
import gc
import os

from mpos.apps import Activity, Intent
from mpos.app import App
from mpos import TaskManager
import mpos.ui
from mpos.content.package_manager import PackageManager

class AppStore(Activity):

    _BADGEHUB_API_BASE_URL = "https://badgehub.p1m.nl/api/v3"
    _BADGEHUB_LIST = "project-summaries?badge=fri3d_2024"
    _BADGEHUB_DETAILS = "projects"

    _BACKEND_API_GITHUB = "github"
    _BACKEND_API_BADGEHUB = "badgehub"

    apps = []
    # These might become configurations:
    #backend_api = _BACKEND_API_BADGEHUB
    backend_api = _BACKEND_API_GITHUB
    app_index_url_github = "https://apps.micropythonos.com/app_index.json"
    app_index_url_badgehub = _BADGEHUB_API_BASE_URL + "/" + _BADGEHUB_LIST
    app_detail_url_badgehub = _BADGEHUB_API_BASE_URL + "/" + _BADGEHUB_DETAILS
    can_check_network = True
    aiohttp_session = None # one session for the whole app is more performant

    # Widgets:
    main_screen = None
    update_button = None
    install_button = None
    install_label = None
    please_wait_label = None
    progress_bar = None

    def onCreate(self):
        self.aiohttp_session = aiohttp.ClientSession()
        self.main_screen = lv.obj()
        self.please_wait_label = lv.label(self.main_screen)
        self.please_wait_label.set_text("Downloading app index...")
        self.please_wait_label.center()
        self.setContentView(self.main_screen)

    def onResume(self, screen):
        super().onResume(screen)
        if len(self.apps):
            return # already downloaded them
        try:
            import network
        except Exception as e:
            self.can_check_network = False
        if self.can_check_network and not network.WLAN(network.STA_IF).isconnected():
            self.please_wait_label.set_text("Error: WiFi is not connected.")
        else:
            if self.backend_api == self._BACKEND_API_BADGEHUB:
                TaskManager.create_task(self.download_app_index(self.app_index_url_badgehub))
            else:
                TaskManager.create_task(self.download_app_index(self.app_index_url_github))

    def onDestroy(self, screen):
        await self.aiohttp_session.close()

    async def download_app_index(self, json_url):
        response = await self.download_url(json_url)
        if not response:
            self.please_wait_label.set_text(f"Could not download app index from\n{json_url}")
            return
        print(f"Got response text: {response[0:20]}")
        try:
            parsed = json.loads(response)
            print(f"parsed json: {parsed}")
            for app in parsed:
                try:
                    if self.backend_api == self._BACKEND_API_BADGEHUB:
                        self.apps.append(AppStore.badgehub_app_to_mpos_app(app))
                    else:
                        self.apps.append(App(app["name"], app["publisher"], app["short_description"], app["long_description"], app["icon_url"], app["download_url"], app["fullname"], app["version"], app["category"], app["activities"]))
                except Exception as e:
                    print(f"Warning: could not add app from {json_url} to apps list: {e}")
        except Exception as e:
            self.please_wait_label.set_text(f"ERROR: could not parse reponse.text JSON: {e}")
            return
        self.please_wait_label.set_text(f"Download successful, building list...")
        await TaskManager.sleep(0.1) # give the UI time to display the app list before starting to download
        print("Remove duplicates based on app.name")
        seen = set()
        self.apps = [app for app in self.apps if not (app.fullname in seen or seen.add(app.fullname))]
        print("Sort apps by app.name")
        self.apps.sort(key=lambda x: x.name.lower())  # Use .lower() for case-insensitive sorting
        print("Creating apps list...")
        self.create_apps_list()
        await TaskManager.sleep(0.1) # give the UI time to display the app list before starting to download
        print("awaiting self.download_icons()")
        await self.download_icons()

    def create_apps_list(self):
        print("create_apps_list")
        print("Hiding please wait label...")
        self.please_wait_label.add_flag(lv.obj.FLAG.HIDDEN)
        apps_list = lv.list(self.main_screen)
        apps_list.set_style_border_width(0, 0)
        apps_list.set_style_radius(0, 0)
        apps_list.set_style_pad_all(0, 0)
        apps_list.set_size(lv.pct(100), lv.pct(100))
        self._icon_widgets = {} # Clear old icons
        print("create_apps_list iterating")
        for app in self.apps:
            print(app)
            item = apps_list.add_button(None, "Test")
            item.set_style_pad_all(0, 0)
            item.set_size(lv.pct(100), lv.SIZE_CONTENT)
            item.add_event_cb(lambda e, a=app: self.show_app_detail(a), lv.EVENT.CLICKED, None)
            cont = lv.obj(item)
            cont.set_style_pad_all(0, 0)
            cont.set_flex_flow(lv.FLEX_FLOW.ROW)
            cont.set_size(lv.pct(100), lv.SIZE_CONTENT)
            cont.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
            cont.set_style_border_width(0, 0)
            cont.set_style_radius(0, 0)
            cont.add_event_cb(lambda e, a=app: self.show_app_detail(a), lv.EVENT.CLICKED, None)
            icon_spacer = lv.image(cont)
            icon_spacer.set_size(64, 64)
            icon_spacer.set_src(lv.SYMBOL.REFRESH)
            icon_spacer.add_event_cb(lambda e, a=app: self.show_app_detail(a), lv.EVENT.CLICKED, None)
            app.image_icon_widget = icon_spacer # save it so it can be later set to the actual image
            label_cont = lv.obj(cont)
            label_cont.set_style_border_width(0, 0)
            label_cont.set_style_radius(0, 0)
            label_cont.set_flex_flow(lv.FLEX_FLOW.COLUMN)
            label_cont.set_size(lv.pct(75), lv.SIZE_CONTENT)
            label_cont.add_event_cb(lambda e, a=app: self.show_app_detail(a), lv.EVENT.CLICKED, None)
            name_label = lv.label(label_cont)
            name_label.set_text(app.name)
            name_label.set_style_text_font(lv.font_montserrat_16, 0)
            name_label.add_event_cb(lambda e, a=app: self.show_app_detail(a), lv.EVENT.CLICKED, None)
            desc_label = lv.label(label_cont)
            desc_label.set_text(app.short_description)
            desc_label.set_style_text_font(lv.font_montserrat_12, 0)
            desc_label.add_event_cb(lambda e, a=app: self.show_app_detail(a), lv.EVENT.CLICKED, None)
        print("create_apps_list app done")

    async def download_icons(self):
        print("Downloading icons...")
        for app in self.apps:
            if not self.has_foreground():
                print(f"App is stopping, aborting icon downloads.") # maybe this can continue? but then update_ui_if_foreground is needed
                break
            if not app.icon_data:
                try:
                    app.icon_data = await TaskManager.wait_for(self.download_url(app.icon_url), 5) # max 5 seconds per icon
                except Exception as e:
                    print(f"Download of {app.icon_url} got exception: {e}")
                    continue
            if app.icon_data:
                print("download_icons has icon_data, showing it...")
                image_icon_widget = None
                try:
                    image_icon_widget = app.image_icon_widget
                except Exception as e:
                    print(f"app.image_icon_widget got exception {e}")
                if image_icon_widget:
                    image_dsc = lv.image_dsc_t({
                        'data_size': len(app.icon_data),
                        'data': app.icon_data
                    })
                    image_icon_widget.set_src(image_dsc) # use some kind of new update_ui_if_foreground() ?
        print("Finished downloading icons.")

    def show_app_detail(self, app):
        intent = Intent(activity_class=AppDetail)
        intent.putExtra("app", app)
        intent.putExtra("appstore", self)
        self.startActivity(intent)

    async def download_url(self, url, outfile=None, total_size=None, progress_callback=None):
        print(f"Downloading {url}")
        #await TaskManager.sleep(4) # test slowness
        try:
            async with self.aiohttp_session.get(url) as response:
                if response.status < 200 or response.status >= 400:
                    return False if outfile else None

                # Always use chunked downloading
                chunk_size = 1024
                print("headers:") ; print(response.headers)
                if total_size is None:
                    total_size = response.headers.get('Content-Length') # some servers don't send this in the headers
                print(f"download_url {'writing to ' + outfile if outfile else 'reading'} {total_size} bytes in chunks of size {chunk_size}")

                fd = open(outfile, 'wb') if outfile else None
                chunks = [] if not outfile else None
                partial_size = 0

                if fd:
                    print("opened file...")

                while True:
                    tries_left = 3
                    chunk = None
                    while tries_left > 0:
                        try:
                            chunk = await TaskManager.wait_for(response.content.read(chunk_size), 10)
                            break
                        except Exception as e:
                            print(f"Waiting for response.content.read of next chunk got error: {e}")
                            tries_left -= 1

                    if tries_left == 0:
                        print("ERROR: failed to download chunk, even with retries!")
                        if fd:
                            fd.close()
                        return False if outfile else None

                    if chunk:
                        partial_size += len(chunk)
                        progress_pct = round((partial_size * 100) / int(total_size))
                        print(f"progress: {partial_size} / {total_size} bytes = {progress_pct}%")
                        if progress_callback:
                            await progress_callback(progress_pct)
                            #await TaskManager.sleep(1) # test slowness
                        if fd:
                            fd.write(chunk)
                        else:
                            chunks.append(chunk)
                    else:
                        print("chunk is None while there was no error so this was the last one")
                        print(f"Done downloading {url}")
                        if fd:
                            fd.close()
                            return True
                        else:
                            return b''.join(chunks)
        except Exception as e:
            print(f"download_url got exception {e}")
            return False if outfile else None

    @staticmethod
    def badgehub_app_to_mpos_app(bhapp):
        #print(f"Converting {bhapp} to MPOS app object...")
        name = bhapp.get("name")
        print(f"Got app name: {name}")
        publisher = None
        short_description = bhapp.get("description")
        long_description = None
        try:
            icon_url = bhapp.get("icon_map").get("64x64").get("url")
        except Exception as e:
            icon_url = None
            print("Could not find icon_map 64x64 url")
        download_url = None
        fullname = bhapp.get("slug")
        version = None
        try:
            category = bhapp.get("categories")[0]
        except Exception as e:
            category = None
            print("Could not parse category")
        activities = None
        return App(name, publisher, short_description, long_description, icon_url, download_url, fullname, version, category, activities)

    async def fetch_badgehub_app_details(self, app_obj):
        details_url = self.app_detail_url_badgehub + "/" + app_obj.fullname
        response = await self.download_url(details_url)
        if not response:
            print(f"Could not download app details from from\n{details_url}")
            return
        print(f"Got response text: {response[0:20]}")
        try:
            parsed = json.loads(response)
            print(f"parsed json: {parsed}")
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
                author = app_metadata.get("author")
                print("Using author as publisher because that's all the backend supports...")
                app_obj.publisher = author
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
            self.please_wait_label.set_text(err)
            return


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
        headercont.set_style_border_width(0, 0)
        headercont.set_style_pad_all(0, 0)
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
        detail_cont.set_style_border_width(0, 0)
        detail_cont.set_style_radius(0, 0)
        detail_cont.set_style_pad_all(0, 0)
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
        self.buttoncont.set_style_border_width(0, 0)
        self.buttoncont.set_style_radius(0, 0)
        self.buttoncont.set_style_pad_all(0, 0)
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
        if self.appstore.backend_api == self.appstore._BACKEND_API_BADGEHUB:
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
        await self.appstore.fetch_badgehub_app_details(self.app)
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
        self.progress_bar.remove_flag(lv.obj.FLAG.HIDDEN)
        self.progress_bar.set_value(21, True)
        await TaskManager.sleep(1) # seems silly but otherwise it goes so quickly that the user can't tell something happened and gets confused
        self.progress_bar.set_value(42, True)
        await TaskManager.sleep(1) # seems silly but otherwise it goes so quickly that the user can't tell something happened and gets confused
        PackageManager.uninstall_app(app_fullname)
        await TaskManager.sleep(1) # seems silly but otherwise it goes so quickly that the user can't tell something happened and gets confused
        self.progress_bar.set_value(100, False)
        self.progress_bar.add_flag(lv.obj.FLAG.HIDDEN)
        self.progress_bar.set_value(0, False)
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
        download_url_size = None
        if hasattr(app_obj, "download_url_size"):
            download_url_size = app_obj.download_url_size
        self.install_button.add_state(lv.STATE.DISABLED)
        self.install_label.set_text("Please wait...")
        self.progress_bar.remove_flag(lv.obj.FLAG.HIDDEN)
        self.progress_bar.set_value(5, True)
        await TaskManager.sleep(1) # seems silly but otherwise it goes so quickly that the user can't tell something happened and gets confused
        # Download the .mpk file to temporary location
        try:
            # Make sure there's no leftover file filling the storage
            os.remove(temp_zip_path)
        except Exception:
            pass
        try:
            os.mkdir("tmp")
        except Exception:
            pass
        temp_zip_path = "tmp/temp.mpk"
        print(f"Downloading .mpk file from: {zip_url} to {temp_zip_path}")
        result = await self.appstore.download_url(zip_url, outfile=temp_zip_path, total_size=download_url_size, progress_callback=self.pcb)
        if result is not True:
            print("Download failed...") # Would be good to show an error to the user if this failed...
        else:
            print("Downloaded .mpk file, size:", os.stat(temp_zip_path)[6], "bytes")
            # Install it:
            PackageManager.install_mpk(temp_zip_path, dest_folder) # 60 until 90 percent is the unzip but no progress there...
            self.progress_bar.set_value(90, True)
        # Make sure there's no leftover file filling the storage:
        try:
            os.remove(temp_zip_path)
        except Exception:
            pass
        # Success:
        await TaskManager.sleep(1) # seems silly but otherwise it goes so quickly that the user can't tell something happened and gets confused
        self.progress_bar.set_value(100, False)
        self.progress_bar.add_flag(lv.obj.FLAG.HIDDEN)
        self.progress_bar.set_value(0, False)
        self.set_install_label(app_fullname)
        self.install_button.remove_state(lv.STATE.DISABLED)
