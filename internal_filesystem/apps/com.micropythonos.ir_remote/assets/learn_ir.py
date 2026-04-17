import lvgl as lv

from mpos import Activity

class LearnIR(Activity):

    status = None
    screen = None

    def onCreate(self):
        print("learn_ir.py")
        self.screen = lv.obj()
        self.status = lv.label(self.screen)        
        self.setContentView(self.screen)
