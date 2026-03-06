from mpos import Activity

class FirstRun(Activity):

    def onCreate(self):
        screen = lv.obj()
        label = lv.label(screen)
        label.align(lv.ALIGN.TOP_LEFT, 0, 0)
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
        self.setContentView(screen)
