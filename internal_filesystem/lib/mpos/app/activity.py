from mpos.navigator import ActivityNavigator

import mpos.ui

class Activity:

    def __init__(self):
        self.intent = None  # Store the intent that launched this activity
        self.result = None
        self._result_callback = None

    def onCreate(self):
        pass
    def onStart(self, screen):
        pass
    def onResume(self, screen):
        pass
    def onPause(self, screen):
        pass
    def onStop(self, screen):
        pass
    def onDestroy(self, screen):
        pass

    def setContentView(self, screen):
        mpos.ui.setContentView(self, screen)

    def startActivity(self, intent):
        ActivityNavigator.startActivity(intent)

    def startActivityForResult(self, intent, result_callback):
        ActivityNavigator.startActivityForResult(intent, result_callback)

    def initError(self, e):
        print(f"WARNING: You might have inherited from Activity with a custom __init__() without calling super().__init__(). Got AttributeError: {e}")

    def getIntent(self):
        try:
            return self.intent
        except AttributeError as e:
            self.initError(e)

    def setResult(self, result_code, data=None):
        """Set the result to be returned when the activity finishes."""
        try:
            self.result = {"result_code": result_code, "data": data or {}}
        except AttributeError as e:
            self.initError(e)

    def finish(self):
        mpos.ui.back_screen()
        try:
            if self._result_callback and self.result:
                self._result_callback(self.result)
                self._result_callback = None  # Clean up
        except AttributeError as e:
            self.initError(e)
