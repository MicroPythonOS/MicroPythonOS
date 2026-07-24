import lvgl as lv

from mpos import Activity

class ErrorDelayed(Activity):

    def onCreate(self):
        screen = lv.obj()
        button = lv.button(screen)
        button.add_event_cb(self.button_callback, lv.EVENT.CLICKED, None)
        label = lv.label(button)
        label.set_text('Hello World!')
        label.center()
        self.setContentView(screen)

    def onResume(self, screen):
        lv.timer_create(self.timer_cb, 5000, None)

    def button_callback(self, event):
        print("Button callback still works, even after a delayed error - no problem!")

    def timer_cb(self, timer):
        print("Triggering intentional error/crash/exception")
        lv.this_doesnt_exist() # should fail here
