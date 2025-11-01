# bin files:
# All icons took: 1085ms
# All icons took: 1051ms
# All icons took: 1032ms
# All icons took: 1118ms
# png files:
# All icons took: 1258ms
# All icons took: 1457ms
# All icons took: 1250ms
# Most of this time is actually spent reading and parsing manifests.
import lvgl as lv
import mpos.apps
import mpos.ui
from mpos.content.package_manager import PackageManager
from mpos import Activity
import time
import uhashlib
import ubinascii


class Launcher(Activity):
    def __init__(self):
        super().__init__()
        # Cache of the last app list + a quick hash of the icons
        self._last_app_list = None          # list of tuples (name, path, icon_hash)
        self._last_ui_built = False         # was UI built at least once?

    def onCreate(self):
        print("launcher.py onCreate()")
        main_screen = lv.obj()
        main_screen.set_style_border_width(0, lv.PART.MAIN)
        main_screen.set_style_radius(0, 0)
        main_screen.set_pos(0, mpos.ui.topmenu.NOTIFICATION_BAR_HEIGHT)
        main_screen.set_style_pad_hor(mpos.ui.pct_of_display_width(2), 0)
        main_screen.set_style_pad_ver(mpos.ui.topmenu.NOTIFICATION_BAR_HEIGHT, 0)
        main_screen.set_flex_flow(lv.FLEX_FLOW.ROW_WRAP)
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
        # ------------------------------------------------------------------
        # 1. Build a *compact* representation of the current app list
        current_apps = []
        for app in PackageManager.get_app_list():
            if app.category == "launcher":
                continue
            icon_path = f"{app.installed_path}/res/mipmap-mdpi/icon_64x64.png"
            icon_hash = Launcher._hash_file(icon_path)   # cheap SHA-1 of the icon file
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
            print(f"Redraw icons took: {end-start}ms (cached – no change)")
            return

        # ------------------------------------------------------------------
        # 3. UI needs (re)building – clear screen and create widgets
        screen.clean()

        focusgroup = lv.group_get_default()
        if not focusgroup:
            print("WARNING: could not get default focusgroup")

        # Grid parameters
        icon_size = 64
        label_height = 24
        iconcont_width = icon_size + label_height
        iconcont_height = icon_size + label_height

        for app in PackageManager.get_app_list():
            if app.category == "launcher":
                continue

            app_name = app.name
            app_dir_fullpath = app.installed_path
            print(f"Adding app {app_name} from {app_dir_fullpath}")

            # ----- container ------------------------------------------------
            app_cont = lv.obj(screen)
            app_cont.set_size(iconcont_width, iconcont_height)
            app_cont.set_style_border_width(0, lv.PART.MAIN)
            app_cont.set_style_pad_all(0, 0)
            app_cont.set_style_bg_opa(lv.OPA.TRANSP, 0)
            app_cont.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)

            # ----- icon ----------------------------------------------------
            icon_path = f"{app_dir_fullpath}/res/mipmap-mdpi/icon_64x64.png"
            image = lv.image(app_cont)
            try:
                image.set_src(Launcher.load_icon(icon_path))
            except Exception as e:
                print(f"Error loading icon {icon_path}: {e} - loading default")
                icon_path = "builtin/res/mipmap-mdpi/default_icon_64x64.png"
                try:
                    image.set_src(Launcher.load_icon(icon_path))
                except Exception as e:
                    print(f"Error loading default {icon_path}: {e} - using symbol")
                    image.set_src(lv.SYMBOL.STOP)

            image.align(lv.ALIGN.TOP_MID, 0, 0)
            image.set_size(icon_size, icon_size)

            # ----- label ---------------------------------------------------
            label = lv.label(app_cont)
            label.set_text(app_name)
            label.set_long_mode(lv.label.LONG_MODE.WRAP)
            label.set_width(iconcont_width)
            label.align(lv.ALIGN.BOTTOM_MID, 0, 0)
            label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

            # ----- events --------------------------------------------------
            app_cont.add_event_cb(
                lambda e, fullname=app.fullname: mpos.apps.start_app(fullname),
                lv.EVENT.CLICKED, None)
            app_cont.add_event_cb(
                lambda e, cont=app_cont: self.focus_app_cont(cont),
                lv.EVENT.FOCUSED, None)
            app_cont.add_event_cb(
                lambda e, cont=app_cont: self.defocus_app_cont(cont),
                lv.EVENT.DEFOCUSED, None)

            if focusgroup:
                focusgroup.add_obj(app_cont)

        # ------------------------------------------------------------------
        # 4. Store the new representation for the next resume
        self._last_app_list = current_apps
        self._last_ui_built = True

        end = time.ticks_ms()
        print(f"Redraw icons took: {end-start}ms (full rebuild)")

    # ------------------------------------------------------------------
    @staticmethod
    def load_icon(icon_path):
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
