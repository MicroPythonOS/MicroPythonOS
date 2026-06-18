import logging

logger = logging.getLogger(__name__)

import lvgl as lv
import os

from ..app.activity import Activity
from .keyboard import MposKeyboard


class RenameActivity(Activity):

    def onCreate(self):
        self._path = self.getIntent().extras.get("path")
        screen = lv.obj()
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        screen.set_style_pad_all(0, 0)
        screen.set_style_pad_gap(0, 0)

        old_name = self._path.rstrip("/").split("/")[-1]
        self._ta = lv.textarea(screen)
        self._ta.set_text(old_name)
        self._ta.set_width(lv.pct(100))
        self._ta.set_style_pad_all(6, lv.PART.MAIN)
        self._ta.set_one_line(True)

        self._keyboard = MposKeyboard(screen)
        self._keyboard.set_style_pad_all(0, 0)
        self._keyboard.set_textarea(self._ta)
        self._keyboard.add_event_cb(lambda e: self._do_rename(), lv.EVENT.READY, None)

        btn_row = lv.obj(screen)
        btn_row.set_width(lv.pct(100))
        btn_row.set_height(lv.SIZE_CONTENT)
        btn_row.set_style_pad_all(0, 0)
        btn_row.set_style_pad_gap(0, 0)
        btn_row.set_flex_flow(lv.FLEX_FLOW.ROW)
        btn_row.set_flex_align(lv.FLEX_ALIGN.SPACE_EVENLY, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)

        cancel_btn = lv.button(btn_row)
        lv.label(cancel_btn).set_text("Cancel")
        cancel_btn.add_event_cb(lambda e: self.finish(), lv.EVENT.CLICKED, None)

        confirm_btn = lv.button(btn_row)
        lv.label(confirm_btn).set_text("Confirm")
        confirm_btn.add_event_cb(lambda e: self._do_rename(), lv.EVENT.CLICKED, None)

        self.setContentView(screen)

    def _do_rename(self):
        new_name = self._ta.get_text()
        if not new_name:
            return
        dir_part = "/".join(self._path.rstrip("/").split("/")[:-1])
        new_path = "{}/{}".format(dir_part, new_name)
        try:
            os.rename(self._path, new_path)
            if __debug__: logger.debug("RenameActivity: renamed %s -> %s", self._path, new_path)
            self.setResult(True, {"new_path": new_path})
        except OSError as e:
            logger.error("RenameActivity: rename error %s -> %s: %s", self._path, new_path, e)
            self.setResult(False, {"error": str(e)})
        self.finish()
