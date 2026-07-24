import logging
import lvgl as lv

logger = logging.getLogger(__name__)

class Activity:

    def __init__(self):
        self.intent = None  # Store the intent that launched this activity
        self.result = None
        self._result_callback = None
        self._has_foreground = None
        self.appFullName = None

    def onCreate(self):
        pass
    def onStart(self, screen):
        pass

    def onResume(self, screen): # app goes to foreground
        self._has_foreground = True

    def onPause(self, screen): # app goes to background
        self._has_foreground = False

    def onBackPressed(self, screen):
        """Intercept the back/close gesture before the activity is paused.

        Return True to consume the event (the activity stays foreground and
        must call finish() itself when it is ready to close). Return False to
        let the framework finish the activity normally.
        """
        return False

    def onStop(self, screen):
        pass
    def onDestroy(self, screen):
        pass

    def setContentView(self, screen):
        # Lazy import avoids circular import during mpos/ui package initialization.
        import mpos.ui

        mpos.ui.setContentView(self, screen)

    def startActivity(self, intent):
        from mpos.activity_navigator import ActivityNavigator
        intent.app_fullname = self.appFullName
        ActivityNavigator.startActivity(intent)

    def startActivityForResult(self, intent, result_callback):
        from mpos.activity_navigator import ActivityNavigator
        intent.app_fullname = self.appFullName
        ActivityNavigator.startActivityForResult(intent, result_callback)

    def initError(self, e):
        logger.warning("You might have inherited from Activity with a custom __init__() without calling super().__init__(). Got AttributeError: %s", e)

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
        from mpos.ui.view import finish_current_activity

        finish_current_activity()
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
            result = func(*args, **kwargs)
            if event:
                event.set()
            return result
        else:
            return None

    # Update the UI in a threadsafe way if the Activity is in the foreground
    # The order of these update_ui calls are not guaranteed, so a UI update might be overwritten by an "earlier" update.
    # To avoid this, use lv.timer_create() with .set_repeat_count(1) as examplified in osupdate.py
    # Or avoid using threads altogether, by using TaskManager (asyncio).
    def update_ui_threadsafe_if_foreground(self, func, *args, important=False, event=None, **kwargs):
        # lv.async_call() is needed to update the UI from another thread than the main one (as LVGL is not thread safe)
        result = lv.async_call(lambda _: self.if_foreground(func, *args, event=event, **kwargs), None)
        return result
