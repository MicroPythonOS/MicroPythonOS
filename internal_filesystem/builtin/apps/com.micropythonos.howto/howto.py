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
        # Only actionable controls should go into the focus group.
        preamble = "Navigate"
        self._add_label(screen, preamble, is_header=True)

        buttonhelp_items = [
            "Joystick: move. Btns: ENTER/BACK.",
            "3 buttons: PREV/ENTER/NEXT.",
            "2 buttons: PREV/NEXT.",
        ]
        buttonhelp_intro = "Use buttons to navigate:"
        touchhelp = "Left/back. Menu top."
        from mpos import InputManager
        try:
            is_k10 = DeviceInfo.get_hardware_id() == "unihiker_k10"
        except Exception:
            is_k10 = False
        if InputManager.has_pointer():
            self._add_label(screen, touchhelp)
        elif is_k10:
            self._add_label(screen, "K")
            self._add_label(screen, "- B: next.")
            self._add_label(screen, "- A: select.")
        else:
            self._add_label(screen, buttonhelp_intro)
            for item in buttonhelp_items:
                self._add_label(screen, f"• {item}")

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

    def _add_label(self, parent, text, is_header=False):
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

        if self.closebutton:
            try:
                lv.group_focus_obj(self.closebutton)
            except Exception:
                pass

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
