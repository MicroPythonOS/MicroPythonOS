import lvgl as lv
import mpos.ui
import time

class Activity:

    throttle_async_call_counter = 0

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
        mpos.ui.task_handler.add_event_cb(self.task_handler_callback, 1)

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

    def task_handler_callback(self, a, b):
        self.throttle_async_call_counter = 0

    # Execute a function if the Activity is in the foreground
    def if_foreground(self, func, *args, **kwargs):
        if self._has_foreground:
            #print(f"executing {func} with args {args} and kwargs {kwargs}")
            result = func(*args, **kwargs)
            return result
        else:
            #print(f"[if_foreground] Skipped {func} because _has_foreground=False")
            return None

    # Update the UI in a threadsafe way if the Activity is in the foreground
    # The call may get throttled, unless important=True is added to it.
    # The order of these update_ui calls are not guaranteed, so a UI update might be overwritten by an "earlier" update.
    # To avoid this, use lv.timer_create() with .set_repeat_count(1) as examplified in osupdate.py
    def update_ui_threadsafe_if_foreground(self, func, *args, important=False, **kwargs):
        self.throttle_async_call_counter += 1
        if not important and self.throttle_async_call_counter > 100: # 250 seems to be okay, so 100 is on the safe side
            print(f"update_ui_threadsafe_if_foreground called more than 100 times for one UI frame, which can overflow - throttling!")
            return None
        # lv.async_call() is needed to update the UI from another thread than the main one (as LVGL is not thread safe)
        result = lv.async_call(lambda _: self.if_foreground(func, *args, **kwargs),None)
        return result
