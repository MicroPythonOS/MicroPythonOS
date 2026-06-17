import lvgl as lv

from mpos import Activity

from confetti import Confetti

class ConfettiApp(Activity):

    ASSET_PATH = "M:builtin/res/emojis/32x32/"
    ICON_PATH = "M:apps/com.micropythonos.confetti/"

    confetti = None

    def onCreate(self):
        main_screen = lv.obj()
        import sys
        self.confetti = Confetti(main_screen, self.ICON_PATH, self.ASSET_PATH, sys.maxsize)
        print("created ", self.confetti)
        self.setContentView(main_screen)

    def onResume(self, screen):
        print("onResume")
        self.confetti.start()

    def onPause(self, screen):
        self.confetti.stop()
