import lvgl as lv
import math
import time
import uhashlib
import ubinascii

from mpos import AppearanceManager, AppManager, Activity, DisplayMetrics

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
        main_screen.set_style_radius(0, lv.PART.MAIN)
        main_screen.set_pos(0, AppearanceManager.NOTIFICATION_BAR_HEIGHT)
        main_screen.set_style_pad_hor(0, lv.PART.MAIN)
        main_screen.set_style_pad_ver(AppearanceManager.NOTIFICATION_BAR_HEIGHT, lv.PART.MAIN)
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
        width_margin = 25
        icons_fit_width = math.floor((DisplayMetrics.width()-width_margin) / icon_size)
        #print(f"{icons_fit_width} icons fit")
        iconcont_width = int((DisplayMetrics.width()-width_margin) / icons_fit_width)
        #print(f"{iconcont_width} iconcont_width")
        iconcont_height = icon_size + label_height

        for app in AppManager.get_app_list():
            if app.category == "launcher" or (app.fullname != "com.micropythonos.settings.wifi" and app.fullname.startswith("com.micropythonos.settings.")):
                # Ignore launchers and MPOS settings (except wifi)
                continue

            app_name = app.name
            app_dir_fullpath = app.installed_path
            #print(f"Adding app {app_name} from {app_dir_fullpath}")

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
            app_cont.add_event_cb(lambda e, fullname=app.fullname: AppManager.start_app(fullname),lv.EVENT.CLICKED, None)
            app_cont.add_event_cb(lambda e, cont=app_cont: self.focus_app_cont(cont),lv.EVENT.FOCUSED, None)
            app_cont.add_event_cb(lambda e, cont=app_cont: self.defocus_app_cont(cont),lv.EVENT.DEFOCUSED, None)

            if focusgroup:
                focusgroup.add_obj(app_cont)

        # ------------------------------------------------------------------
        # 4. Add "Manage" icon
        manage_cont = lv.obj(screen)
        manage_cont.set_size(iconcont_width, iconcont_height)
        manage_cont.set_style_border_width(0, lv.PART.MAIN)
        manage_cont.set_style_pad_all(0, lv.PART.MAIN)
        manage_cont.set_style_bg_opa(lv.OPA.TRANSP, lv.PART.MAIN)
        manage_cont.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)

        manage_img = lv.image(manage_cont)
        manage_icon_path = "builtin/apps/com.micropythonos.launcher/assets/manage_icon_64x64.png"
        try:
            manage_img.set_src(Launcher.create_icon_dsc(manage_icon_path))
        except Exception:
            manage_img.set_src(lv.SYMBOL.SETTINGS)
        manage_img.align(lv.ALIGN.TOP_MID, 0, 0)
        manage_img.set_size(icon_size, icon_size)

        manage_label = lv.label(manage_cont)
        manage_label.set_text("Manage")
        manage_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        manage_label.set_width(iconcont_width)
        manage_label.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        manage_label.set_style_text_align(lv.TEXT_ALIGN.CENTER, lv.PART.MAIN)

        def manage_clicked(e):
            msgbox = lv.msgbox(None)
            msgbox.add_title("Manage Apps")
            msgbox.add_close_button()
            
            content = msgbox.get_content()
            content.set_flex_flow(lv.FLEX_FLOW.ROW)
            content.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
            content.set_style_pad_all(10, lv.PART.MAIN)
            content.set_style_pad_column(20, lv.PART.MAIN)

            # Delete Icon
            del_cont = lv.obj(content)
            del_cont.set_size(icon_size, icon_size)
            del_cont.set_style_border_width(0, lv.PART.MAIN)
            del_cont.set_style_bg_opa(lv.OPA.TRANSP, lv.PART.MAIN)
            del_img = lv.image(del_cont)
            del_cont.remove_flag(lv.obj.FLAG.SCROLLABLE)
            del_icon_path = "builtin/apps/com.micropythonos.launcher/assets/delete_icon_64x64.png"
            try:
                del_img.set_src(Launcher.create_icon_dsc(del_icon_path))
            except Exception:
                del_img.set_src(lv.SYMBOL.TRASH)
            del_img.center()
            del_cont.add_event_cb(lambda e: print("Delete pressed"), lv.EVENT.CLICKED, None)

            # Update Icon
            upd_cont = lv.obj(content)
            upd_cont.set_size(icon_size, icon_size)
            upd_cont.set_style_border_width(0, lv.PART.MAIN)
            upd_cont.set_style_bg_opa(lv.OPA.TRANSP, lv.PART.MAIN)
            upd_img = lv.image(upd_cont)
            upd_cont.remove_flag(lv.obj.FLAG.SCROLLABLE)
            upd_icon_path = "builtin/apps/com.micropythonos.launcher/assets/update_icon_64x64.png"
            try:
                upd_img.set_src(Launcher.create_icon_dsc(upd_icon_path))
            except Exception:
                upd_img.set_src(lv.SYMBOL.REFRESH)
            upd_img.center()
            upd_cont.add_event_cb(lambda e: print("Update pressed"), lv.EVENT.CLICKED, None)

        manage_cont.add_event_cb(manage_clicked, lv.EVENT.CLICKED, None)
        manage_cont.add_event_cb(lambda e, cont=manage_cont: self.focus_app_cont(cont), lv.EVENT.FOCUSED, None)
        manage_cont.add_event_cb(lambda e, cont=manage_cont: self.defocus_app_cont(cont), lv.EVENT.DEFOCUSED, None)

        if focusgroup:
            focusgroup.add_obj(manage_cont)

        # ------------------------------------------------------------------
        # 5. Store the new representation for the next resume
        self._last_app_list = current_apps
        self._last_ui_built = True

        end = time.ticks_ms()
        print(f"Redraw icons took: {end-start}ms (full rebuild)")

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
