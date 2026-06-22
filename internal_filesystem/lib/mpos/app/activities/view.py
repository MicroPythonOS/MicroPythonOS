import logging

import lvgl as lv

from ..activity import Activity
from ...content.app_manager import AppManager

logger = logging.getLogger(__name__)

# Number of bytes to show from the beginning of a file.
_MAX_PREVIEW_BYTES = 512

# Threshold (in percent) of non-whitespace control characters used to
# classify unknown data as binary.
_BINARY_CONTROL_THRESHOLD = 8

# Friendly hints for files that end up in the generic viewer only because
# no file-type-specific handler is installed for them.
_BINARY_HINTS = {
    (".png", ".jpg", ".jpeg", ".raw", ".bmp"):
        "This is an image file.\nInstall an image viewer to open it.",
    (".raw"):
        "This might be an image file.\Try an image viewer to open it.",
    (".wav",):
        "This is an audio file.\nInstall a music/audio player to open it.",
}

_BINARY_HINT_BY_EXT = {}
for _exts, _msg in _BINARY_HINTS.items():
    for _ext in _exts:
        _BINARY_HINT_BY_EXT[_ext] = _msg


class ViewActivity(Activity):
    def __init__(self):
        super().__init__()
        self._title_label = None
        self._content_label = None

    def _read_preview(self, path):
        """Read the first bytes of a file and return a printable preview or hint."""
        try:
            with open(path, "rb") as f:
                data = f.read(_MAX_PREVIEW_BYTES)
        except Exception as e:
            if __debug__: logger.debug("ViewActivity could not read %s: %s", path, e)
            return "(could not read file: %s)" % repr(e)

        if self._path_has_binary_extension(path) or self._is_binary(data):
            return self._binary_hint_for_path(path)

        try:
            return data.decode("utf-8", "replace")
        except Exception as e:
            if __debug__: logger.debug("ViewActivity could not decode %s: %s", path, e)
            return self._binary_hint_for_path(path)

    @staticmethod
    def _is_binary(data):
        """Return True if data looks like binary rather than text."""
        if not data:
            return False
        if b"\x00" in data:
            return True
        non_text = 0
        for byte in data:
            if byte < 32 and byte not in (9, 10, 13):
                non_text += 1
        return (non_text * 100) // len(data) > _BINARY_CONTROL_THRESHOLD

    @staticmethod
    def _path_has_binary_extension(path):
        """Return True if the path ends with a known binary extension."""
        lower_path = path.lower()
        for ext in _BINARY_HINT_BY_EXT:
            if lower_path.endswith(ext):
                return True
        return False

    @staticmethod
    def _binary_hint_for_path(path):
        """Return a human-friendly hint for a binary file path."""
        lower_path = path.lower()
        for ext, msg in _BINARY_HINT_BY_EXT.items():
            if lower_path.endswith(ext):
                return msg
        return "This is a binary file.\nIt cannot be previewed."

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
