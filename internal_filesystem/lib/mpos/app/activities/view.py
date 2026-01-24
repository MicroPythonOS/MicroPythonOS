from ..activity import Activity
from ...content.app_manager import AppManager

class ViewActivity(Activity):
    def __init__(self):
        super().__init__()

    def onCreate(self):
        screen = lv.obj()
        # Get content from intent (prefer extras.url, fallback to data)
        content = self.getIntent().extras.get("url", self.getIntent().data or "No content")
        label = lv.label(screen)
        label.set_user_data("content_label")
        label.set_text(f"Viewing: {content}")
        label.center()
        self.setContentView(screen)

    def onStart(self, screen):
        content = self.getIntent().extras.get("url", self.getIntent().data or "No content")
        for i in range(screen.get_child_cnt()):
            if screen.get_child(i).get_user_data() == "content_label":
                screen.get_child(i).set_text(f"Viewing: {content}")

    def onStop(self, screen):
        if self.getIntent() and self.getIntent().getStringExtra("destination") == "ViewActivity":
            print("Stopped for View")
        else:
            print("Stopped for other screen")

# Register this activity for "view" intents
AppManager.register_activity("view", ViewActivity)
