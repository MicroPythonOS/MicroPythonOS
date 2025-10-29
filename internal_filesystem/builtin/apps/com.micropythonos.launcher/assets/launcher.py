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

import uos
import lvgl as lv

import mpos.apps
import mpos.ui
from mpos.package_manager import PackageManager

class Launcher(mpos.apps.Activity):

    def onCreate(self):
        print("launcher.py onCreate()")
        main_screen = lv.obj()
        main_screen.set_style_border_width(0, lv.PART.MAIN)
        main_screen.set_style_radius(0, 0)
        main_screen.set_pos(0, mpos.ui.topmenu.NOTIFICATION_BAR_HEIGHT) # leave some margin for the notification bar
        #main_screen.set_size(lv.pct(100), lv.pct(100))
        main_screen.set_style_pad_hor(mpos.ui.pct_of_display_width(2), 0)
        main_screen.set_style_pad_ver(mpos.ui.topmenu.NOTIFICATION_BAR_HEIGHT, 0)
        main_screen.set_flex_flow(lv.FLEX_FLOW.ROW_WRAP)
        self.setContentView(main_screen)

    def onResume(self, screen):
        # Grid parameters
        icon_size = 64  # Adjust based on your display
        label_height = 24
        iconcont_width = icon_size + label_height
        iconcont_height = icon_size + label_height

        app_list = PackageManager.app_list

        import time
        start = time.ticks_ms()

        screen.clean()

        # Get the group for focusable objects
        focusgroup = lv.group_get_default()
        if not focusgroup:
            print("WARNING: could not get default focusgroup")

        # Create UI for each app
        for app in app_list:
            app_name = app.name
            app_dir_fullpath = app.installed_path
            print(f"Adding app {app_name} from {app_dir_fullpath}")
            # Create container for each app (icon + label)
            app_cont = lv.obj(screen)
            app_cont.set_size(iconcont_width, iconcont_height)
            app_cont.set_style_border_width(0, lv.PART.MAIN)
            app_cont.set_style_pad_all(0, 0)
            app_cont.set_style_bg_opa(lv.OPA.TRANSP,0) # prevent default style from adding slight gray to this container
            app_cont.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
            # Load and display icon
            icon_path = f"{app_dir_fullpath}/res/mipmap-mdpi/icon_64x64.png"
            image = lv.image(app_cont)
            try:
                image.set_src(Launcher.load_icon(icon_path))
            except Exception as e:
                print(f"Error loading icon {icon_path}: {e} - loading default icon")
                icon_path = "builtin/res/mipmap-mdpi/default_icon_64x64.png"
                try:
                    image.set_src(Launcher.load_icon(icon_path))
                except Exception as e:
                    print(f"Error loading default icon {icon_path}: {e} - using symbol")
                    image.set_src(lv.SYMBOL.STOP)
            image.align(lv.ALIGN.TOP_MID, 0, 0)
            image.set_size(icon_size, icon_size)
            label = lv.label(app_cont)
            label.set_text(app_name)  # Use app_name directly
            label.set_long_mode(lv.label.LONG_MODE.WRAP)
            label.set_width(iconcont_width)
            label.align(lv.ALIGN.BOTTOM_MID, 0, 0)
            label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
            app_cont.add_event_cb(lambda e, path=app_dir_fullpath: mpos.apps.start_app(path), lv.EVENT.CLICKED, None)
            app_cont.add_event_cb(lambda e, app_cont=app_cont: self.focus_app_cont(app_cont),lv.EVENT.FOCUSED,None)
            app_cont.add_event_cb(lambda e, app_cont=app_cont: self.defocus_app_cont(app_cont),lv.EVENT.DEFOCUSED,None)
            if focusgroup:
                focusgroup.add_obj(app_cont)
        
        end = time.ticks_ms()
        print(f"Redraw icons took: {end-start}ms")

    @staticmethod
    def load_icon(icon_path):
        with open(icon_path, 'rb') as f:
            image_data = f.read()
            image_dsc = lv.image_dsc_t({
                'data_size': len(image_data),
                'data': image_data
            })
        return image_dsc

    def focus_app_cont(self, app_cont):
        #print(f"app_cont {app_cont} focused, setting border...")
        app_cont.set_style_border_color(lv.theme_get_color_primary(None),lv.PART.MAIN)
        app_cont.set_style_border_width(1, lv.PART.MAIN)
        app_cont.scroll_to_view(True) # scroll to bring it into view

    def defocus_app_cont(self, app_cont):
        #print(f"app_cont {app_cont} defocused, unsetting border...")
        app_cont.set_style_border_width(0, lv.PART.MAIN)
