from mpos import Activity

"""

"""

import time
import os
import json

try:
    import lvgl as lv
except ImportError:
    pass

from mpos import Activity, MposKeyboard

TMP = "/tmp/cmd.json"


def run_cmd_json(cmd):
    rc = os.system(cmd + " > " + TMP)
    if rc != 0:
        raise RuntimeError("command failed")

    with open(TMP, "r") as f:
        data = f.read().strip()

    return json.loads(data)

def dbus_json(cmd):
    return run_cmd_json("sudo /home/mobian/g/MicroPythonOS/phone.py " + cmd)

class CellularManager:
    def init(self):
        v = dbus_json("loc_on")
    
    def poll(self):
        v = dbus_json("signal")
        print(v)
        self.signal = v

cm = CellularManager()

# ------------------------------------------------------------
#
# ------------------------------------------------------------

class Main(Activity):

    def __init__(self):
        super().__init__()

     # --------------------

    def onCreate(self):
        self.screen = lv.obj()
        #self.screen.remove_flag(lv.obj.FLAG.SCROLLABLE)

        # Top labels
        self.lbl_time = lv.label(self.screen)
        self.lbl_time.set_style_text_font(lv.font_montserrat_34, 0)
        self.lbl_time.set_text("Startup...")
        self.lbl_time.align(lv.ALIGN.TOP_LEFT, 6, 22)

        self.lbl_date = lv.label(self.screen)
        self.lbl_date.set_style_text_font(lv.font_montserrat_20, 0)
        self.lbl_date.align_to(self.lbl_time, lv.ALIGN.OUT_BOTTOM_LEFT, 0, 5)
        self.lbl_date.set_text("(details here?")

        self.lbl_month = lv.label(self.screen)
        self.lbl_month.set_style_text_font(lv.font_montserrat_20, 0)
        self.lbl_month.align(lv.ALIGN.TOP_RIGHT, -6, 22)

        self.number = lv.textarea(self.screen)
        #self.number.set_accepted_chars("0123456789")
        self.number.set_one_line(True)
        self.number.set_style_text_font(lv.font_montserrat_34, 0)
        self.number.align_to(self.lbl_date, lv.ALIGN.OUT_BOTTOM_LEFT, 0, 12)

        self.call = lv.button(self.screen)
        self.call.align_to(self.number, lv.ALIGN.OUT_RIGHT_MID, 10, 0)

        l = lv.label(self.call)
        l.set_text("Call")
	l.center()


        kb = lv.keyboard(self.screen)
        kb.set_textarea(self.number)
        kb.set_size(lv.pct(100), lv.pct(33))

        self.setContentView(self.screen)
        cm.init()

    def onResume(self, screen):
        self.timer = lv.timer_create(self.tick, 60000, None)
        self.tick(0)

    def onPause(self, screen):
        if self.timer:
            self.timer.delete()
            self.timer = None

    # --------------------

    def tick(self, t):
        now = time.localtime()
        y, m, d = now[0], now[1], now[2]
        hh, mm, ss = now[3], now[4], now[5]

        self.lbl_month.set_text("busy")

        cm.poll()
        s = ""
        s += cm.signal["OperatorName"] + "\n"
        s += "RegistrationState %d\n" % cm.signal["RegistrationState"]
        s += "State %d " % cm.signal["State"]
        sq, re = cm.signal["SignalQuality"]
        s += "Signal %d\n" % sq

        self.lbl_month.set_text(s)
        self.lbl_time.set_text("%02d:%02d" % (hh, mm))
        s = ""
        self.lbl_date.set_text("%04d-%02d-%02d %s" % (y, m, d, s))
        

    # --------------------


