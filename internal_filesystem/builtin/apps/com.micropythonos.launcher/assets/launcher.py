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
import _thread

# Mode constants
MODE_LAUNCHING = 0
MODE_UNINSTALL = 1


class Launcher(Activity):
    def __init__(self):
        super().__init__()
        # Cache of the last app list + a quick hash of the icons
        self._last_app_list = None          # list of tuples (name, path, icon_hash)
        self._last_ui_built = False         # was UI built at least once?
        self._current_mode = MODE_LAUNCHING # current launcher mode
        self._mode_button = None            # reference to mode toggle button
        self._mode_button_icon = None       # reference to mode button icon
        self._mode_button_label = None      # reference to mode button label
        self._app_widgets = []              # list to store app widget references

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
    def _create_mode_button(self, screen, icon_size, label_height, iconcont_width, iconcont_height, focusgroup):
        """Create the mode toggle button as an app-like icon in the grid"""
        import os

        # ----- container (same as regular apps) -------------------------
        mode_cont = lv.obj(screen)
        mode_cont.set_size(iconcont_width, iconcont_height)
        mode_cont.set_style_border_width(0, lv.PART.MAIN)
        mode_cont.set_style_pad_all(0, 0)
        mode_cont.set_style_bg_opa(lv.OPA.TRANSP, 0)
        mode_cont.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)

        # ----- icon -----------------------------------------------------
        mode_icon = lv.image(mode_cont)
        mode_icon.align(lv.ALIGN.TOP_MID, 0, 0)
        mode_icon.set_size(icon_size, icon_size)

        # Load appropriate icon based on mode
        if self._current_mode == MODE_LAUNCHING:
            # Show trashcan icon (enter uninstall mode)
            try:
                app_dir = os.path.dirname(os.path.dirname(__file__))
                icon_path = app_dir + "/res/mipmap-mdpi/trashcan_icon.png"
                icon_dsc = self.create_icon_dsc(icon_path)
                mode_icon.set_src(icon_dsc)
            except Exception as e:
                print(f"Failed to load trashcan icon: {e}")
                mode_icon.set_src(lv.SYMBOL.TRASH)
            label_text = "Uninstall Apps"
        else:
            # Show exit icon (exit uninstall mode)
            try:
                app_dir = os.path.dirname(os.path.dirname(__file__))
                icon_path = app_dir + "/res/mipmap-mdpi/exit_icon.png"
                icon_dsc = self.create_icon_dsc(icon_path)
                mode_icon.set_src(icon_dsc)
            except Exception as e:
                print(f"Failed to load exit icon: {e}")
                mode_icon.set_src(lv.SYMBOL.CLOSE)
            label_text = "Exit Uninstall"

        # ----- label (same as regular apps) -----------------------------
        mode_label = lv.label(mode_cont)
        mode_label.set_text(label_text)
        mode_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        mode_label.set_width(iconcont_width)
        mode_label.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        mode_label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

        # ----- events ---------------------------------------------------
        mode_cont.add_event_cb(
            lambda e: self._toggle_mode(),
            lv.EVENT.CLICKED, None)
        mode_cont.add_event_cb(
            lambda e, cont=mode_cont: self.focus_app_cont(cont),
            lv.EVENT.FOCUSED, None)
        mode_cont.add_event_cb(
            lambda e, cont=mode_cont: self.defocus_app_cont(cont),
            lv.EVENT.DEFOCUSED, None)

        if focusgroup:
            focusgroup.add_obj(mode_cont)

        # Store references
        self._mode_button = mode_cont
        self._mode_button_icon = mode_icon
        self._mode_button_label = mode_label

    # ------------------------------------------------------------------
    def _toggle_mode(self):
        """Toggle between launching and uninstall modes"""
        if self._current_mode == MODE_LAUNCHING:
            self._current_mode = MODE_UNINSTALL
        else:
            self._current_mode = MODE_LAUNCHING

        # Force UI rebuild to update mode button and app overlays
        # self._last_ui_built = False
        # # Trigger onResume to rebuild
        # screen = self.getContentView()
        # Force UI rebuild to update mode button and app overlays
        self._last_app_list = None  # Invalidate cache
        # Trigger onResume to rebuild with the active screen
        screen = lv.screen_active()
        if screen:
            self.onResume(screen)


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

        # Clear app widgets list
        self._app_widgets = []

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
            label.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)

            # Store widget info
            widget_info = {
                'app': app,
                'container': app_cont,
                'image': image,
                'label': label,
                'overlay': None,
                'x_label': None
            }
            self._app_widgets.append(widget_info)

            # ----- Add overlay if in uninstall mode --------------------
            if self._current_mode == MODE_UNINSTALL:
                is_builtin = PackageManager.is_builtin_app(app.fullname)

                # Create overlay
                overlay = lv.obj(app_cont)
                overlay.set_size(icon_size, icon_size)
                overlay.align(lv.ALIGN.TOP_MID, 0, 0)
                overlay.set_style_radius(8, 0)
                overlay.set_style_border_width(0, 0)
                widget_info['overlay'] = overlay

                if is_builtin:
                    # Grey out builtin apps
                    overlay.set_style_bg_color(lv.color_hex(0x808080), 0)
                    overlay.set_style_bg_opa(lv.OPA._60, 0)
                else:
                    # Red X for non-builtin apps
                    overlay.set_style_bg_color(lv.color_hex(0xE74C3C), 0)
                    overlay.set_style_bg_opa(lv.OPA._80, 0)
                    # Draw X
                    x_label = lv.label(overlay)
                    x_label.set_text(lv.SYMBOL.CLOSE)
                    x_label.set_style_text_color(lv.color_hex(0xFFFFFF), 0)
                    x_label.set_style_text_font(lv.font_montserrat_32, 0)
                    x_label.center()
                    widget_info['x_label'] = x_label

            # ----- events --------------------------------------------------
            app_cont.add_event_cb(
                lambda e, a=app: self._handle_app_click(a),
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
        # Add mode toggle button as last item in grid
        self._create_mode_button(screen, icon_size, label_height, iconcont_width, iconcont_height, focusgroup)

        # ------------------------------------------------------------------
        # 4. Store the new representation for the next resume
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

    # ------------------------------------------------------------------
    def _handle_app_click(self, app):
        """Handle app icon click based on current mode"""
        if self._current_mode == MODE_LAUNCHING:
            # Normal launch
            mpos.apps.start_app(app.fullname)
        elif self._current_mode == MODE_UNINSTALL:
            # Check if builtin
            is_builtin = PackageManager.is_builtin_app(app.fullname)
            if is_builtin:
                self._show_builtin_info_modal(app)
            else:
                self._show_uninstall_confirmation_modal(app)

    # ------------------------------------------------------------------
    def _show_uninstall_confirmation_modal(self, app):
        """Show confirmation modal for uninstalling an app"""
        # Get current focus group
        focus_group = lv.group_get_default()

        # Remove all app containers from focus group temporarily
        if focus_group:
            for widget_info in self._app_widgets:
                try:
                    focus_group.remove_obj(widget_info['container'])
                except:
                    pass
            # Also remove mode button
            if self._mode_button:
                try:
                    focus_group.remove_obj(self._mode_button)
                except:
                    pass

        # Create modal background on layer_top to ensure it's above everything
        try:
            parent = lv.layer_top()
        except:
            parent = lv.screen_active()

        modal_bg = lv.obj(parent)
        modal_bg.set_size(lv.pct(100), lv.pct(100))
        modal_bg.set_style_bg_color(lv.color_hex(0x000000), 0)
        modal_bg.set_style_bg_opa(lv.OPA._50, 0)
        modal_bg.set_style_border_width(0, 0)
        modal_bg.set_style_radius(0, 0)
        modal_bg.set_pos(0, 0)
        modal_bg.remove_flag(lv.obj.FLAG.SCROLLABLE)

        # Create modal dialog
        modal = lv.obj(modal_bg)
        modal.set_size(lv.pct(90), lv.pct(90))
        modal.center()
        modal.set_style_pad_all(20, 0)
        modal.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        modal.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)

        # Title
        title = lv.label(modal)
        title.set_text("Uninstall App?")
        title.set_style_text_font(lv.font_montserrat_20, 0)

        # Message
        msg = lv.label(modal)
        msg.set_text(f"Are you sure you want to uninstall {app.name}?")
        msg.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        msg.set_width(lv.pct(90))

        # Button container
        btn_cont = lv.obj(modal)
        btn_cont.set_size(lv.pct(100), lv.SIZE_CONTENT)
        btn_cont.set_style_border_width(0, 0)
        btn_cont.set_style_pad_all(10, 0)
        btn_cont.set_flex_flow(lv.FLEX_FLOW.ROW)
        btn_cont.set_flex_align(lv.FLEX_ALIGN.SPACE_EVENLY, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)

        # No button (add first so it gets focus by default - safer option)
        no_btn = lv.button(btn_cont)
        no_btn.set_size(lv.pct(40), 50)
        no_btn.add_event_cb(lambda e, m=modal_bg: self._close_modal(m), lv.EVENT.CLICKED, None)
        no_label = lv.label(no_btn)
        no_label.set_text("No")
        no_label.center()
        if focus_group:
            focus_group.add_obj(no_btn)

        # Yes button
        yes_btn = lv.button(btn_cont)
        yes_btn.set_size(lv.pct(40), 50)
        yes_btn.add_event_cb(lambda e, a=app, m=modal_bg: self._confirm_uninstall(a, m), lv.EVENT.CLICKED, None)
        yes_label = lv.label(yes_btn)
        yes_label.set_text("Yes")
        yes_label.center()
        if focus_group:
            focus_group.add_obj(yes_btn)

    # ------------------------------------------------------------------
    def _show_builtin_info_modal(self, app):
        """Show info modal explaining builtin apps cannot be uninstalled"""
        # Get current focus group
        focus_group = lv.group_get_default()

        # Remove all app containers from focus group temporarily
        if focus_group:
            for widget_info in self._app_widgets:
                try:
                    focus_group.remove_obj(widget_info['container'])
                except:
                    pass
            # Also remove mode button
            if self._mode_button:
                try:
                    focus_group.remove_obj(self._mode_button)
                except:
                    pass

        # Create modal background on layer_top to ensure it's above everything
        try:
            parent = lv.layer_top()
        except:
            parent = lv.screen_active()

        modal_bg = lv.obj(parent)
        modal_bg.set_size(lv.pct(100), lv.pct(100))
        modal_bg.set_style_bg_color(lv.color_hex(0x000000), 0)
        modal_bg.set_style_bg_opa(lv.OPA._50, 0)
        modal_bg.set_style_border_width(0, 0)
        modal_bg.set_style_radius(0, 0)
        modal_bg.set_pos(0, 0)
        modal_bg.remove_flag(lv.obj.FLAG.SCROLLABLE)

        # Create modal dialog
        modal = lv.obj(modal_bg)
        modal.set_size(lv.pct(90), lv.pct(90))
        modal.center()
        modal.set_style_pad_all(20, 0)
        modal.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        modal.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)

        # Title
        title = lv.label(modal)
        title.set_text("Cannot Uninstall")
        title.set_style_text_font(lv.font_montserrat_20, 0)

        # Message
        msg = lv.label(modal)
        msg.set_text(f"{app.name} is a built-in app\nand cannot be uninstalled.")
        msg.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
        msg.set_width(lv.pct(90))

        # OK button
        ok_btn = lv.button(modal)
        ok_btn.set_size(lv.pct(50), 50)
        ok_btn.add_event_cb(lambda e, m=modal_bg: self._close_modal(m), lv.EVENT.CLICKED, None)
        ok_label = lv.label(ok_btn)
        ok_label.set_text("OK")
        ok_label.center()
        if focus_group:
            focus_group.add_obj(ok_btn)

    # ------------------------------------------------------------------
    def _close_modal(self, modal_bg):
        """Close and delete modal and restore focus group"""
        # Get focus group
        focus_group = lv.group_get_default()

        # Delete modal (this will remove modal buttons from group)
        modal_bg.delete()

        # Re-add all app containers and mode button back to focus group
        if focus_group:
            for widget_info in self._app_widgets:
                try:
                    focus_group.add_obj(widget_info['container'])
                except:
                    pass
            # Re-add mode button
            if self._mode_button:
                try:
                    focus_group.add_obj(self._mode_button)
                except:
                    pass

    # ------------------------------------------------------------------
    def _confirm_uninstall(self, app, modal_bg):
        """Actually uninstall the app"""
        self._close_modal(modal_bg)
        # Run uninstall in thread to avoid blocking UI
        try:
            _thread.stack_size(mpos.apps.good_stack_size())
            _thread.start_new_thread(self._uninstall_app_thread, (app.fullname,))
        except Exception as e:
            print(f"Could not start uninstall thread: {e}")

    # ------------------------------------------------------------------
    def _uninstall_app_thread(self, app_fullname):
        """Thread function to uninstall app"""
        print(f"Uninstalling app: {app_fullname}")
        try:
            PackageManager.uninstall_app(app_fullname)
            print(f"Successfully uninstalled {app_fullname}")
            # Note: The app list will be refreshed when launcher resumes
        except Exception as e:
            print(f"Error uninstalling {app_fullname}: {e}")
