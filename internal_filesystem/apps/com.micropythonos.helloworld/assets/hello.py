from mpos import Activity

class Hello(Activity):

    def onCreate(self):
        screen = lv.obj()
        label = lv.label(screen)
        label.set_text('Hello World!')
        label.center()
        self.setContentView(screen)
