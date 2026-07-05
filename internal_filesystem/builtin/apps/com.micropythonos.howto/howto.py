import logging

from mpos import Activity, SharedPreferences, DisplayMetrics, add_focus_border
import lvgl as lv

logger = logging.getLogger(__name__)

class HowTo(Activity):

    appname = "com.micropythonos.howto"

    dontshow_checkbox = None
    prefs = None

    def onCreate(self):
        screen = lv.obj()
        screen.set_style_border_width(0, lv.PART.MAIN)
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        screen.set_style_pad_all(DisplayMetrics.pct_of_width(5), lv.PART.MAIN)
        # Children (labels, checkbox, button) are auto-added to the default group;
        # the screen itself must NOT be in the group, otherwise move_focus_direction
        # cannot find widgets below it (the fullscreen rect blocks spatial navigation).
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
        closebutton.add_event_cb(self._on_long_press, lv.EVENT.LONG_PRESSED, None)
        closelabel = lv.label(closebutton)
        closelabel.set_text("Close")

        self.setContentView(screen)

    def _add_label(self, parent, text, is_header=False):
        label = lv.label(parent)
        label.set_width(lv.pct(100))
        label.set_text(text)
        label.set_long_mode(lv.label.LONG_MODE.WRAP)
        add_focus_border(label)
        lv.group_get_default().add_obj(label)
        if is_header:
            label.set_style_text_font(lv.font_montserrat_24, lv.PART.MAIN)
            label.set_style_margin_bottom(4, lv.PART.MAIN)
        else:
            label.set_style_text_font(lv.font_montserrat_14, lv.PART.MAIN)
            label.set_style_margin_bottom(2, lv.PART.MAIN)
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
