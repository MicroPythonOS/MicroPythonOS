from mpos import Activity, SharedPreferences

class HowTo(Activity):

    appname = "com.micropythonos.howto"

    dontshow_checkbox = None
    prefs = None
    autostart_enabled = None

    def onCreate(self):
        screen = lv.obj()
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        # Make the screen focusable so it can be scrolled with the arrow keys
        focusgroup = lv.group_get_default()
        if focusgroup:
            focusgroup.add_obj(screen)
        preamble = "How to Navigate"
        self._add_label(screen, preamble, is_header=True)

        buttonhelp_intro = "As you don't have a touch screen, you need to use the buttons to navigate:"
        buttonhelp_items = [
            "If you have a joystick and at least 2 buttons, then use the joystick to move around. Use one of the buttons to ENTER and another to go BACK.",
            "If you have 3 buttons, then one is PREVIOUS, one is ENTER and one is NEXT. To go back, press PREVIOUS and NEXT together.",
            "If you have just 2 buttons, then one is PREVIOUS, the other is NEXT. To ENTER, press both at the same time. To go back, long-press the PREVIOUS button.",
        ]
        touchhelp = "Swipe from the left edge to go back and from the top edge to open the menu."
        from mpos import InputManager
        if InputManager.has_pointer():
            self._add_label(screen, touchhelp)
        else:
            self._add_label(screen, buttonhelp_intro)
            for item in buttonhelp_items:
                self._add_label(screen, f"• {item}")

        self.dontshow_checkbox = lv.checkbox(screen)
        self.dontshow_checkbox.set_text("Don't show again")

        closebutton = lv.button(screen)
        closebutton.add_event_cb(lambda *args: self.finish(), lv.EVENT.CLICKED, None)
        closelabel = lv.label(closebutton)
        closelabel.set_text("Close")

        self.setContentView(screen)

    @staticmethod
    def _focus_obj(event):
        target = event.get_target_obj()
        target.set_style_border_color(lv.theme_get_color_primary(None), lv.PART.MAIN)
        target.set_style_border_width(1, lv.PART.MAIN)
        target.scroll_to_view(True)

    @staticmethod
    def _defocus_obj(event):
        target = event.get_target_obj()
        target.set_style_border_width(0, lv.PART.MAIN)

    def _add_label(self, parent, text, is_header=False):
        label = lv.label(parent)
        label.set_width(lv.pct(100))
        label.set_text(text)
        label.set_long_mode(lv.label.LONG_MODE.WRAP)
        label.add_event_cb(self._focus_obj, lv.EVENT.FOCUSED, None)
        label.add_event_cb(self._defocus_obj, lv.EVENT.DEFOCUSED, None)
        focusgroup = lv.group_get_default()
        if focusgroup:
            focusgroup.add_obj(label)
        if is_header:
            label.set_style_text_font(lv.font_montserrat_24, lv.PART.MAIN)
            label.set_style_margin_bottom(4, lv.PART.MAIN)
        else:
            label.set_style_text_font(lv.font_montserrat_14, lv.PART.MAIN)
            label.set_style_margin_bottom(2, lv.PART.MAIN)
        return label

    def onResume(self, screen):
        # Autostart can only be disabled if nothing was enabled or if this app was enabled
        self.prefs = SharedPreferences("com.micropythonos.settings")
        auto_start_app_early = self.prefs.get_string("auto_start_app_early")
        print(f"auto_start_app_early: {auto_start_app_early}")
        if auto_start_app_early is None or auto_start_app_early == self.appname: # empty also means autostart because then it's the default
            self.dontshow_checkbox.remove_state(lv.STATE.CHECKED)
        else:
            self.dontshow_checkbox.add_state(lv.STATE.CHECKED)

    def onPause(self, screen):
        checked = self.dontshow_checkbox.get_state() & lv.STATE.CHECKED
        print("Removing this app from autostart")
        editor = self.prefs.edit()
        if checked:
            editor.put_string("auto_start_app_early", "") # None might result in the OS starting it, empty string means explictly don't start it
        else:
            editor.put_string("auto_start_app_early", self.appname)
        editor.commit()
