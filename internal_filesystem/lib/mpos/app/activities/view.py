import logging

import lvgl as lv

from ..activity import Activity
from ...content.app_manager import AppManager

logger = logging.getLogger(__name__)


class ViewActivity(Activity):
    def __init__(self):
        super().__init__()
        self._content_label = None

    def onCreate(self):
        screen = lv.obj()
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        screen.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        screen.set_style_pad_all(10, lv.PART.MAIN)

        # Get content from intent (prefer extras.url, fallback to data)
        content = self.getIntent().extras.get("url", self.getIntent().data or "No content")

        self._content_label = lv.label(screen)
        self._content_label.set_text("Viewing:\n{}".format(content))
        self._content_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        self._content_label.set_width(lv.pct(90))
        self.setContentView(screen)

    def onStart(self, screen):
        content = self.getIntent().extras.get("url", self.getIntent().data or "No content")
        if self._content_label:
            self._content_label.set_text("Viewing:\n{}".format(content))

    def onStop(self, screen):
        if __debug__: logger.debug("ViewActivity stopped")


AppManager.register_activity("view", ViewActivity)
