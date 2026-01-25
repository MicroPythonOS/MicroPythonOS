import time
import random
import lvgl as lv

from mpos import Activity

from confetti import Confetti

class ConfettiApp(Activity):

    ASSET_PATH = "M:apps/com.micropythonos.confetti/res/drawable-mdpi/"
    ICON_PATH = "M:apps/com.lightningpiggy.displaywallet/res/mipmap-mdpi/"
    confetti_duration = 60 * 1000

    confetti = None

    def onCreate(self):
        main_screen = lv.obj()
        self.confetti = Confetti(main_screen, self.ICON_PATH, self.ASSET_PATH, self.confetti_duration)
        print("created ", self.confetti)
        self.setContentView(main_screen)

    def onResume(self, screen):
        print("onResume")
        self.confetti.start()

    def onPause(self, screen):
        self.confetti.stop()
