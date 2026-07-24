import lvgl as lv

from mpos import Activity

class ErrorResume(Activity):

    def onCreate(self):
        screen = lv.obj()
        button = lv.button(screen)
        button.add_event_cb(self.button_callback, lv.EVENT.CLICKED, None)
        label = lv.label(button)
        label.set_text('Hello World!')
        label.center()
        self.setContentView(screen)

    def onResume(self, screen):
        lv.this_should_fail()

    def button_callback(self, event):
        print("Button callback still works, even after a onResume error!")


