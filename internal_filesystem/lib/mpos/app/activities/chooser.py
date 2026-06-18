import logging

import lvgl as lv

from ..activity import Activity

# Chooser doesn't handle an action — it shows handlers
# → No registration needed

from ...content.app_manager import AppManager

logger = logging.getLogger(__name__)


class ChooserActivity(Activity):
    def __init__(self):
        super().__init__()

    def onCreate(self):
        screen = lv.obj()
        screen.set_flex_flow(lv.FLEX_FLOW.COLUMN)
        screen.set_flex_align(lv.FLEX_ALIGN.START, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        screen.set_style_pad_all(10, lv.PART.MAIN)

        # Get handlers from intent extras
        original_intent = self.getIntent().extras.get("original_intent")
        handlers = self.getIntent().extras.get("handlers", [])
        self._result_callback = self.getIntent().extras.get("result_callback")

        title = lv.label(screen)
        title.set_text("Open with")
        title.set_style_text_font(lv.font_montserrat_18, lv.PART.MAIN)
        title.set_style_pad_bottom(10, lv.PART.MAIN)

        for handler_info in handlers:
            display_name = AppManager.get_handler_display_name(handler_info.activity_class)
            btn = lv.button(screen)
            btn.set_width(lv.pct(90))
            btn.set_style_pad_all(8, lv.PART.MAIN)
            btn.add_event_cb(
                lambda e, hi=handler_info: self._select_handler(hi, original_intent),
                lv.EVENT.CLICKED,
                None,
            )
            btn_label = lv.label(btn)
            btn_label.set_text(display_name)
            btn_label.center()

        self.setContentView(screen)

    def _select_handler(self, handler_info, original_intent):
        from ...activity_navigator import ActivityNavigator

        ActivityNavigator._dispatch(original_intent, handler_info, self._result_callback)
        self.finish()

    def onStop(self, screen):
        if __debug__: logger.debug("ChooserActivity stopped")
