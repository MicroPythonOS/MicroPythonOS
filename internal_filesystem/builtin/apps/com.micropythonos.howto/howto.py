import logging

from mpos import Activity, DeviceInfo, SharedPreferences, DisplayMetrics, add_focus_highlight
import lvgl as lv

logger = logging.getLogger(__name__)

class HowTo(Activity):

    appname = "com.micropythonos.howto"

    dontshow_checkbox = None
    closebutton = None
    prefs = None

    def onCreate(self):
        screen = lv.obj()
        screen.set_style_border_width(0, lv.PART.MAIN)
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        screen.set_style_pad_all(DisplayMetrics.pct_of_width(5), lv.PART.MAIN)
        self._add_label(
            screen,
            "How to Navigate",
            is_header=True,
            focusable=DeviceInfo.get_hardware_id() != "unihiker_k10",
        )

        buttonhelp_items = [
            (
                "If you have a joystick and at least 2 buttons, then use the joystick "
                "to move around. Use one of the buttons to ENTER and another to go BACK."
            ),
            (
                "If you have 3 buttons, then one is PREVIOUS, one is ENTER and one "
                "is NEXT. To go back, press PREVIOUS and NEXT together."
            ),
            (
                "If you have just 2 buttons, then one is PREVIOUS, the other is NEXT. "
                "To ENTER, press both at the same time. To go back, long-press the "
                "PREVIOUS button."
            ),
        ]
        buttonhelp_intro = "As you don't have a touch screen, you need to use the buttons to navigate:"
        touchhelp = (
            "Swipe from the left edge to go back. Swipe down from the top edge to "
            "open the menu."
        )
        from mpos import InputManager
        if DeviceInfo.get_hardware_id() == "unihiker_k10":
            # K10 uses B as its only NEXT key, so static help text stays out of
            # its focus cycle and must remain compact enough to fit on one screen.
            self._add_label(screen, "Open a drop-down: B next. Hold B: previous.", focusable=False)
            self._add_label(screen, "A: select. Hold A: cancel or go back.", focusable=False)
        elif InputManager.has_pointer():
            self._add_label(screen, touchhelp)
        else:
            self._add_label(screen, buttonhelp_intro)
            for item in buttonhelp_items:
                self._add_label(screen, f"• {item}")

        # Register the only actionable controls for keypad navigation.
        self.dontshow_checkbox = lv.checkbox(screen)
        self.dontshow_checkbox.set_text("Don't show again")
        add_focus_highlight(self.dontshow_checkbox)

        closebutton = lv.button(screen)
        self.closebutton = closebutton
        closebutton.add_event_cb(lambda *args: self.finish(), lv.EVENT.CLICKED, None)
        closebutton.add_event_cb(self._on_long_press, lv.EVENT.LONG_PRESSED, None)
        closelabel = lv.label(closebutton)
        closelabel.set_text("Close")
        add_focus_highlight(closebutton)

        self.setContentView(screen)

    def _add_label(self, parent, text, is_header=False, focusable=True):
        label = lv.label(parent)
        label.set_width(lv.pct(100))
        label.set_text(text)
        label.set_long_mode(lv.label.LONG_MODE.WRAP)
        if is_header:
            label.set_style_text_font(lv.font_montserrat_24, lv.PART.MAIN)
            label.set_style_margin_bottom(4, lv.PART.MAIN)
        else:
            label.set_style_text_font(lv.font_montserrat_14, lv.PART.MAIN)
            label.set_style_margin_bottom(2, lv.PART.MAIN)
        if focusable:
            add_focus_highlight(label)
        return label

    def _on_long_press(self, event):
        if __debug__: logger.debug("long press detected")

    def onResume(self, screen):
        # Autostart can only be disabled if nothing was enabled or if this app was enabled
        self.prefs = SharedPreferences("com.micropythonos.settings")
        auto_start_app_early = self.prefs.get_string("auto_start_app_early")
        if __debug__: logger.debug("auto_start_app_early: %s", auto_start_app_early)
        if auto_start_app_early is None or auto_start_app_early == self.appname: # empty also means autostart because then it's the default
            self.dontshow_checkbox.remove_state(lv.STATE.CHECKED)
        else:
            self.dontshow_checkbox.add_state(lv.STATE.CHECKED)

        if DeviceInfo.get_hardware_id() == "unihiker_k10" and self.closebutton:
            # Make the exit action immediately reachable on the two-button K10.
            lv.group_focus_obj(self.closebutton)

    def onPause(self, screen):
        if __debug__: logger.debug("howto app onPause called")
        checked = self.dontshow_checkbox.get_state() & lv.STATE.CHECKED
        if checked:
            new_value = "" # None might result in the OS starting it, empty string means explictly don't start it
        else:
            new_value = self.appname

        old_value = self.prefs.get_string("auto_start_app_early", "com.micropythonos.howto") # same default as lib/mpos/main.py
        if old_value == new_value:
            return

        if __debug__: logger.debug("removing app from autostart")
        editor = self.prefs.edit()
        editor.put_string("auto_start_app_early", new_value)
        editor.commit()
