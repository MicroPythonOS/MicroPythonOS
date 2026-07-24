import logging

import lvgl as lv

from mpos import Activity

logger = logging.getLogger(__name__)


class ResetIntoBootloader(Activity):

    message = "Bootloader mode activated.\nYou can now install firmware over USB.\n\nReset the device to cancel."

    def onCreate(self):
        logger.info(self.message)
        screen = lv.obj()
        label = lv.label(screen)
        label.set_text(self.message)
        label.center()
        self.setContentView(screen)

    def onResume(self, screen):
        if __debug__: logger.debug("scheduling bootloader start")
        lv.timer_create(self.start_bootloader, 1000, None).set_repeat_count(1)

    def start_bootloader(self, timer):
        try:
            import machine
            machine.bootloader()
        except Exception as e:
            logger.error("could not reset into bootloader: %s", e)
