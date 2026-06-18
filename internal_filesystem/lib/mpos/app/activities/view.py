import logging

import lvgl as lv

from ..activity import Activity
from ...content.app_manager import AppManager

logger = logging.getLogger(__name__)

# Number of bytes to show from the beginning of a file.
_MAX_PREVIEW_BYTES = 512


class ViewActivity(Activity):
    def __init__(self):
        super().__init__()
        self._title_label = None
        self._content_label = None

    def _read_preview(self, path):
        """Read the first bytes of a file and return them as a printable string."""
        try:
            with open(path, "rb") as f:
                data = f.read(_MAX_PREVIEW_BYTES)
            return data.decode("utf-8", "replace")
        except Exception as e:
            if __debug__: logger.debug("ViewActivity could not read %s: %s", path, e)
            return "(could not read file: %s)" % e

    def _build_screen(self):
        screen = lv.obj()
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        screen.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        screen.set_style_pad_all(10, lv.PART.MAIN)
        screen.set_style_pad_gap(6, lv.PART.MAIN)

        # Get content from intent (prefer extras.url, fallback to data)
        target = self.getIntent().extras.get("url", self.getIntent().data or "No content")
        preview = self._read_preview(target) if self.getIntent().data and isinstance(self.getIntent().data, str) else ""

        self._title_label = lv.label(screen)
        self._title_label.set_text("Viewing:\n{}".format(target))
        self._title_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        self._title_label.set_width(lv.pct(90))

        self._content_label = lv.label(screen)
        self._content_label.set_text(preview)
        self._content_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        self._content_label.set_width(lv.pct(90))
        self._content_label.set_style_text_font(lv.font_montserrat_14, lv.PART.MAIN)

        return screen

    def onCreate(self):
        self.setContentView(self._build_screen())

    def onStart(self, screen):
        target = self.getIntent().extras.get("url", self.getIntent().data or "No content")
        preview = self._read_preview(target) if self.getIntent().data and isinstance(self.getIntent().data, str) else ""
        if self._title_label:
            self._title_label.set_text("Viewing:\n{}".format(target))
        if self._content_label:
            self._content_label.set_text(preview)

    def onStop(self, screen):
        if __debug__: logger.debug("ViewActivity stopped")


AppManager.register_activity("view", ViewActivity)
