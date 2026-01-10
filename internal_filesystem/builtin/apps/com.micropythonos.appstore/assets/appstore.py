import os
import json
import lvgl as lv

from mpos import Activity, App, Intent, DownloadManager, SettingActivity, SharedPreferences, TaskManager

from app_detail import AppDetail

class AppStore(Activity):

    PACKAGE = "com.micropythonos.appstore"

    _GITHUB_PROD_BASE_URL = "https://apps.micropythonos.com"
    _GITHUB_LIST = "/app_index.json"

    _BADGEHUB_TEST_BASE_URL = "https://badgehub.p1m.nl/api/v3"
    _BADGEHUB_PROD_BASE_URL = "https://badge.why2025.org/api/v3"
    _BADGEHUB_LIST = "project-summaries?badge=fri3d_2024"
    _BADGEHUB_DETAILS = "projects"

    _BACKEND_API_GITHUB = "github"
    _BACKEND_API_BADGEHUB = "badgehub"

    _ICON_SIZE = 64

    # Hardcoded list for now:
    backends = [
        ("MPOS GitHub", _BACKEND_API_GITHUB, _GITHUB_PROD_BASE_URL, _GITHUB_LIST, None),
        ("BadgeHub Test", _BACKEND_API_BADGEHUB, _BADGEHUB_TEST_BASE_URL, _BADGEHUB_LIST, _BADGEHUB_DETAILS),
        ("BadgeHub Prod", _BACKEND_API_BADGEHUB, _BADGEHUB_PROD_BASE_URL, _BADGEHUB_LIST, _BADGEHUB_DETAILS)
    ]

    _DEFAULT_BACKEND = _BACKEND_API_GITHUB + "," + _GITHUB_PROD_BASE_URL + "/" + _GITHUB_LIST

    apps = []
    prefs = None
    can_check_network = True

    # Widgets:
    main_screen = None
    update_button = None
    install_button = None
    install_label = None
    please_wait_label = None
    progress_bar = None
    settings_button = None

    def onCreate(self):
        self.main_screen = lv.obj()
        self.please_wait_label = lv.label(self.main_screen)
        self.please_wait_label.set_text("Downloading app index...")
        self.please_wait_label.center()
        self.settings_button = lv.button(self.main_screen)
        settings_margin = 15
        settings_size = self._ICON_SIZE - settings_margin
        self.settings_button.set_size(settings_size, settings_size)
        self.settings_button.align(lv.ALIGN.TOP_RIGHT, -settings_margin, 10)
        self.settings_button.add_event_cb(self.settings_button_tap,lv.EVENT.CLICKED,None)
        settings_label = lv.label(self.settings_button)
        settings_label.set_text(lv.SYMBOL.SETTINGS)
        settings_label.set_style_text_font(lv.font_montserrat_24, 0)
        settings_label.center()
        self.setContentView(self.main_screen)

    def onResume(self, screen):
        super().onResume(screen)
        if not self.prefs:
            self.prefs = SharedPreferences(self.PACKAGE)
        if not len(self.apps):
            self.refresh_list()

    def refresh_list(self):
        try:
            import network
            if not network.WLAN(network.STA_IF).isconnected():
                self.please_wait_label.remove_flag(lv.obj.FLAG.HIDDEN) # make sure it's visible
                self.please_wait_label.set_text("Error: WiFi is not connected.")
        except Exception as e:
            print("Warning: can't check network state, assuming we're online...")
        TaskManager.create_task(self.download_app_index(self.get_backend_list_url_from_settings()))

    def settings_button_tap(self, event):
        intent = Intent(activity_class=SettingActivity)
        intent.putExtra("prefs", self.prefs)
        intent.putExtra("setting", {"title": "AppStore Backend",
                                    "key": "backend",
                                    "ui": "radiobuttons",
                                    "ui_options":  [(backend[0], AppStore.get_backend_pref_string(index)) for index, backend in enumerate(AppStore.backends)],
                                    "changed_callback": self.backend_changed})
        self.startActivity(intent)

    def backend_changed(self, new_value):
        print(f"backend changed to {new_value}, refreshing...")
        self.refresh_list()

    async def download_app_index(self, json_url):
        try:
            response = await DownloadManager.download_url(json_url)
        except Exception as e:
            print(f"Failed to download app index: {e}")
            if DownloadManager.is_network_error(e):
                self.please_wait_label.set_text(f"Network error - check your WiFi connection\nand try again.")
            else:
                self.please_wait_label.set_text(f"Could not download app index from\n{json_url}\nError: {e}")
            return
        print(f"Got response text: {response[0:20]}")
        try:
            parsed = json.loads(response)
            #print(f"parsed json: {parsed}")
            self.apps.clear()
            for app in parsed:
                try:
                    backend_type = self.get_backend_type_from_settings()
                    if backend_type == self._BACKEND_API_BADGEHUB:
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
            item = apps_list.add_button(None, "")
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
            icon_spacer.set_size(self._ICON_SIZE, self._ICON_SIZE)
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
        print("create_apps_list done")
        # Settings button needs to float in foreground:
        self.settings_button.move_to_index(-1)

    async def download_icons(self):
        print("Downloading icons...")
        for app in self.apps:
            if not self.has_foreground():
                print(f"App is stopping, aborting icon downloads.") # maybe this can continue? but then update_ui_if_foreground is needed
                break
            if not app.icon_data:
                try:
                    app.icon_data = await TaskManager.wait_for(DownloadManager.download_url(app.icon_url), 5) # max 5 seconds per icon
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
        details_url = self.get_backend_details_url_from_settings()
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
            self.please_wait_label.set_text(err)
            return

    def get_backend_type_from_settings(self):
        return AppStore.backend_pref_string_to_backend(self.prefs.get_string("backend", self._DEFAULT_BACKEND))[0]

    def get_backend_list_url_from_settings(self):
        return AppStore.backend_pref_string_to_backend(self.prefs.get_string("backend", self._DEFAULT_BACKEND))[1]

    def get_backend_details_url_from_settings():
        return AppStore.backend_pref_string_to_backend(self.prefs.get_string("backend", self._DEFAULT_BACKEND))[2]

    @staticmethod
    def get_backend_pref_string(index):
        backend_info = AppStore.backends[index]
        if backend_info:
            api = backend_info[1]
            base_url = backend_info[2]
            list_suffix  = backend_info[3]
            details_suffix = backend_info[4]
            toreturn = api + "," + base_url + "/" + list_suffix
            if api == AppStore._BACKEND_API_BADGEHUB:
                toreturn += "," + base_url + "/" + details_suffix
            return toreturn

    @staticmethod
    def backend_pref_string_to_backend(string):
        return string.split(",")
