import json
import logging

import lvgl as lv

from mpos import Activity, App, AppManager, BuildInfo, Intent, DownloadManager, SettingsActivity, SharedPreferences, TaskManager
from mpos.ui import QR_SYMBOL, STAR_SYMBOL
from mpos.content import deeplink

from app_detail import AppDetail
from blurhash import blurhash_to_image_dsc, generate_raw_app_icon

logger = logging.getLogger(__name__)


class AppStore(Activity):

    _BADGEHUB_BASE_URL = "https://badgehub.eu/api/v3"
    _BADGEHUB_LIST_URL = f"https://badgehub.eu/api/v3/project-summaries?badge=mpos_api_{BuildInfo.version.api_level}"
    _BADGEHUB_DETAILS_URL = "https://badgehub.eu/api/v3/projects"

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
    _SPECIAL_CATEGORIES = {"All", "Work In Progress", "Installed", "Updates"}

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
        self._hide_wip = self.prefs.get_string("hide_wip", "true") == "true"
        self._wip_apps = []
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

        self.scanqr_button = lv.button(self.top_bar)
        self.scanqr_button.set_size(self._TOP_BAR_BUTTON_SIZE, self._TOP_BAR_BUTTON_SIZE)
        self.scanqr_button.align(lv.ALIGN.RIGHT_MID, -5, 0)
        self.scanqr_button.add_event_cb(self.scanqr_button_tap, lv.EVENT.CLICKED, None)
        scanqr_label = lv.label(self.scanqr_button)
        scanqr_label.set_text(QR_SYMBOL)
        scanqr_label.set_style_text_font(lv.font_montserrat_24, lv.PART.MAIN)
        scanqr_label.center()

        self.category_dropdown = lv.dropdown(self.top_bar)
        self.category_dropdown.set_size(lv.pct(55), self._TOP_BAR_HEIGHT - 6)
        self.category_dropdown.align_to(self.settings_button, lv.ALIGN.OUT_RIGHT_MID, 8, 0)
        self.category_dropdown.set_options("All")
        self.category_dropdown.add_event_cb(self._category_changed, lv.EVENT.VALUE_CHANGED, None)
        self._category_options = ["All"]
        self._selected_category = self.getIntent().extras.get("category")
        self._pending_deeplink = self.getIntent().extras.get("deeplink_fullname")
        self._default_to_installed = self._selected_category is None and self._pending_deeplink is None

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
            if getattr(self, '_selected_category', None) == "Updates" and getattr(self, '_data_loaded', False):
                self.create_apps_list()
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
                list_top = self._TOP_BAR_HEIGHT + self._UPDATE_BUTTON_HEIGHT + 8
                self.apps_list.align(lv.ALIGN.TOP_LEFT, 0, list_top)
                self.apps_list.set_height(lv.screen_active().get_height() - list_top)
        else:
            self.update_all_button.add_flag(lv.obj.FLAG.HIDDEN)
            # Move the list back up
            if hasattr(self, "apps_list") and self.apps_list:
                list_top = self._TOP_BAR_HEIGHT
                self.apps_list.align(lv.ALIGN.TOP_LEFT, 0, list_top)
                self.apps_list.set_height(lv.screen_active().get_height() - list_top)

        # Show/hide per-app "Update available" labels
        updatable_set = {a.get("fullname") for a in (updatable_apps or [])}
        for fullname, label in self._update_labels.items():
            if fullname in updatable_set:
                label.remove_flag(lv.obj.FLAG.HIDDEN)
            else:
                label.add_flag(lv.obj.FLAG.HIDDEN)
        if getattr(self, '_data_loaded', False):
            self._update_category_dropdown()

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
                details_url = AppStore._BADGEHUB_DETAILS_URL + "/" + fullname
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
        TaskManager.create_task(self._download_app_index_wrapper(AppStore._BADGEHUB_LIST_URL))

    def settings_button_tap(self, event):
        intent = Intent(activity_class=SettingsActivity)
        intent.putExtra("prefs", self.prefs)
        intent.putExtra("settings", [
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
            {"title": "Update notifications",
             "key": "update_notifications",
             "ui": "radiobuttons",
             "default_value": "true",
             "ui_options": [
                 ("On", "true"),
                 ("Off", "false"),
             ],
             "changed_callback": self._update_notifications_changed},
        ])
        self.startActivity(intent)

    def _hide_wip_changed(self, new_value):
        self._hide_wip = new_value == "true"
        self.refresh_list()

    def _update_notifications_changed(self, new_value):
        if new_value != "true":
            try:
                from appstore_core import AppUpdateManager
                AppUpdateManager.get_instance().clear_updates_notification()
            except Exception as e:
                logger.warning("could not clear update notification: %s", e)

    def _category_changed(self, event):
        if getattr(self, "_rebuilding_dropdown", False):
            return
        idx = self.category_dropdown.get_selected()
        cat = self._category_options[idx]
        self._selected_category = None if cat == "All" else cat
        self.create_apps_list()

    def _update_category_dropdown(self):
        if self.category_dropdown is None:
            return
        cat_counts = {}
        total = 0
        for app in self.apps:
            for cat in app.categories:
                cat_counts[cat] = cat_counts.get(cat, 0) + 1
            total += 1
        sorted_cats = [c for c in sorted(cat_counts.keys()) if c != "Adult" and c not in AppStore._SPECIAL_CATEGORIES]
        top_cats = ["Installed", "Updates"]
        if self._wip_apps:
            top_cats.append("Work In Progress")
        top_cats.append("All")
        self._category_options = top_cats + sorted_cats
        if "Adult" in cat_counts:
            self._category_options.append("Adult")
        display = []
        for cat_name in top_cats:
            if cat_name == "Installed":
                n_installed = sum(1 for app in self.apps if app.installed_path is not None)
                display.append("%s (%d)" % (cat_name, n_installed))
            elif cat_name == "Updates":
                try:
                    from appstore_core import AppUpdateManager
                    n_updates = len(AppUpdateManager.get_instance().updatable_apps or [])
                except Exception:
                    n_updates = 0
                display.append("%s (%d)" % (cat_name, n_updates))
            elif cat_name == "Work In Progress":
                display.append("%s (%d)" % (cat_name, len(self._wip_apps)))
            elif cat_name == "All":
                display.append("%s (%d)" % (cat_name, total))
        for cat_name in sorted_cats:
            display.append("%s (%d)" % (cat_name, cat_counts[cat_name]))
        if "Adult" in cat_counts:
            display.append("Adult (%d)" % cat_counts["Adult"])
        self._rebuilding_dropdown = True
        self.category_dropdown.set_options("\n".join(display))
        selected_cat = getattr(self, "_selected_category", None)
        if selected_cat and selected_cat in self._category_options:
            self.category_dropdown.set_selected(self._category_options.index(selected_cat))
        elif selected_cat is None and "All" in self._category_options:
            self.category_dropdown.set_selected(self._category_options.index("All"))
        else:
            selected = self.category_dropdown.get_selected()
            if selected < len(self._category_options):
                self.category_dropdown.set_selected(selected)
        self._rebuilding_dropdown = False

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
        self._wip_apps.clear()
        self._builtin_fullnames = set()
        for installed_app in AppManager.get_app_list():
            if installed_app.installed_path and "builtin" in installed_app.installed_path:
                self._builtin_fullnames.add(installed_app.fullname)
                continue
            self.apps.append(installed_app)
        if getattr(self, "_default_to_installed", False):
            self._default_to_installed = False
            n_installed = sum(1 for app in self.apps if app.installed_path is not None)
            if n_installed > 0:
                self._selected_category = "Installed"
        self._data_loaded = True
        self.create_apps_list()
        self._update_category_dropdown()

        # A deep link to an app that is already known locally (e.g. installed)
        # can open its detail screen right now, without waiting for the index
        # download. Unknown apps keep waiting for Phase 2.
        self._try_early_deeplink()

        # Phase 2: download store index and merge in new apps
        try:
            response = await DownloadManager.download_url(json_url)
        except Exception as e:
            if __debug__: logger.debug("store index unavailable (%s), showing installed apps only", e)
            self._resolve_pending_deeplink(index_available=False)
            return
        try:
            parsed = json.loads(response)
        except Exception as e:
            logger.warning("could not parse store index: %s", e)
            self._resolve_pending_deeplink(index_available=False)
            return

        installed_by_fullname = {app.fullname: app for app in self.apps}
        new_apps = []
        for app_data in parsed:
            try:
                fullname = app_data.get("slug")
                if not fullname:
                    continue
                if fullname in installed_by_fullname:
                    existing = installed_by_fullname[fullname]
                    store_version = app_data.get("version")
                    if store_version:
                        existing._remote_version = store_version
                    ratings = app_data.get("ratings") or {}
                    existing.rating_average = ratings.get("average")
                    existing.rating_count = ratings.get("count", 0)
                    if app_data.get("development_status") == "work_in_progress":
                        self._wip_apps.append(existing)
                    continue
                if fullname in self._builtin_fullnames:
                    continue
                app = AppStore.badgehub_app_to_mpos_app(app_data)
                if app_data.get("development_status") == "work_in_progress":
                    self._wip_apps.append(app)
                    if self._hide_wip:
                        continue
                new_apps.append(app)
            except Exception as e:
                logger.warning("could not process store app %s: %s", app_data.get("slug", "?"), e)

        # Insert new apps at their sorted positions (avoids rebuilding entire list)
        # If the activity is no longer in the foreground (e.g. test called
        # back_screen() while the download was in flight), the list widgets may
        # have been deleted — inserting into a stale list can segfault LVGL.
        if not self.has_foreground():
            self._resolve_pending_deeplink()
            return
        for app in new_apps:
            idx = self._find_sorted_insert_index(app)
            self.apps.insert(idx, app)
            self._insert_app_list_item(app, idx)

        # ponytail: rebuild whole list so installed apps get their rating labels
        # (ratings were patched after Phase 1 already painted the list)
        if self.has_foreground():
            self.create_apps_list()
            self._update_category_dropdown()
        self._resolve_pending_deeplink()

    def create_apps_list(self):
        if __debug__: logger.debug("create_apps_list")
        # Guard against being called after the activity was removed (e.g. async
        # download completing after back_screen). Acting on deleted LVGL objects
        # can hard-fault the device.
        if not getattr(self, "main_screen", None) or not self.has_foreground():
            if __debug__: logger.debug("create_apps_list skipped: not in foreground")
            return

        self._stop_all_timers()
        self._icon_queue.clear()
        self._download_in_progress = False

        if __debug__: logger.debug("hiding please wait label")
        try:
            self.please_wait_label.add_flag(lv.obj.FLAG.HIDDEN)
        except Exception:
            return

        # Determine top offset (update button may be visible)
        button_visible = not self.update_all_button.has_flag(lv.obj.FLAG.HIDDEN)
        list_top = self._TOP_BAR_HEIGHT + (self._UPDATE_BUTTON_HEIGHT + 8 if button_visible else 0)
        list_h = lv.screen_active().get_height() - list_top

        if hasattr(self, "apps_list") and self.apps_list:
            for app in self.apps:
                app.image_icon_widget = None
            self.apps_list.delete()
        self.apps_list = lv.list(self.main_screen)
        self._apply_default_styles(self.apps_list)
        self.apps_list.set_size(lv.pct(100), list_h)
        self.apps_list.align(lv.ALIGN.TOP_LEFT, 0, list_top)
        self._icon_widgets = {}
        self._update_labels = {}
        if __debug__: logger.debug("create_apps_list iterating")
        sel_cat = getattr(self, "_selected_category", None)
        apps_to_show = self._wip_apps if sel_cat == "Work In Progress" else self.apps
        installed_set = set()
        if sel_cat == "Installed":
            installed_set = {app.fullname for app in self.apps if app.installed_path is not None}
        if sel_cat == "Updates":
            try:
                from appstore_core import AppUpdateManager
                updatable_set = {a.get("fullname") for a in (AppUpdateManager.get_instance().updatable_apps or [])}
            except Exception:
                updatable_set = set()
        for app in apps_to_show:
            if sel_cat:
                if sel_cat == "Work In Progress":
                    pass
                elif sel_cat == "Installed":
                    if app.fullname not in installed_set:
                        continue
                elif sel_cat == "Updates":
                    if app.fullname not in updatable_set:
                        continue
                elif not app.categories or sel_cat not in app.categories:
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
            name_row = lv.obj(label_cont)
            self._apply_default_styles(name_row)
            name_row.set_flex_flow(lv.FLEX_FLOW.ROW)
            name_row.set_size(lv.pct(100), lv.SIZE_CONTENT)
            self._add_click_handler(name_row, self.show_app_detail, app)
            name_label = lv.label(name_row)
            name_label.set_text(app.name)
            name_label.set_style_text_font(lv.font_montserrat_16, lv.PART.MAIN)
            name_label.set_flex_grow(1)
            self._add_click_handler(name_label, self.show_app_detail, app)
            rating_avg = getattr(app, "rating_average", None)
            if rating_avg is not None and rating_avg > 0:
                rating_label = lv.label(name_row)
                rating_label.set_text("%s %.1f" % (STAR_SYMBOL, rating_avg))
                rating_label.set_style_text_font(lv.font_montserrat_12, lv.PART.MAIN)
                rating_label.set_size(lv.SIZE_CONTENT, lv.SIZE_CONTENT)
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
            from appstore_core import AppUpdateManager, AppUpdateState
            updatable = []
            for app in self.apps:
                installed_path = getattr(app, "installed_path", None)
                if not installed_path:
                    continue
                remote = getattr(app, "_remote_version", None)
                if not remote:
                    continue
                if AppManager.is_update_available(app.fullname, remote):
                    updatable.append({
                        "fullname": app.fullname,
                        "version": remote,
                        "name": app.name,
                        "download_url": app.download_url,
                    })
            AppUpdateManager.get_instance().updatable_apps = updatable
            if updatable:
                AppUpdateManager.get_instance().current_state = AppUpdateState.UPDATES_AVAILABLE
            state = AppUpdateState.UPDATES_AVAILABLE if updatable else AppUpdateState.NO_UPDATES
            self._sync_update_banner(state, updatable)
        except Exception:
            pass
        if __debug__: logger.debug("create_apps_list done")

    _SORT_STRIP = "!\"'?:;.,@#$%^&*()-_=+[]{}\\|`~<>/"

    def _sort_key(self, name):
        return name.lstrip(self._SORT_STRIP).lower()

    def _find_sorted_insert_index(self, app):
        app_key = self._sort_key(app.name)
        for i, existing in enumerate(self.apps):
            if app_key < self._sort_key(existing.name):
                return i
        return len(self.apps)

    def _insert_app_list_item(self, app, index):
        """Create LVGL widgets for an app and insert at the given index in the list."""
        if not hasattr(self, "apps_list") or not self.apps_list:
            return
        if not self.has_foreground():
            return
        sel_cat = getattr(self, "_selected_category", None)
        if sel_cat == "Installed":
            if app.installed_path is None:
                return
        elif sel_cat == "Updates":
            try:
                from appstore_core import AppUpdateManager
                updatable_set = {a.get("fullname") for a in (AppUpdateManager.get_instance().updatable_apps or [])}
            except Exception:
                updatable_set = set()
            if app.fullname not in updatable_set:
                return
        elif sel_cat and sel_cat not in AppStore._SPECIAL_CATEGORIES:
            if not app.categories or sel_cat not in app.categories:
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
        name_row = lv.obj(label_cont)
        self._apply_default_styles(name_row)
        name_row.set_flex_flow(lv.FLEX_FLOW.ROW)
        name_row.set_size(lv.pct(100), lv.SIZE_CONTENT)
        self._add_click_handler(name_row, self.show_app_detail, app)
        name_label = lv.label(name_row)
        name_label.set_text(app.name)
        name_label.set_style_text_font(lv.font_montserrat_16, lv.PART.MAIN)
        name_label.set_flex_grow(1)
        self._add_click_handler(name_label, self.show_app_detail, app)
        rating_avg = getattr(app, "rating_average", None)
        if rating_avg is not None and rating_avg > 0:
            rating_label = lv.label(name_row)
            rating_label.set_text("%s %.1f" % (STAR_SYMBOL, rating_avg))
            rating_label.set_style_text_font(lv.font_montserrat_12, lv.PART.MAIN)
            rating_label.set_size(lv.SIZE_CONTENT, lv.SIZE_CONTENT)
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
        sel_cat = getattr(self, "_selected_category", None)
        if sel_cat == "Installed" and not app.installed_path:
            item.add_flag(lv.obj.FLAG.HIDDEN)
        elif sel_cat == "Updates":
            try:
                from appstore_core import AppUpdateManager
                updatable_set = {a.get("fullname") for a in (AppUpdateManager.get_instance().updatable_apps or [])}
            except Exception:
                updatable_set = set()
            if app.fullname not in updatable_set:
                item.add_flag(lv.obj.FLAG.HIDDEN)
        elif sel_cat and sel_cat not in ("All", "Work In Progress"):
            if not app.categories or sel_cat not in app.categories:
                item.add_flag(lv.obj.FLAG.HIDDEN)

    def _stop_all_timers(self):
        if self._raw_timer:
            self._raw_timer.delete()
            self._raw_timer = None

    def _process_icon_queue(self, timer):
        if not self._icon_queue:
            if self._download_in_progress:
                return
            if self._raw_timer:
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

    # ------------------------------------------------------------------
    # QR scanning and deep links
    # ------------------------------------------------------------------

    def scanqr_button_tap(self, event):
        from mpos.ui.camera_activity import CameraActivity
        self.startActivityForResult(
            Intent(activity_class=CameraActivity).putExtra("scanqr_intent", True),
            self.scanqr_result_callback,
        )

    def scanqr_result_callback(self, result):
        if not isinstance(result, dict) or not result.get("result_code"):
            return
        data = result.get("data")
        link = deeplink.parse_store_link(data)
        if link:
            self.open_app_by_fullname(link["fullname"])
            return
        # Not a store link: offer it to third-party URL handlers.
        if isinstance(data, str) and deeplink.open_url(data):
            return
        preview = data if isinstance(data, str) else repr(data)
        if len(preview) > 128:
            preview = preview[:128] + "..."
        self._show_scan_message("Not an app link", "This QR code is not a MicroPythonOS app link:\n\n%s" % preview)

    def open_app_by_fullname(self, fullname):
        """Open the detail screen for a store app, refreshing the index if needed."""
        app = self._find_store_app(fullname)
        if app:
            self.show_app_detail(app)
            return
        self._pending_deeplink = fullname
        if self._data_loaded and not self._refresh_in_progress:
            self.refresh_list()
        # Otherwise the index download is already underway and
        # _resolve_pending_deeplink() will run when it finishes.

    def _find_store_app(self, fullname):
        for app in self.apps:
            if app.fullname == fullname:
                return app
        for app in self._wip_apps:
            if app.fullname == fullname:
                return app
        return None

    def _try_early_deeplink(self):
        """Open a pending deep link now if the app is already resolvable."""
        fullname = getattr(self, "_pending_deeplink", None)
        if not fullname:
            return
        app = self._find_store_app(fullname)
        if app:
            self._pending_deeplink = None
            self.show_app_detail(app)

    def _resolve_pending_deeplink(self, index_available=True):
        fullname = getattr(self, "_pending_deeplink", None)
        if not fullname:
            return
        self._pending_deeplink = None
        app = self._find_store_app(fullname)
        if app:
            self.show_app_detail(app)
        elif not index_available:
            self._show_scan_message("No connection",
                                    "Could not download the app index to look up '%s'.\nCheck your network connection and try again." % fullname)
        else:
            self._show_scan_message("App not found",
                                    "App '%s' is not in the App Store.\nIt may have been removed, or your device may need a system update." % fullname)

    def _show_scan_message(self, title, text):
        mbox = lv.msgbox(lv.layer_top())
        mbox.add_title(title)
        mbox.add_text(text)
        ok = mbox.add_footer_button("OK")
        ok.add_event_cb(lambda e: mbox.delete(), lv.EVENT.CLICKED, None)
        close = mbox.add_close_button()
        close.add_event_cb(lambda e: mbox.delete(), lv.EVENT.CLICKED, None)
        mbox.add_event_cb(lambda e: mbox.delete(), lv.EVENT.CANCEL, None)

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
        category = bhapp.get("categories")
        ratings = bhapp.get("ratings") or {}
        rating_average = ratings.get("average")
        rating_count = ratings.get("count", 0)
        return App(name, None, short_description, None, icon_url, None, fullname, bhapp.get("version"), category, None, blur_hash=blur_hash, rating_average=rating_average, rating_count=rating_count)

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
