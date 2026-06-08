import logging
import lvgl as lv
import math
import time
import uhashlib
import ubinascii

from mpos import AppearanceManager, AppManager, Activity, DisplayMetrics

logger = logging.getLogger(__name__)

class Launcher(Activity):
    def __init__(self):
        super().__init__()
        # Cache of the last app list + a quick hash of the icons
        self._last_app_list = None          # list of tuples (name, path, icon_hash)
        self._last_ui_built = False         # was UI built at least once?
        self._last_started_fullname = None  # fullname of the last app the user launched
        self._app_cont_map = {}             # fullname -> app_cont widget
        self._splash_fullname = None        # fullname of the app being launched (splash shown)
        self._splash_screen = None          # temporary splash screen shown before app launch
        self._screen = None                 # the launcher's own screen object

    def onCreate(self):
        if __debug__: logger.debug("onCreate")
        main_screen = lv.obj()
        main_screen.set_style_border_width(0, lv.PART.MAIN)
        main_screen.set_style_radius(0, lv.PART.MAIN)
        main_screen.set_pos(0, AppearanceManager.NOTIFICATION_BAR_HEIGHT)
        main_screen.set_style_pad_hor(0, lv.PART.MAIN)
        main_screen.set_style_pad_ver(AppearanceManager.NOTIFICATION_BAR_HEIGHT, lv.PART.MAIN)
        main_screen.set_flex_flow(lv.FLEX_FLOW.ROW_WRAP)
        self._screen = main_screen
        self.setContentView(main_screen)

    # ------------------------------------------------------------------
    # Helper: compute a cheap hash of a file (or return None if missing)
    @staticmethod
    def _hash_file(path):
        try:
            with open(path, "rb") as f:
                h = uhashlib.sha1()
                while True:
                    data = f.read(1024)
                    if not data:
                        break
                    h.update(data)
                return ubinascii.hexlify(h.digest()).decode()
        except Exception:
            return None

    # ------------------------------------------------------------------
    def onResume(self, screen):
        # If we were showing a splash, force a full rebuild to clean up
        self._exit_splash_mode(screen)

        # ------------------------------------------------------------------
        # 1. Build a *compact* representation of the current app list
        current_apps = []
        for app in AppManager.get_app_list():
            if app.category == "launcher":
                continue
            icon_hash = Launcher._hash_file(app.icon_path)   # cheap SHA-1 of the icon file
            current_apps.append((app.name, app.installed_path, icon_hash))

        # ------------------------------------------------------------------
        # 2. Compare with the cached list – if identical we skip UI rebuild
        start = time.ticks_ms()
        rebuild_needed = True

        if (self._last_app_list is not None and
            len(self._last_app_list) == len(current_apps)):
            # element-wise compare (name, path, icon_hash)
            if all(a == b for a, b in zip(self._last_app_list, current_apps)):
                rebuild_needed = False

        if not rebuild_needed:
            end = time.ticks_ms()
            if __debug__: logger.debug("redraw took %dms (cached)", end - start)
            self._focus_last_or_first()
            return

        # ------------------------------------------------------------------
        # 3. UI needs (re)building – clear screen and create widgets
        screen.clean()
        self._app_cont_map = {}

        focusgroup = lv.group_get_default()

        # Grid parameters
        icon_size = 64
        label_height = 24
        width_margin = 25
        icons_fit_width = math.floor((DisplayMetrics.width()-width_margin) / icon_size)
        iconcont_width = int((DisplayMetrics.width()-width_margin) / icons_fit_width)
        iconcont_height = icon_size + label_height

        for app in AppManager.get_app_list():
            if app.category == "launcher" or (app.fullname != "com.micropythonos.settings.wifi" and app.fullname.startswith("com.micropythonos.settings.")):
                # Ignore launchers and MPOS settings (except wifi)
                continue

            app_name = app.name
            app_dir_fullpath = app.installed_path

            # ----- container ------------------------------------------------
            app_cont = lv.obj(screen)
            app_cont.set_size(iconcont_width, iconcont_height)
            app_cont.set_style_border_width(0, lv.PART.MAIN)
            app_cont.set_style_pad_all(0, lv.PART.MAIN)
            app_cont.set_style_bg_opa(lv.OPA.TRANSP, lv.PART.MAIN)
            app_cont.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)

            # ----- icon ----------------------------------------------------
            image = lv.image(app_cont)
            if app.icon_data:
                image.set_src(lv.image_dsc_t({
                    'data_size': len(app.icon_data),
                    'data': app.icon_data
                }))
            else:
                image.set_src(lv.SYMBOL.IMAGE)
            image.align(lv.ALIGN.TOP_MID, 0, 0)
            image.set_size(icon_size, icon_size)

            # ----- label ---------------------------------------------------
            label = lv.label(app_cont)
            label.set_text(app_name)
            label.set_long_mode(lv.label.LONG_MODE.WRAP)
            label.set_width(iconcont_width)
            label.align(lv.ALIGN.BOTTOM_MID, 0, 0)
            label.set_style_text_align(lv.TEXT_ALIGN.CENTER, lv.PART.MAIN)

            # ----- events --------------------------------------------------
            app_cont.add_event_cb(lambda e, fullname=app.fullname: self._launch_app(fullname), lv.EVENT.CLICKED, None)
            app_cont.add_event_cb(lambda e, cont=app_cont: self.focus_app_cont(cont),lv.EVENT.FOCUSED, None)
            app_cont.add_event_cb(lambda e, cont=app_cont: self.defocus_app_cont(cont),lv.EVENT.DEFOCUSED, None)

            focusgroup.add_obj(app_cont)
            self._app_cont_map[app.fullname] = app_cont

        # ------------------------------------------------------------------
        # 4. Store the new representation for the next resume
        self._last_app_list = current_apps
        self._last_ui_built = True

        end = time.ticks_ms()
        if __debug__: logger.debug("redraw took %dms (full rebuild)", end - start)

        self._focus_last_or_first()

    # ------------------------------------------------------------------
    def _launch_app(self, fullname):
        """Record which app was launched, show splash screen, then start it."""
        self._last_started_fullname = fullname
        self._splash_fullname = fullname

        splash_screen = lv.obj()
        splash_screen.set_style_border_width(0, lv.PART.MAIN)
        splash_screen.set_style_radius(0, lv.PART.MAIN)
        splash_screen.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)

        splash_cont = self._app_cont_map.get(fullname)
        if splash_cont:
            image = splash_cont.get_child(0)
            if image:
                splash_icon = lv.image(splash_screen)
                splash_icon.set_src(image.get_src())
                splash_icon.set_scale(384)
                splash_icon.align(lv.ALIGN.CENTER, 0, 0)

        self._splash_screen = splash_screen
        animation_time = 250
        lv.screen_load_anim(splash_screen, lv.SCREEN_LOAD_ANIM.OVER_LEFT, animation_time, 0, False)

        # Wait until after the animation so LVGL renders the splash before the app starts
        timer = lv.timer_create(lambda t: self._do_start_app(t, fullname), 2*animation_time, None)
        timer.set_repeat_count(1)

    def _do_start_app(self, timer, fullname):
        start_result = AppManager.start_app(fullname)
        if __debug__: logger.debug("start_result=%s", start_result)

        # On failure restore the launcher icon grid immediately using our own
        # screen reference (lv.screen_active() would be unreliable here if a
        # new app screen was partially pushed before failing).
        if start_result is False:
            lv.screen_load_anim(self._screen, lv.SCREEN_LOAD_ANIM.OVER_RIGHT, 500, 0, True)
            self.onResume(self._screen)
        else:
            self._cleanup_splash_screen()

    def _cleanup_splash_screen(self):
        splash_screen = self._splash_screen
        if splash_screen is None:
            return
        self._splash_screen = None
        try:
            if splash_screen != lv.screen_active():
                splash_screen.delete()
        except Exception:
            pass

    def _exit_splash_mode(self, screen):
        if self._splash_fullname is None and self._splash_screen is None:
            return
        self._splash_fullname = None
        self._cleanup_splash_screen()
        screen.set_scrollbar_mode(lv.SCROLLBAR_MODE.AUTO)

    # ------------------------------------------------------------------
    def _focus_last_or_first(self):
        """Focus the last launched app tile, or the first tile if none was launched yet."""
        focusgroup = lv.group_get_default()
        if not focusgroup:
            return
        target = self._app_cont_map.get(self._last_started_fullname)
        if target:
            lv.group_focus_obj(target)
        else:
            focusgroup.focus_next()

    # ------------------------------------------------------------------
    @staticmethod
    def create_icon_dsc(icon_path):
        with open(icon_path, 'rb') as f:
            image_data = f.read()
            image_dsc = lv.image_dsc_t({
                'data_size': len(image_data),
                'data': image_data
            })
        return image_dsc

    # ------------------------------------------------------------------
    def focus_app_cont(self, app_cont):
        app_cont.set_style_border_color(lv.theme_get_color_primary(None), lv.PART.MAIN)
        app_cont.set_style_border_width(1, lv.PART.MAIN)
        app_cont.scroll_to_view(True)

    def defocus_app_cont(self, app_cont):
        app_cont.set_style_border_width(0, lv.PART.MAIN)
