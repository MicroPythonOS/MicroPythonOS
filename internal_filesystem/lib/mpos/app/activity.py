import lvgl as lv
import mpos.ui
import time

class Activity:

    def __init__(self):
        self.intent = None  # Store the intent that launched this activity
        self.result = None
        self._result_callback = None
        self._has_foreground = None

    def onCreate(self):
        pass
    def onStart(self, screen):
        pass

    def onResume(self, screen): # app goes to foreground
        self._has_foreground = True

    def onPause(self, screen): # app goes to background
        self._has_foreground = False

    def onStop(self, screen):
        pass
    def onDestroy(self, screen):
        pass

    def setContentView(self, screen):
        mpos.ui.setContentView(self, screen)

    def startActivity(self, intent):
        from mpos.activity_navigator import ActivityNavigator
        ActivityNavigator.startActivity(intent)

    def startActivityForResult(self, intent, result_callback):
        from mpos.activity_navigator import ActivityNavigator
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

    # Apps may want to check this to cancel heavy operations if the user moves away
    def has_foreground(self):
        return self._has_foreground

    # Execute a function if the Activity is in the foreground
    def if_foreground(self, func, *args, event=None, **kwargs):
        if self._has_foreground:
            #print(f"executing {func} with args {args} and kwargs {kwargs}")
            result = func(*args, **kwargs)
            if event:
                event.set()
            return result
        else:
            #print(f"[if_foreground] Skipped {func} because _has_foreground=False")
            return None

    # Update the UI in a threadsafe way if the Activity is in the foreground
    # The order of these update_ui calls are not guaranteed, so a UI update might be overwritten by an "earlier" update.
    # To avoid this, use lv.timer_create() with .set_repeat_count(1) as examplified in osupdate.py
    # Or avoid using threads altogether, by using TaskManager (asyncio).
    def update_ui_threadsafe_if_foreground(self, func, *args, important=False, event=None, **kwargs):
        # lv.async_call() is needed to update the UI from another thread than the main one (as LVGL is not thread safe)
        result = lv.async_call(lambda _: self.if_foreground(func, *args, event=event, **kwargs), None)
        return result
