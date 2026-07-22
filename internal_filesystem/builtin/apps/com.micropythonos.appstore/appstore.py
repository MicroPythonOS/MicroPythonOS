import json
import logging

import lvgl as lv

from mpos import Activity, App, AppManager, BuildInfo, Intent, DownloadManager, SettingsActivity, SharedPreferences, TaskManager

from app_detail import AppDetail
from blurhash import blurhash_to_image_dsc, generate_raw_app_icon

logger = logging.getLogger(__name__)


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

    _GENERATE_APP_ICON_BENCHMARK = 11 # ms
    _BLURHASH_APP_ICON_BENCHMARK = 76 # ms
    _WAIT_FACTOR_APP_ICON = 7 # 85% idle time
    _DOWNLOAD_ICON_INTERVAL = 3000 # ms between icon downloads

    _STAGE_RANK = {'raw': 1, 'blurhash': 2, 'download': 3}
    _DEFAULT_ICON_PIPELINE = 'blurhash'
    _DEFAULT_HIDE_WIP = True

    # Hardcoded list for now:
    backends = [
        ("BadgeHub.eu", _BACKEND_API_BADGEHUB, _BADGEHUB_PROD_BASE_URL, _BADGEHUB_LIST, _BADGEHUB_DETAILS),
        ("Apps.MicroPythonOS.com", _BACKEND_API_GITHUB, _GITHUB_PROD_BASE_URL, _GITHUB_LIST, None),
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
    category_dropdown = None
    update_all_button = None
    update_all_label = None
    _update_labels = {}

    def onCreate(self):
        self.prefs = SharedPreferences(self.appFullName)
        self._DEFAULT_BACKEND = AppStore.get_backend_pref_string(0)
        self._hide_wip = self.prefs.get_string("hide_wip", "true") == "true"
        self._refresh_in_progress = False
        self._data_loaded = False
        self._icon_queue = []
        self._raw_timer = None
        self._download_in_progress = False
        self._icon_pipeline = self.prefs.get_string("icon_pipeline", self._DEFAULT_ICON_PIPELINE)
        self.main_screen = lv.obj()
        self.main_screen.remove_flag(lv.obj.FLAG.SCROLLABLE)

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

        self.category_dropdown = lv.dropdown(self.top_bar)
        self.category_dropdown.set_size(lv.pct(75), self._TOP_BAR_HEIGHT - 6)
        self.category_dropdown.align_to(self.settings_button, lv.ALIGN.OUT_RIGHT_MID, 8, 0)
        self.category_dropdown.set_options("All Categories")
        self.category_dropdown.add_event_cb(self._category_changed, lv.EVENT.VALUE_CHANGED, None)
        self._category_options = ["All Categories"]
        self._selected_category = None

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
            from appstore_core import AppUpdateManager
            um = AppUpdateManager.get_instance()
            um.set_state_callback(self._on_update_state_change)
            um.suppress_notifications = True
            self._sync_update_banner(um.current_state, um.updatable_apps)
        except Exception as e:
            logger.warning("could not attach to AppUpdateManager: %s", e)

        if not self._data_loaded:
            self.refresh_list()
        elif self._data_loaded and hasattr(self, "apps_list") and self.apps_list:
            self._stop_all_timers()
            self._icon_queue.clear()
            for app in self.apps:
                if not app.image_icon_widget:
                    continue
                if app.icon_data:
                    self._set_icon_widget(app)
                elif self._restore_cached_icon(app, app.image_icon_widget):
                    pass
                else:
                    self._icon_queue.append((app, 'raw'))
            if self._icon_queue:
                self._raw_timer = lv.timer_create(self._process_icon_queue, self._GENERATE_APP_ICON_BENCHMARK*self._WAIT_FACTOR_APP_ICON, None)

    def onPause(self, screen):
        self._stop_all_timers()
        try:
            from appstore_core import AppUpdateManager
            AppUpdateManager.get_instance().clear_state_callback()
            AppUpdateManager.get_instance().suppress_notifications = False
        except Exception as e:
            logger.warning("could not detach from AppUpdateManager: %s", e)
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
            logger.warning("state change error: %s", e)

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
            logger.warning("update all click error: %s", e)
            return
        if not updatable:
            return
        TaskManager.create_task(self._run_update_all(updatable))

    async def _run_update_all(self, updatable_app_data_list):
        """Sequentially download-and-install every app that has an update."""
        self.update_all_button.add_state(lv.STATE.DISABLED)

        for app_data in updatable_app_data_list:
            fullname = app_data.get("fullname")
            download_url = app_data.get("download_url")
            if not fullname:
                if __debug__: logger.debug("skipping update for %s (missing fullname)", app_data)
                continue
            if not download_url:
                from appstore_core import fetch_badgehub_project_details
                base_url = AppStore._BADGEHUB_PROD_BASE_URL
                details_url = base_url + "/projects/" + fullname
                self.update_all_label.set_text(f"Checking {app_data.get('name', fullname)}...")
                details = await fetch_badgehub_project_details(details_url)
                download_url = details.get("download_url")
                if not download_url:
                    logger.warning("no download URL for %s", fullname)
                    app_data["download_url"] = None
                    continue
                app_data["download_url"] = download_url
                app_data["download_url_size"] = details.get("download_url_size")

            self.update_all_label.set_text(f"Updating {app_data.get('name', fullname)}...")
            try:
                await AppManager.download_and_install_package(download_url, fullname)
                if __debug__: logger.debug("updated %s", fullname)
            except Exception as e:
                logger.warning("update of %s failed: %s", fullname, e)
                if "Not enough free space" in str(e):
                    self.update_all_label.set_text(f"Not enough space for {app_data.get('name', fullname)}")
                else:
                    self.update_all_label.set_text(f"Update failed for {app_data.get('name', fullname)}")
                await TaskManager.sleep(1.5)

        # Refresh everything after all updates
        self.update_all_button.remove_state(lv.STATE.DISABLED)
        self.apps.clear()
        self.refresh_list()
        try:
            from appstore_core import AppUpdateManager
            AppManager.refresh_apps()
            AppUpdateManager.get_instance().check_for_updates_now()
        except Exception as e:
            logger.warning("post-update check error: %s", e)

    # ------------------------------------------------------------------
    # Existing AppStore methods (unchanged)
    # ------------------------------------------------------------------

    def refresh_list(self):
        if self._refresh_in_progress:
            if __debug__: logger.debug("refresh already in progress, skipping")
            return
        self._refresh_in_progress = True
        TaskManager.create_task(self._download_app_index_wrapper(self.get_backend_list_url_from_settings()))

    def settings_button_tap(self, event):
        intent = Intent(activity_class=SettingsActivity)
        intent.putExtra("prefs", self.prefs)
        intent.putExtra("settings", [
            {"title": "AppStore Backend",
             "key": "backend",
             "ui": "radiobuttons",
             "default_value": self._DEFAULT_BACKEND,
             "ui_options": [(backend[0], AppStore.get_backend_pref_string(index)) for index, backend in enumerate(AppStore.backends)],
             "changed_callback": self.backend_changed},
            {"title": "App List Icons",
             "key": "icon_pipeline",
             "ui": "radiobuttons",
             "default_value": self._DEFAULT_ICON_PIPELINE,
             "ui_options": [
                 ("None", "none"),
                 ("Blocky", "raw"),
                 ("Blocky, then blurhash", "blurhash"),
                 ("Blocky, blurhash, then download", "download"),
             ],
             "changed_callback": self._icon_pipeline_changed},
            {"title": "Hide 'Work in Progress' Apps",
             "key": "hide_wip",
             "ui": "radiobuttons",
             "default_value": "true",
             "ui_options": [
                 ("Hide", "true"),
                 ("Show", "false"),
             ],
             "changed_callback": self._hide_wip_changed},
        ])
        self.startActivity(intent)

    def backend_changed(self, new_value):
        if __debug__: logger.debug("backend changed to %s", new_value)
        self.refresh_list()

    def _hide_wip_changed(self, new_value):
        self._hide_wip = new_value == "true"
        self.refresh_list()

    def _category_changed(self, event):
        idx = self.category_dropdown.get_selected()
        self._selected_category = self._category_options[idx] if idx > 0 else None
        self.create_apps_list()

    def _update_category_dropdown(self):
        if self.category_dropdown is None:
            return
        cat_counts = {}
        total = 0
        for app in self.apps:
            if app.category:
                cat = AppStore._normalize_category(app.category)
                cat_counts[cat] = cat_counts.get(cat, 0) + 1
            total += 1
        sorted_cats = sorted(cat_counts.keys())
        if "Adult" in sorted_cats:
            sorted_cats.remove("Adult")
            sorted_cats.append("Adult")
        self._category_options = ["All Categories"] + sorted_cats
        display = ["All Categories (%d)" % total]
        for cat_name in sorted_cats:
            display.append("%s (%d)" % (cat_name, cat_counts[cat_name]))
        selected = self.category_dropdown.get_selected()
        self.category_dropdown.set_options("\n".join(display))
        if selected < len(self._category_options):
            self.category_dropdown.set_selected(selected)

    def _icon_pipeline_changed(self, new_value):
        self._icon_pipeline = new_value
        self._stop_all_timers()
        self._icon_queue.clear()
        self._download_in_progress = False
        if new_value != 'none' and hasattr(self, "apps_list") and self.apps_list:
            for app in self.apps:
                if not app.icon_data:
                    self._icon_queue.append((app, 'raw'))
            if self._icon_queue:
                self._raw_timer = lv.timer_create(self._process_icon_queue, self._GENERATE_APP_ICON_BENCHMARK*self._WAIT_FACTOR_APP_ICON, None)

    def _advance(self, app, from_stage):
        if self._icon_pipeline == 'none' or app.icon_data:
            return
        if from_stage == 'raw':
            if self._STAGE_RANK['blurhash'] <= self._STAGE_RANK[self._icon_pipeline] and app.blur_hash:
                self._icon_queue.append((app, 'blurhash'))
            elif self._STAGE_RANK['download'] <= self._STAGE_RANK[self._icon_pipeline] and app.icon_url:
                self._icon_queue.append((app, 'download'))
        elif from_stage == 'blurhash':
            if self._STAGE_RANK['download'] <= self._STAGE_RANK[self._icon_pipeline] and app.icon_url:
                self._icon_queue.append((app, 'download'))

    async def _download_app_index_wrapper(self, json_url):
        try:
            await self.download_app_index(json_url)
        finally:
            self._refresh_in_progress = False

    async def download_app_index(self, json_url):
        await TaskManager.sleep(0)

        # Phase 1: always show installed apps first (no network needed)
        self.apps.clear()
        self._builtin_fullnames = set()
        for installed_app in AppManager.get_app_list():
            if installed_app.installed_path and "builtin" in installed_app.installed_path:
                self._builtin_fullnames.add(installed_app.fullname)
                continue
            self.apps.append(installed_app)
        self._data_loaded = True
        self.create_apps_list()
        self._update_category_dropdown()

        # Phase 2: download store index and merge in new apps
        try:
            response = await DownloadManager.download_url(json_url)
        except Exception as e:
            if __debug__: logger.debug("store index unavailable (%s), showing installed apps only", e)
            return
        try:
            parsed = json.loads(response)
        except Exception as e:
            logger.warning("could not parse store index: %s", e)
            return

        backend_type = self.get_backend_type_from_settings()
        installed_by_fullname = {app.fullname: app for app in self.apps}
        new_apps = []
        for app_data in parsed:
            try:
                if backend_type == self._BACKEND_API_BADGEHUB:
                    if app_data.get("slug") in installed_by_fullname:
                        continue
                    if app_data.get("slug") in self._builtin_fullnames:
                        continue
                    if self._hide_wip and app_data.get("development_status") == "work_in_progress":
                        continue
                    new_apps.append(AppStore.badgehub_app_to_mpos_app(app_data))
                else:
                    fullname = app_data["fullname"]
                    if fullname in self._builtin_fullnames:
                        continue
                    if fullname in installed_by_fullname:
                        existing = installed_by_fullname[fullname]
                        existing.icon_url = app_data["icon_url"]
                        existing.download_url = app_data["download_url"]
                    else:
                        new_apps.append(App(
                            app_data["name"], app_data["publisher"],
                            app_data["short_description"], app_data["long_description"],
                            app_data["icon_url"], app_data["download_url"],
                            fullname, app_data["version"],
                            app_data["category"], app_data["activities"],
                        ))
            except Exception as e:
                logger.warning("could not process store app %s: %s", app_data.get("fullname", "?"), e)

        # Insert new apps at their sorted positions (avoids rebuilding entire list)
        for app in new_apps:
            idx = self._find_sorted_insert_index(app)
            self.apps.insert(idx, app)
            self._insert_app_list_item(app, idx)

        self._update_category_dropdown()

    def create_apps_list(self):
        if __debug__: logger.debug("create_apps_list")

        self._stop_all_timers()
        self._icon_queue.clear()
        self._download_in_progress = False

        if __debug__: logger.debug("hiding please wait label")
        self.please_wait_label.add_flag(lv.obj.FLAG.HIDDEN)

        # Determine top offset (update button may be visible)
        button_visible = not self.update_all_button.has_flag(lv.obj.FLAG.HIDDEN)
        list_top = self._TOP_BAR_HEIGHT + (self._UPDATE_BUTTON_HEIGHT + 8 if button_visible else 0)

        if hasattr(self, "apps_list") and self.apps_list:
            for app in self.apps:
                app.image_icon_widget = None
            self.apps_list.delete()
        self.apps_list = lv.list(self.main_screen)
        self._apply_default_styles(self.apps_list)
        self.apps_list.set_size(lv.pct(100), lv.pct(100))
        self.apps_list.align(lv.ALIGN.TOP_LEFT, 0, list_top)
        self._icon_widgets = {}
        self._update_labels = {}
        if __debug__: logger.debug("create_apps_list iterating")
        for app in self.apps:
            if self._selected_category:
                if not app.category or AppStore._normalize_category(app.category) != self._selected_category:
                    continue
            if __debug__: logger.debug(app)
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
            self._add_click_handler(icon_spacer, self.show_app_detail, app)
            app.image_icon_widget = icon_spacer
            if app.icon_data:
                self._set_icon_widget(app)
            elif self._restore_cached_icon(app, icon_spacer):
                pass
            elif self._icon_pipeline != 'none':
                self._icon_queue.append((app, 'raw'))
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
        if self._icon_queue:
            self._raw_timer = lv.timer_create(self._process_icon_queue, self._GENERATE_APP_ICON_BENCHMARK*self._WAIT_FACTOR_APP_ICON, None)
        try:
            from appstore_core import AppUpdateManager
            um = AppUpdateManager.get_instance()
            self._sync_update_banner(um.current_state, um.updatable_apps)
        except Exception:
            pass
        if __debug__: logger.debug("create_apps_list done")

    def _find_sorted_insert_index(self, app):
        """Find the index where app should be inserted to maintain alphabetical order."""
        app_key = app.name.lower()
        for i, existing in enumerate(self.apps):
            if app_key < existing.name.lower():
                return i
        return len(self.apps)

    def _insert_app_list_item(self, app, index):
        """Create LVGL widgets for an app and insert at the given index in the list."""
        if not hasattr(self, "apps_list") or not self.apps_list:
            return
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
        self._add_click_handler(icon_spacer, self.show_app_detail, app)
        app.image_icon_widget = icon_spacer
        if app.icon_data:
            self._set_icon_widget(app)
        elif self._restore_cached_icon(app, icon_spacer):
            pass
        elif self._icon_pipeline != 'none':
            self._icon_queue.append((app, 'raw'))
            if not self._raw_timer:
                self._raw_timer = lv.timer_create(self._process_icon_queue, self._GENERATE_APP_ICON_BENCHMARK*self._WAIT_FACTOR_APP_ICON, None)
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
        item.move_to_index(index)

    def _stop_all_timers(self):
        if self._raw_timer:
            self._raw_timer.delete()
            self._raw_timer = None

    def _process_icon_queue(self, timer):
        if not self._icon_queue:
            if self._download_in_progress:
                return
            self._raw_timer.delete()
            self._raw_timer = None
            return
        idx = self._find_best_app_index(self._icon_queue)
        app, stage = self._icon_queue.pop(idx)
        if stage == 'raw':
            self._set_raw_icon(app)
            self._advance(app, 'raw')
        elif stage == 'blurhash':
            if app.blur_hash and not app.icon_data:
                dsc, buf = blurhash_to_image_dsc(app.blur_hash, 16, 16)
                if dsc is not None:
                    app._icon_dsc = dsc
                    app._icon_buf = buf
                    widget = getattr(app, 'image_icon_widget', None)
                    if widget:
                        widget.set_src(dsc)
                        widget.set_scale(4 * 256)
            self._advance(app, 'blurhash')
        elif stage == 'download':
            if self._download_in_progress:
                self._icon_queue.append((app, 'download'))
                return
            if app.icon_data or not app.icon_url:
                return
            self._download_in_progress = True
            TaskManager.create_task(self._do_download(app))

    def _set_raw_icon(self, app):
        try:
            widget = app.image_icon_widget
        except Exception as e:
            if __debug__: logger.debug("no icon widget for %s: %s", app.fullname, e)
            return
        if not widget:
            return
        dsc, buf = generate_raw_app_icon(app.fullname, AppStore._ICON_SIZE)
        app._icon_dsc = dsc
        app._icon_buf = buf
        widget.set_src(dsc)
        widget.set_scale(256)

    async def _do_download(self, app):
        try:
            app.icon_data = await TaskManager.wait_for(DownloadManager.download_url(app.icon_url), 5)
        except Exception:
            pass
        self._download_in_progress = False
        if app.icon_data:
            try:
                self._set_icon_widget(app)
            except Exception:
                pass

    def _find_best_app_index(self, queue):
        try:
            scroll_y = self.apps_list.get_scroll_y()
            list_h = self.apps_list.get_height()
        except Exception:
            return 0
        best_i = 0
        best_dist = 999999
        for i, entry in enumerate(queue):
            app = entry[0]
            try:
                list_idx = self.apps.index(app)
            except ValueError:
                continue
            item_y = list_idx * self._ICON_SIZE
            if item_y + self._ICON_SIZE > scroll_y and item_y < scroll_y + list_h:
                return i
            if item_y + self._ICON_SIZE <= scroll_y:
                dist = scroll_y - (item_y + self._ICON_SIZE)
            else:
                dist = item_y - (scroll_y + list_h)
            if dist < best_dist:
                best_dist = dist
                best_i = i
        return best_i

    def _restore_cached_icon(self, app, widget):
        if hasattr(app, '_icon_dsc') and app._icon_dsc is not None:
            dsc = app._icon_dsc
            if dsc.header.w == self._ICON_SIZE:
                scale = 256
            else:
                scale = 4 * 256
            widget.set_src(dsc)
            widget.set_scale(scale)
            return True
        return False

    def _set_icon_widget(self, app):
        try:
            widget = app.image_icon_widget
        except Exception as e:
            if __debug__: logger.debug("no icon widget for %s: %s", app.fullname, e)
            return
        if not widget:
            return
        if app.icon_data:
            dsc = lv.image_dsc_t({
                'data_size': len(app.icon_data),
                'data': app.icon_data
            })
            scale = 256
            buf = None
        else:
            dsc, buf = blurhash_to_image_dsc(app.blur_hash, 16, 16)
            if dsc is None:
                dsc, buf = generate_raw_app_icon(app.fullname, AppStore._ICON_SIZE)
                scale = 256
            else:
                scale = 4 * 256
        app._icon_dsc = dsc
        app._icon_buf = buf
        widget.set_src(dsc)
        widget.set_scale(scale)

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
        if __debug__: logger.debug("got app name: %s", name)
        short_description = bhapp.get("description")
        fullname = bhapp.get("slug")
        icon_url = None
        try:
            icon_url = bhapp.get("icon_map", {}).get("64x64", {}).get("url")
        except Exception:
            if __debug__: logger.debug("could not find icon_map 64x64 url")
        blur_hash = bhapp.get("blur_hash")
        category = None
        try:
            category = bhapp.get("categories", [None])[0]
        except Exception:
            if __debug__: logger.debug("could not parse category")
        return App(name, None, short_description, None, icon_url, None, fullname, None, category, None, blur_hash=blur_hash)

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
    def _normalize_category(category):
        return category[0].upper() + category[1:].lower()

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
