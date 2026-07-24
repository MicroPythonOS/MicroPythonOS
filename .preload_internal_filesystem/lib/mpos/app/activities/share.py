import logging

import lvgl as lv

from ..activity import Activity
from ...content.app_manager import AppManager

logger = logging.getLogger(__name__)


class ShareActivity(Activity):
    def __init__(self):
        super().__init__()

    def onCreate(self):
        screen = lv.obj()
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        screen.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        screen.set_style_pad_all(10, lv.PART.MAIN)

        # Get text from intent (prefer extras.text, fallback to data)
        text = self.getIntent().extras.get("text", self.getIntent().data or "No text")

        label = lv.label(screen)
        label.set_text("Share:\n{}".format(text))
        label.set_long_mode(lv.label.LONG_MODE.WRAP)
        label.set_width(lv.pct(90))

        btn = lv.button(screen)
        btn_label = lv.label(btn)
        btn_label.set_text("Share")
        btn_label.center()
        btn.add_event_cb(lambda e: self._share_content(text), lv.EVENT.CLICKED, None)

        self.setContentView(screen)

    def _share_content(self, text):
        if __debug__: logger.debug("Sharing: %s", text)
        self.finish()

    def onStop(self, screen):
        if __debug__: logger.debug("ShareActivity stopped")


AppManager.register_activity("share", ShareActivity)
