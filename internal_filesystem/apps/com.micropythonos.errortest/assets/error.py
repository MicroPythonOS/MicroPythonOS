import lvgl as lv
from mpos import ActivityDoesntExist  # noqa: F401 - should fail here!


class Error(Activity):

    def onCreate(self):
        screen = lv.obj()
        label = lv.label(screen)
        label.set_text('Hello World!')
        label.center()
        self.setContentView(screen)
