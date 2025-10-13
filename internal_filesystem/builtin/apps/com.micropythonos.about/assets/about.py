from mpos.apps import Activity

import mpos.info
import sys

class About(Activity):

    def onCreate(self):
        screen = lv.obj()
        screen.set_style_border_width(0, 0)
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        screen.set_style_pad_all(mpos.ui.pct_of_display_width(2), 0)
        label0 = lv.label(screen)
        label0.set_text(f"Hardware ID: {mpos.info.get_hardware_id()}")
        label1 = lv.label(screen)
        label1.set_text(f"MicroPythonOS version: {mpos.info.CURRENT_OS_VERSION}")
        label2 = lv.label(screen)
        label2.set_text(f"sys.version: {sys.version}")
        label3 = lv.label(screen)
        label3.set_text(f"sys.implementation: {sys.implementation}")
        label4 = lv.label(screen)
        label4.set_text(f"sys.platform: {sys.platform}")
        try:
            print("Trying to find out additional board info, not available on every platform...")
            import machine
            label5 = lv.label(screen)
            label5.set_text("") # otherwise it will show the default "Text" if there's an exception below
            label5.set_text(f"machine.freq: {machine.freq()}")
            label6 = lv.label(screen)
            label6.set_text(f"machine.unique_id(): {machine.unique_id()}")
            label7 = lv.label(screen)
            label7.set_text(f"machine.wake_reason(): {machine.wake_reason()}")
            label8 = lv.label(screen)
            label8.set_text(f"machine.reset_cause(): {machine.reset_cause()}")
        except Exception as e:
            print(f"Additional board info got exception: {e}")
        self.setContentView(screen)
