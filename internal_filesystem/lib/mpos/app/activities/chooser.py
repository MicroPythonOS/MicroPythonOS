from ..activity import Activity
# Chooser doesn't handle an action — it shows handlers
# → No registration needed

from ...content.pm import PackageManager

class ChooserActivity(Activity):
    def __init__(self):
        super().__init__()

    def onCreate(self):
        screen = lv.obj()
        # Get handlers from intent extras
        original_intent = self.getIntent().extras.get("original_intent")
        handlers = self.getIntent().extras.get("handlers", [])
        label = lv.label(screen)
        label.set_text("Choose an app")
        label.set_pos(10, 10)

        for i, handler_name in enumerate(handlers):
            btn = lv.btn(screen)
            btn.set_user_data(f"handler_{i}")
            btn_label = lv.label(btn)
            btn_label.set_text(handler_name)
            btn.set_pos(10, 50 * (i + 1) + 10)
            btn.add_event_cb(lambda e, h=handler_name, oi=original_intent: self._select_handler(h, oi), lv.EVENT.CLICKED)
        self.setContentView(screen)

    def _select_handler(self, handler_name, original_intent):
        for handler in PackageManager.APP_REGISTRY.get(original_intent.action, []):
            if handler.__name__ == handler_name:
                original_intent.activity_class = handler
                navigator.startActivity(original_intent)
                break
        navigator.finish()  # Close chooser

    def onStop(self, screen):
        if self.getIntent() and self.getIntent().getStringExtra("destination") == "ChooserActivity":
            print("Stopped for Chooser")
        else:
            print("Stopped for other screen")


