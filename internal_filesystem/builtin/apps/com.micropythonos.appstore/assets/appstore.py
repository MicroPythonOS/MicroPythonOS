import json
import lvgl as lv

from mpos import Activity, App, BuildInfo, Intent, DownloadManager, SettingActivity, SharedPreferences, TaskManager

from app_detail import AppDetail


class AppStore(Activity):

    _GITHUB_PROD_BASE_URL = "https://apps.micropythonos.com"
    _GITHUB_LIST = "/app_index.json"

    _BADGEHUB_TEST_BASE_URL = "https://badgehub.p1m.nl/api/v3"
    _BADGEHUB_PROD_BASE_URL = "https://badgehub.eu/api/v3"
    _BADGEHUB_LIST = f"project-summaries?badge=mpos_api_{BuildInfo.version.api_level}"
    _BADGEHUB_DETAILS = "projects"

    _BACKEND_API_GITHUB = "github"
    _BACKEND_API_BADGEHUB = "badgehub"

    _ICON_SIZE = 64
    _TOP_BAR_HEIGHT = 44
    _TOP_BAR_BUTTON_SIZE = 34
    _UPDATE_BUTTON_HEIGHT = 40

    # Hardcoded list for now:
    backends = [
        ("Apps.MicroPythonOS.com on GitHub", _BACKEND_API_GITHUB, _GITHUB_PROD_BASE_URL, _GITHUB_LIST, None),
        ("BadgeHub.eu (beta)", _BACKEND_API_BADGEHUB, _BADGEHUB_PROD_BASE_URL, _BADGEHUB_LIST, _BADGEHUB_DETAILS),
        ("BadgeHub.p1m.nl Testing (unstable)", _BACKEND_API_BADGEHUB, _BADGEHUB_TEST_BASE_URL, _BADGEHUB_LIST, _BADGEHUB_DETAILS),
    ]

    apps = []
    can_check_network = True

    # Widgets:
    main_screen = None
    app_list = None
    update_button = None
    install_button = None
    install_label = None
    please_wait_label = None
    progress_bar = None
    settings_button = None
    top_bar = None
    title_label = None
    update_all_button = None
    update_all_label = None
    _update_labels = {}

    def onCreate(self):
        self.prefs = SharedPreferences(self.appFullName)
        self._migrate_backend_pref()
        self._DEFAULT_BACKEND = AppStore.get_backend_pref_string(0)
        self.main_screen = lv.obj()

        # ---- top bar ----
        self.top_bar = lv.obj(self.main_screen)
        self._apply_default_styles(self.top_bar)
        self.top_bar.set_size(lv.pct(100), self._TOP_BAR_HEIGHT)
        self.top_bar.align(lv.ALIGN.TOP_MID, 0, 0)
        self.top_bar.set_style_bg_opa(lv.OPA.COVER, lv.PART.MAIN)
        self.top_bar.set_style_border_width(1, lv.PART.MAIN)
        self.top_bar.set_style_border_side(lv.BORDER_SIDE.BOTTOM, lv.PART.MAIN)

        self.settings_button = lv.button(self.top_bar)
        self.settings_button.set_size(self._TOP_BAR_BUTTON_SIZE, self._TOP_BAR_BUTTON_SIZE)
        self.settings_button.align(lv.ALIGN.LEFT_MID, 5, 0)
        self.settings_button.add_event_cb(self.settings_button_tap, lv.EVENT.CLICKED, None)
        settings_label = lv.label(self.settings_button)
        settings_label.set_text(lv.SYMBOL.SETTINGS)
        settings_label.set_style_text_font(lv.font_montserrat_24, lv.PART.MAIN)
        settings_label.center()

        self.title_label = lv.label(self.top_bar)
        self.title_label.set_text("App Store")
        self.title_label.set_style_text_font(lv.font_montserrat_16, lv.PART.MAIN)
        self.title_label.center()

        # ---- "Update N App(s)" button (hidden until updates are found) ----
        self.update_all_button = lv.button(self.main_screen)
        self.update_all_button.set_size(lv.pct(90), self._UPDATE_BUTTON_HEIGHT)
        self.update_all_button.align(lv.ALIGN.TOP_MID, 0, self._TOP_BAR_HEIGHT + 4)
        self.update_all_button.add_event_cb(self._update_all_click, lv.EVENT.CLICKED, None)
        self.update_all_button.add_flag(lv.obj.FLAG.HIDDEN)
        self.update_all_label = lv.label(self.update_all_button)
        self.update_all_label.set_text("")
        self.update_all_label.center()

        # ---- please-wait / error label ----
        self.please_wait_label = lv.label(self.main_screen)
        self.please_wait_label.set_text("Downloading app index...")
        self.please_wait_label.align(lv.ALIGN.CENTER, 0, self._TOP_BAR_HEIGHT // 2)
        self.setContentView(self.main_screen)

    def onResume(self, screen):
        super().onResume(screen)

        # Attach to AppUpdateManager so the banner refreshes live
        try:
            from appstore_core import AppUpdateManager, AppUpdateState
            um = AppUpdateManager.get_instance()
            um.set_state_callback(self._on_update_state_change)
            um.suppress_notifications = True
            self._sync_update_banner(um.current_state, um.updatable_apps)
            um.check_for_updates_now(self.get_backend_list_url_from_settings())
        except Exception as e:
            print(f"AppStore: could not attach to AppUpdateManager: {e}")

        if not len(self.apps):
            self.refresh_list()

    def onPause(self, screen):
        try:
            from appstore_core import AppUpdateManager
            AppUpdateManager.get_instance().clear_state_callback()
            AppUpdateManager.get_instance().suppress_notifications = False
        except Exception as e:
            print(f"AppStore: could not detach from AppUpdateManager: {e}")
        super().onPause(screen)

    # ------------------------------------------------------------------
    # Update-banner helpers
    # ------------------------------------------------------------------

    def _on_update_state_change(self, state):
        if not self.has_foreground():
            return
        try:
            from appstore_core import AppUpdateManager
            um = AppUpdateManager.get_instance()
            self._sync_update_banner(state, um.updatable_apps)
        except Exception as e:
            print(f"AppStore: _on_update_state_change error: {e}")

    def _sync_update_banner(self, state, updatable_apps):
        from appstore_core import AppUpdateState
        if state == AppUpdateState.UPDATES_AVAILABLE and updatable_apps:
            n = len(updatable_apps)
            self.update_all_label.set_text(f"Update {n} App{'s' if n != 1 else ''}")
            self.update_all_button.remove_flag(lv.obj.FLAG.HIDDEN)
            # Push the list below the button
            if hasattr(self, "apps_list") and self.apps_list:
                self.apps_list.align(lv.ALIGN.TOP_LEFT, 0, self._TOP_BAR_HEIGHT + self._UPDATE_BUTTON_HEIGHT + 8)
        else:
            self.update_all_button.add_flag(lv.obj.FLAG.HIDDEN)
            # Move the list back up
            if hasattr(self, "apps_list") and self.apps_list:
                self.apps_list.align(lv.ALIGN.TOP_LEFT, 0, self._TOP_BAR_HEIGHT)

        # Show/hide per-app "Update available" labels
        updatable_set = {a.get("fullname") for a in (updatable_apps or [])}
        for fullname, label in self._update_labels.items():
            if fullname in updatable_set:
                label.remove_flag(lv.obj.FLAG.HIDDEN)
            else:
                label.add_flag(lv.obj.FLAG.HIDDEN)

    def _update_all_click(self, event):
        try:
            from appstore_core import AppUpdateManager
            updatable = AppUpdateManager.get_instance().updatable_apps
        except Exception as e:
            print(f"AppStore: _update_all_click error: {e}")
            return
        if not updatable:
            return
        TaskManager.create_task(self._run_update_all(updatable))

    async def _run_update_all(self, updatable_app_data_list):
        """Sequentially download-and-install every app that has an update."""
        from mpos import AppManager
        self.update_all_button.add_state(lv.STATE.DISABLED)

        for app_data in updatable_app_data_list:
            fullname = app_data.get("fullname")
            download_url = app_data.get("download_url")
            if not fullname or not download_url:
                print(f"AppStore: skipping update for {app_data} (missing fullname/download_url)")
                continue

            self.update_all_label.set_text(f"Updating {app_data.get('name', fullname)}...")
            try:
                await AppManager.download_and_install_package(download_url, fullname)
                print(f"AppStore: updated {fullname}")
            except Exception as e:
                print(f"AppStore: update of {fullname} failed: {e}")

        # Refresh everything after all updates
        self.update_all_button.remove_state(lv.STATE.DISABLED)
        self.apps.clear()
        self.refresh_list()
        try:
            from appstore_core import AppUpdateManager
            AppUpdateManager.get_instance().check_for_updates_now()
        except Exception as e:
            print(f"AppStore: post-update check error: {e}")

    # ------------------------------------------------------------------
    # Existing AppStore methods (unchanged)
    # ------------------------------------------------------------------

    def refresh_list(self):
        try:
            import network
            if not network.WLAN(network.STA_IF).isconnected():
                self.please_wait_label.remove_flag(lv.obj.FLAG.HIDDEN)
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
                                    "default_value": self._DEFAULT_BACKEND,
                                    "ui_options":  [(backend[0], AppStore.get_backend_pref_string(index)) for index, backend in enumerate(AppStore.backends)],
                                    "changed_callback": self.backend_changed})
        self.startActivity(intent)

    def backend_changed(self, new_value):
        print(f"backend changed to {new_value}, refreshing...")
        self.refresh_list()

    def _migrate_backend_pref(self):
        old_pref = "badgehub,https://badgehub.eu/api/v3/project-summaries?badge=fri3d_2024,https://badgehub.eu/api/v3/projects"
        new_pref = f"badgehub,https://badgehub.eu/api/v3/project-summaries?badge=mpos_api_{BuildInfo.version.api_level},https://badgehub.eu/api/v3/projects"
        current_pref = self.prefs.get_string("backend")
        if current_pref == old_pref:
            print(f"Migrating AppStore backend preference to mpos_api_{BuildInfo.version.api_level}")
            self.prefs.edit().put_string("backend", new_pref).commit()

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
        await TaskManager.sleep(0.1)
        print("Remove duplicates based on app.name")
        seen = set()
        self.apps = [app for app in self.apps if not (app.fullname in seen or seen.add(app.fullname))]
        print("Sort apps by app.name")
        self.apps.sort(key=lambda x: x.name.lower())
        print("Creating apps list...")
        self.create_apps_list()
        await TaskManager.sleep(0.1)
        print("awaiting self.download_icons()")
        await self.download_icons()

    def create_apps_list(self):
        print("create_apps_list")

        print("Hiding please wait label...")
        self.please_wait_label.add_flag(lv.obj.FLAG.HIDDEN)

        # Determine top offset (update button may be visible)
        button_visible = not self.update_all_button.has_flag(lv.obj.FLAG.HIDDEN)
        list_top = self._TOP_BAR_HEIGHT + (self._UPDATE_BUTTON_HEIGHT + 8 if button_visible else 0)

        self.apps_list = lv.list(self.main_screen)
        self._apply_default_styles(self.apps_list)
        self.apps_list.set_size(lv.pct(100), lv.pct(100))
        self.apps_list.align(lv.ALIGN.TOP_LEFT, 0, list_top)
        self._icon_widgets = {}
        self._update_labels = {}
        print("create_apps_list iterating")
        for app in self.apps:
            print(app)
            item = self.apps_list.add_button(None, "")
            item.set_style_pad_all(0, lv.PART.MAIN)
            item.set_size(lv.pct(100), lv.SIZE_CONTENT)
            self._add_click_handler(item, self.show_app_detail, app)
            cont = lv.obj(item)
            cont.set_style_pad_all(0, lv.PART.MAIN)
            cont.set_flex_flow(lv.FLEX_FLOW.ROW)
            cont.set_size(lv.pct(100), lv.SIZE_CONTENT)
            cont.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
            self._apply_default_styles(cont)
            self._add_click_handler(cont, self.show_app_detail, app)
            icon_spacer = lv.image(cont)
            icon_spacer.set_size(self._ICON_SIZE, self._ICON_SIZE)
            icon_spacer.set_src(lv.SYMBOL.REFRESH)
            self._add_click_handler(icon_spacer, self.show_app_detail, app)
            app.image_icon_widget = icon_spacer
            label_cont = lv.obj(cont)
            self._apply_default_styles(label_cont)
            label_cont.set_flex_flow(lv.FLEX_FLOW.COLUMN)
            label_cont.set_style_pad_ver(10, lv.PART.MAIN)
            label_cont.set_size(lv.pct(75), lv.SIZE_CONTENT)
            self._add_click_handler(label_cont, self.show_app_detail, app)
            name_label = lv.label(label_cont)
            name_label.set_text(app.name)
            name_label.set_style_text_font(lv.font_montserrat_16, lv.PART.MAIN)
            self._add_click_handler(name_label, self.show_app_detail, app)
            desc_label = lv.label(label_cont)
            desc_label.set_text(app.short_description)
            desc_label.set_style_text_font(lv.font_montserrat_12, lv.PART.MAIN)
            self._add_click_handler(desc_label, self.show_app_detail, app)
            update_label = lv.label(label_cont)
            update_label.set_text("Update available")
            update_label.set_style_text_font(lv.font_montserrat_12, lv.PART.MAIN)
            update_label.set_style_text_color(lv.palette_main(lv.PALETTE.GREEN), lv.PART.MAIN)
            update_label.add_flag(lv.obj.FLAG.HIDDEN)
            self._update_labels[app.fullname] = update_label
        print("create_apps_list done")

    async def download_icons(self):
        print("Downloading icons...")
        for app in self.apps:
            if not self.has_foreground():
                print(f"App is stopping, aborting icon downloads.")
                break
            if not app.icon_data:
                try:
                    app.icon_data = await TaskManager.wait_for(DownloadManager.download_url(app.icon_url), 5)
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
                    image_icon_widget.set_src(image_dsc)
        print("Finished downloading icons.")

    def show_app_detail(self, app):
        intent = Intent(activity_class=AppDetail)
        intent.putExtra("app", app)
        intent.putExtra("appstore", self)
        self.startActivity(intent)

    def _get_backend_config(self):
        """Get backend configuration tuple (type, list_url, details_url)"""
        pref_string = self.prefs.get_string("backend", self._DEFAULT_BACKEND)
        return AppStore.backend_pref_string_to_backend(pref_string)

    def get_backend_type_from_settings(self):
        return self._get_backend_config()[0]

    def get_backend_list_url_from_settings(self):
        return self._get_backend_config()[1]

    def get_backend_details_url_from_settings(self):
        return self._get_backend_config()[2]

    @staticmethod
    def badgehub_app_to_mpos_app(bhapp):
        name = bhapp.get("name")
        print(f"Got app name: {name}")
        short_description = bhapp.get("description")
        fullname = bhapp.get("slug")
        icon_url = None
        try:
            icon_url = bhapp.get("icon_map", {}).get("64x64", {}).get("url")
        except Exception:
            print("Could not find icon_map 64x64 url")
        category = None
        try:
            category = bhapp.get("categories", [None])[0]
        except Exception:
            print("Could not parse category")
        return App(name, None, short_description, None, icon_url, None, fullname, None, category, None)

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

    @staticmethod
    def _apply_default_styles(widget, border=0, radius=0, pad=0):
        """Apply common default styles to reduce repetition"""
        widget.set_style_border_width(border, lv.PART.MAIN)
        widget.set_style_radius(radius, lv.PART.MAIN)
        widget.set_style_pad_all(pad, lv.PART.MAIN)

    @staticmethod
    def _add_click_handler(widget, callback, app):
        """Register click handler to avoid repetition"""
        widget.add_event_cb(lambda e, a=app: callback(a), lv.EVENT.CLICKED, None)
