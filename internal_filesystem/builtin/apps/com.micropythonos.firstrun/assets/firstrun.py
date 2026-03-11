from mpos import Activity

class FirstRun(Activity):

    dontshow_checkbox = None

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

    def onPause(self, screen):
        checked = self.dontshow_checkbox.get_state() & lv.STATE.CHECKED
        if checked:
            print("TODO: make sure this doesn't appear again")
