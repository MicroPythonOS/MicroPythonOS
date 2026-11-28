import logging

import lvgl as lv

from mpos import Activity, AppManager, TaskManager, WidgetAnimator
try:
    from mpos import extent as extent_files
except ImportError:
    extent_files = None
from mpos.ui import STAR_SYMBOL, add_focus_highlight
import store_source
from store_install import install_package, update_available, forget_receipt, exists, clear_app_cache
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
    installed_version_label = None
    buttoncont = None
    publisher_label = None
    _open_button = None
    icon_image = None
    rate_cont = None
    _stars = None
    _selected_rating = 0
    _rated = False
    _submit_rating_btn = None
    _icon_download_started = False
    _icon_timer = None
    _icon_token = None

    # Received from the Intent extras:
    app = None
    appstore = None

    def _open_app(self, app_fullname):
        if __debug__: logger.debug("APPSTORE_OPEN_REQUEST %s", app_fullname)
        if not AppManager.start_app(app_fullname):
            if self.has_foreground():
                self.long_desc_label.set_text("App failed to open. Check its dependencies or uninstall and retry.")
            logger.warning("APPSTORE_OPEN_FAILED %s", app_fullname)

    def _sync_open_button(self):
        if self._open_button is None:
            return
        if AppManager.is_installed_by_name(self.app.fullname):
            self._open_button.remove_flag(lv.obj.FLAG.HIDDEN)
        else:
            self._open_button.add_flag(lv.obj.FLAG.HIDDEN)

    def _sync_rate_cont(self):
        if self.rate_cont is None:
            return
        if getattr(self.app, "_store_source", store_source.current_source()) != "upystore" and AppManager.is_installed_by_name(self.app.fullname) and not self._rated:
            self.rate_cont.remove_flag(lv.obj.FLAG.HIDDEN)
        else:
            self.rate_cont.add_flag(lv.obj.FLAG.HIDDEN)

    def _on_star_click(self, idx):
        if self._rated:
            return
        self._selected_rating = idx + 1
        yellow = lv.palette_main(lv.PALETTE.YELLOW)
        gray = lv.color_hex(0x888888)
        for i, star in enumerate(self._stars):
            star.set_style_text_color(yellow if i <= idx else gray, lv.PART.MAIN)
        WidgetAnimator.smooth_show(self._submit_rating_btn, duration=200)

    def _on_submit_rating(self, e):
        self._rated = True
        WidgetAnimator.smooth_hide(self._submit_rating_btn, duration=200)
        thanks = lv.label(self.rate_cont)
        thanks.set_text("Rating submitted. Thanks!")
        thanks.set_style_text_font(lv.font_montserrat_16, lv.PART.MAIN)
        thanks.set_size(lv.pct(100), lv.SIZE_CONTENT)
        revision = getattr(self.app, "revision", None)
        if revision is not None:
            from appstore_core import report_badgehub_rating
            TaskManager.create_task(report_badgehub_rating(
                self.app.fullname, revision, self._selected_rating
            ))

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
            self.app.icon_data = await store_source.request(self.app.icon_url, timeout=10)
        except Exception as e:
            if __debug__: logger.debug("download of %s failed: %s", self.app.icon_url, e)
            self._icon_download_started = False
            return
        if not self.has_foreground():
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
        if self.has_foreground():
            self.progress_bar.set_value(value, wait)
        if wait:
            await TaskManager.sleep(1)

    def _show_progress_bar(self):
        """Show progress bar and reset to 0"""
        if self.has_foreground():
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
        name_row = lv.obj(detail_cont)
        self._apply_default_styles(name_row)
        name_row.set_flex_flow(lv.FLEX_FLOW.ROW)
        name_row.set_size(lv.pct(100), lv.SIZE_CONTENT)
        name_label = lv.label(name_row)
        name_label.set_text(self.app.name)
        name_label.set_style_text_font(lv.font_montserrat_24, lv.PART.MAIN)
        name_label.set_flex_grow(1)
        rating_avg = getattr(self.app, "rating_average", None)
        if rating_avg is not None and rating_avg > 0:
            rating_label = lv.label(name_row)
            rating_label.set_text("%s %.1f" % (STAR_SYMBOL, rating_avg))
            rating_label.set_style_text_font(lv.font_montserrat_16, lv.PART.MAIN)
            rating_label.set_size(lv.SIZE_CONTENT, lv.SIZE_CONTENT)
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
        self.rate_cont = lv.obj(app_detail_screen)
        self._apply_default_styles(self.rate_cont)
        self.rate_cont.set_size(lv.pct(100), lv.SIZE_CONTENT)
        self.rate_cont.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        self.rate_cont.add_flag(lv.obj.FLAG.HIDDEN)
        rate_title = lv.label(self.rate_cont)
        rate_title.set_text("Rate this app")
        rate_title.set_style_text_font(lv.font_montserrat_16, lv.PART.MAIN)
        stars_row = lv.obj(self.rate_cont)
        self._apply_default_styles(stars_row)
        stars_row.set_size(lv.pct(100), lv.SIZE_CONTENT)
        stars_row.set_flex_flow(lv.FLEX_FLOW.ROW)
        stars_row.set_style_pad_ver(4, lv.PART.MAIN)
        stars_row.set_style_flex_main_place(lv.FLEX_ALIGN.SPACE_EVENLY, lv.PART.MAIN)
        self._stars = []
        for i in range(5):
            star = lv.label(stars_row)
            star.set_text(STAR_SYMBOL)
            star.set_style_text_font(lv.font_montserrat_24, lv.PART.MAIN)
            star.set_style_text_color(lv.color_hex(0x888888), lv.PART.MAIN)
            star.add_flag(lv.obj.FLAG.CLICKABLE)
            star.add_event_cb(lambda e, idx=i: self._on_star_click(idx), lv.EVENT.CLICKED, None)
            add_focus_highlight(star)
            self._stars.append(star)
        self._submit_rating_btn = lv.button(self.rate_cont)
        self._submit_rating_btn.set_size(lv.SIZE_CONTENT, 40)
        self._submit_rating_btn.set_style_pad_hor(12, lv.PART.MAIN)
        self._submit_rating_btn.add_flag(lv.obj.FLAG.HIDDEN)
        self._submit_rating_btn.add_event_cb(self._on_submit_rating, lv.EVENT.CLICKED, None)
        submit_label = lv.label(self._submit_rating_btn)
        submit_label.set_text("Submit Rating")
        submit_label.center()
        # version label:
        self.version_label = lv.label(app_detail_screen)
        self.version_label.set_width(lv.pct(100))
        self.version_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.version_label.set_style_text_font(lv.font_montserrat_12, lv.PART.MAIN)
        self.version_label.align_to(self.install_button, lv.ALIGN.OUT_BOTTOM_MID, 0, lv.pct(5))
        self.version_label.set_text("Loading details...")
        add_focus_highlight(self.version_label)
        self.installed_version_label = lv.label(app_detail_screen)
        self.installed_version_label.set_width(lv.pct(100))
        self.installed_version_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.installed_version_label.set_style_text_font(lv.font_montserrat_12, lv.PART.MAIN)
        self.installed_version_label.align_to(self.version_label, lv.ALIGN.OUT_BOTTOM_MID, 0, lv.pct(3))
        self.installed_version_label.add_flag(lv.obj.FLAG.HIDDEN)
        add_focus_highlight(self.installed_version_label)
        self.long_desc_label = lv.label(app_detail_screen)
        self.long_desc_label.align_to(self.installed_version_label, lv.ALIGN.OUT_BOTTOM_MID, 0, lv.pct(5))
        self.long_desc_label.set_text(self.app.long_description or self.app.short_description or "Loading details...")
        self.long_desc_label.set_style_text_font(lv.font_montserrat_12, lv.PART.MAIN)
        self.long_desc_label.set_width(lv.pct(100))
        self.long_desc_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        add_focus_highlight(self.long_desc_label)
        self._update_version_labels()

        if __debug__: logger.debug("loading app detail screen")
        self.setContentView(app_detail_screen)

    def onResume(self, screen):
        super().onResume(screen)
        self._sync_open_button()
        self._sync_rate_cont()
        TaskManager.create_task(self.fetch_and_set_app_details())

    def _start_icon_download(self):
        if self.has_foreground() and not self.app.icon_data and self.app.icon_url and not self._icon_download_started:
            self._icon_download_started = True
            token = object()
            self._icon_token = token
            self._icon_timer = lv.timer_create(lambda timer: self._download_icon_after_timer(timer, token), 500, None)

    def _download_icon_after_timer(self, timer, token=None):
        if token is not self._icon_token or self._icon_timer is None:
            return
        pending = self._icon_timer
        self._icon_timer = None
        self._icon_token = None
        pending.delete()
        if self.has_foreground():
            TaskManager.create_task(self._download_icon())
        else:
            self._icon_download_started = False

    def onPause(self, screen):
        super().onPause(screen)
        timer = self._icon_timer
        self._icon_timer = None
        self._icon_token = None
        if timer is not None:
            timer.delete()
            self._icon_download_started = False

    def onDestroy(self, screen):
        self.onPause(screen)
        self.appstore = None
        for name in (
            "install_button", "update_button", "progress_bar", "install_label", "long_desc_label",
            "version_label", "installed_version_label", "buttoncont", "publisher_label", "_open_button",
            "icon_image", "rate_cont", "_stars", "_submit_rating_btn",
        ):
            setattr(self, name, None)
        super().onDestroy(screen)

    @staticmethod
    def _read_installed_version(app_fullname):
        for base in ("apps", "builtin/apps"):
            manifest = "%s/%s/MANIFEST.JSON" % (base, app_fullname)
            try:
                import ujson
                with open(manifest, "r") as f:
                    data = ujson.load(f)
                return data.get("version")
            except Exception:
                continue
        return None

    def _update_version_labels(self):
        if self.version_label is not None:
            remote = getattr(self.app, "_remote_version", None) or self.app.version
            if remote:
                self.version_label.set_text("Available: %s%s" % (remote, " (r%s)" % self.app.revision if getattr(self.app, "revision", None) is not None else ""))
            else:
                self.version_label.set_text("Loading details...")
        if self.installed_version_label is not None:
            installed_version = self._read_installed_version(self.app.fullname)
            if installed_version:
                self.installed_version_label.set_text("Installed: %s" % installed_version)
                self.installed_version_label.remove_flag(lv.obj.FLAG.HIDDEN)
            else:
                self.installed_version_label.add_flag(lv.obj.FLAG.HIDDEN)

    def add_action_buttons(self, buttoncont, app):
        # clean() below deletes the current install button. If that is the
        # focused widget, LVGL would move focus to the next widget in the
        # group (the description label) when the details finish loading, so
        # remember it and put it back on the rebuilt button (issue #256).
        group = lv.group_get_default()
        install_had_focus = False
        if group is not None and self.install_button is not None:
            try:
                install_had_focus = group.get_focused() == self.install_button
            except lv.LvReferenceError:
                install_had_focus = False
        buttoncont.clean()
        buttoncont.set_style_pad_all(4, lv.PART.MAIN)
        buttoncont.set_style_pad_column(3, lv.PART.MAIN)
        if __debug__: logger.debug("adding (un)install button for url: %s", self.app.download_url)
        self.install_button = lv.button(buttoncont)
        self.install_button.set_style_pad_hor(3, lv.PART.MAIN)
        self.install_button.set_flex_grow(1)
        self.install_button.set_height(40)
        self.install_button.add_event_cb(lambda e, a=self.app: self.toggle_install(a), lv.EVENT.CLICKED, None)
        self.install_label = lv.label(self.install_button)
        self.install_label.center()
        self.set_install_label(self.app.fullname)
        self.update_button = None
        store_version = getattr(app, "_remote_version", None) or app.version
        if __debug__: logger.debug("update check: _remote_version=%s app.version=%s store_version=%s",
            getattr(app, "_remote_version", None), app.version, store_version)
        if store_version and update_available(self.app.fullname, store_version, getattr(app, "revision", None), getattr(app, "_store_source", None)):
            if __debug__: logger.debug("update available, adding update button")
            self.update_button = lv.button(buttoncont)
            self.update_button.set_style_pad_hor(3, lv.PART.MAIN)
            self.update_button.set_flex_grow(1)
            self.update_button.set_height(40)
            self.update_button.add_event_cb(lambda e, a=self.app: self.update_button_click(a), lv.EVENT.CLICKED, None)
            update_label = lv.label(self.update_button)
            update_label.set_text("Update")
            update_label.center()
        self._open_button = lv.button(buttoncont)
        self._open_button.set_style_pad_hor(3, lv.PART.MAIN)
        self._open_button.set_size(lv.SIZE_CONTENT, 40)
        self._open_button.add_event_cb(lambda e, a=self.app: self._open_app(a.fullname), lv.EVENT.CLICKED, None)
        open_label = lv.label(self._open_button)
        open_label.set_text(" Open ")
        open_label.center()
        self._sync_open_button()
        self._sync_rate_cont()
        self._update_version_labels()
        if install_had_focus:
            lv.group_focus_obj(self.install_button)

    def _description_text(self):
        description = getattr(self.app, "long_description", None) or ""
        if getattr(self.app, "_store_source", store_source.current_source()) == "upystore":
            description += "\n\nuPyStore: rating submission is not available."
            versions = getattr(self.app, "_store_versions", [])
            if versions:
                description += "\nPublished: " + ", ".join("%s (r%s)" % (v.get("version", "?"), v.get("revision", "?")) for v in versions[:8])
        return description

    async def fetch_and_set_app_details(self):
        if getattr(self, "_details_loading", False):
            return
        self._details_loading = True
        try:
            await self.fetch_badgehub_app_details(self.app)
            self._details_error = False
        except Exception as error:
            logger.warning("APPSTORE_DETAILS_FAILED %s %s %s", self.app.fullname, type(error).__name__, str(error))
            self._details_error = True
            if self.has_foreground():
                self.long_desc_label.set_text("Store details unavailable: %s. Tap Install to retry or return to the list." % store_source.error_text(error)[:90])
            return
        finally:
            self._details_loading = False
        if not self.has_foreground():
            return
        if __debug__: logger.debug("app has version: %s", self.app.version)
        self._update_version_labels()
        self.long_desc_label.set_text(self._description_text())
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
                if __debug__: logger.debug("no download_url yet")
                if getattr(self, "_details_error", False) and not getattr(self, "_details_loading", False):
                    TaskManager.create_task(self.fetch_and_set_app_details())
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
        if not download_url:
            if __debug__: logger.debug("no download_url yet, ignoring")
            return
        self._action_in_progress = True
        self.update_button.add_flag(lv.obj.FLAG.HIDDEN)
        self.install_button.add_state(lv.STATE.DISABLED)
        self.install_label.set_text("Please wait...")
        TaskManager.create_task(self.download_and_install(app_obj, f"apps/{fullname}"))

    async def uninstall_app(self, app_fullname):
        self._show_progress_bar()
        try:
            destination = "apps/" + store_source.identity(app_fullname)
            if not exists(destination):
                raise ValueError("No removable user installation")
            await self._update_progress(21)
            AppManager.uninstall_app(app_fullname)
            if exists(destination):
                raise OSError("Application directory could not be removed")
            clear_app_cache(destination)
            forget_receipt(app_fullname)
            logger.info("APPSTORE_UNINSTALL_SUCCESS %s", app_fullname)
            if self.has_foreground() and self.long_desc_label is not None:
                self.long_desc_label.set_text(self._description_text())
            await self._update_progress(100, wait=False)
            self._trigger_update_recheck()
        except Exception as error:
            logger.warning("APPSTORE_UNINSTALL_FAILED %s %s", app_fullname, error)
            if self.has_foreground():
                self.long_desc_label.set_text("Uninstall failed: %s. Retry or return to the list." % store_source.error_text(error)[:110])
        finally:
            self._action_in_progress = False
            AppManager.refresh_apps()
            if self.has_foreground():
                self._hide_progress_bar()
                self.add_action_buttons(self.buttoncont, self.app)

    async def pcb(self, percent):
        if not self.has_foreground():
            return
        if __debug__: logger.debug("pcb: %s", percent)
        scaled_percent_start = 5 # before 5% is preparation
        scaled_percent_finished = 60 # after 60% is unzip
        scaled_percent_diff = scaled_percent_finished - scaled_percent_start
        scale = 100 / scaled_percent_diff # 100 / 55 = 1.81
        scaled_percent = round(percent / scale)
        scaled_percent += scaled_percent_start
        self.progress_bar.set_value(scaled_percent, True)

    async def space_progress(self, phase, percent):
        """Called while an extent reservation defragments the filesystem."""
        if not self.has_foreground():
            return
        if percent <= 0 or (extent_files is not None and phase == extent_files.PHASE_SPACE):
            self.install_label.set_text("Defragmenting storage...")
        else:
            self.install_label.set_text("Defragmenting storage... %d%%" % percent)
        # The download bar keeps its position; this is a separate phase.
        await TaskManager.sleep(1)

    async def download_and_install(self, app_obj, dest_folder):
        app_fullname = app_obj.fullname
        self._show_progress_bar()
        await self._update_progress(5)
        try:
            receipt = await install_package(app_obj, progress_callback=self.pcb, space_callback=self.space_progress)
            if receipt and receipt.get("version"):
                app_obj._remote_version = receipt["version"]
                app_obj.revision = receipt.get("revision")

        except Exception as e:
            logger.warning("APPSTORE_INSTALL_FAILED %s %s %s", app_fullname, type(e).__name__, str(e))
            logger.error("download failed: %s", store_source.error_text(e))
            self._action_in_progress = False
            if self.has_foreground():
                self._hide_progress_bar()
                self.add_action_buttons(self.buttoncont, self.app)
                self.long_desc_label.set_text("Install failed: %s. Retry the action or return to the list." % store_source.error_text(e)[:110])
            return
        self._details_error = False
        if self.has_foreground() and self.long_desc_label is not None:
            self.long_desc_label.set_text(self._description_text())
        revision = getattr(app_obj, "revision", None)
        if revision is not None and getattr(app_obj, "_store_source", store_source.current_source()) == "badgehub":
            from appstore_core import report_badgehub_install
            TaskManager.create_task(report_badgehub_install(app_obj.fullname, revision))
        await self._update_progress(100, wait=False)
        self._action_in_progress = False
        AppManager.refresh_apps()
        if self.has_foreground():
            self._hide_progress_bar()
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
            AppUpdateManager.get_instance().check_for_updates_now()
        except Exception as e:
            logger.warning("could not schedule update recheck: %s", e)

    async def fetch_badgehub_app_details(self, app_obj):
        result = await store_source.fetch_details(app_obj.fullname, getattr(app_obj, "_store_slug", None), getattr(app_obj, "_store_source", None))
        store_source.attach(app_obj, result)
        app_obj.download_url = result.get("download_url")
        app_obj.download_url_size = result.get("download_url_size")
        app_obj.long_description = result.get("long_description") or app_obj.short_description
        app_obj._store_versions = result.get("versions", [])
