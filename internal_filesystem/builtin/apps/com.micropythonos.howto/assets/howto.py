from mpos import Activity, SharedPreferences

class HowTo(Activity):

    appname = "com.micropythonos.howto"

    dontshow_checkbox = None
    prefs = None
    autostart_enabled = None

    def onCreate(self):
        screen = lv.obj()
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        label = lv.label(screen)
        label.set_width(lv.pct(100))
        touchhelp = "swipe from the left edge to go back and from the top edge to open the menu."
        label.set_text(f'''
Welcome!

This app will explain how to move around in MicroPythonOS.

If you're on a touch screen, {touchhelp}

If you've got 3 buttons, one is PREVIOUS, one is ENTER and one is NEXT. To go back, press PREVIOUS and NEXT together.

If you've got 2 buttons, one is PREVIOUS, the other is NEXT. To ENTER, press both at the same time. To go back, long-press PREVIOUS.
        ''')
        label.set_long_mode(lv.label.LONG_MODE.WRAP)

        self.dontshow_checkbox = lv.checkbox(screen)
        self.dontshow_checkbox.set_text("Don't show again")

        closebutton = lv.button(screen)
        closebutton.add_event_cb(lambda *args: self.finish(), lv.EVENT.CLICKED, None)
        closelabel = lv.label(closebutton)
        closelabel.set_text("Close")

        self.setContentView(screen)

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
