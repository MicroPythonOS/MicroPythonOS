from ..activity import Activity
from ...content.app_manager import AppManager

class ShareActivity(Activity):
    def __init__(self):
        super().__init__()

    def onCreate(self):
        screen = lv.obj()
        # Get text from intent (prefer extras.text, fallback to data)
        text = self.getIntent().extras.get("text", self.getIntent().data or "No text")
        label = lv.label(screen)
        label.set_user_data("share_label")
        label.set_text(f"Share: {text}")
        label.set_pos(10, 10)

        btn = lv.btn(screen)
        btn.set_user_data("share_btn")
        btn_label = lv.label(btn)
        btn_label.set_text("Share")
        btn.set_pos(10, 50)
        btn.add_event_cb(lambda e: self._share_content(text), lv.EVENT.CLICKED)
        self.setContentView(screen)

    def _share_content(self, text):
        # Dispatch to another app (e.g., MessagingActivity) or simulate sharing
        print(f"Sharing: {text}")  # Placeholder for actual sharing
        # Example: Launch another share handler
        navigator.startActivity(Intent(action="share", data=text))
        navigator.finish()  # Close ShareActivity

    def onStop(self, screen):
        if self.getIntent() and self.getIntent().getStringExtra("destination") == "ShareActivity":
            print("Stopped for Share")
        else:
            print("Stopped for other screen")

AppManager.register_activity("share", ShareActivity)
