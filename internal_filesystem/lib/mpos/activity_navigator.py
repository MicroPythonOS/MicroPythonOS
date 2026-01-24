import sys
import utime

from .content.intent import Intent
from .content.app_manager import AppManager

import mpos.ui

class ActivityNavigator:

    @staticmethod
    def startActivity(intent):
        if not isinstance(intent, Intent):
            raise ValueError("Must provide an Intent")
        if intent.action:  # Implicit intent: resolve handlers
            handlers = AppManager.resolve_activity(intent)
            if not handlers:
                print("No handler for action:", intent.action)
                return
            if len(handlers) == 1:
                intent.activity_class = handlers[0]
                ActivityNavigator._launch_activity(intent)
            elif handlers:
                ActivityNavigator._show_chooser(intent, handlers)
        else:
            ActivityNavigator._launch_activity(intent)

    @staticmethod
    def startActivityForResult(intent, result_callback):
        """Launch an activity and pass a callback for the result."""
        if not isinstance(intent, Intent):
            raise ValueError("Must provide an Intent")
        if intent.action:  # Implicit intent: resolve handlers
            handlers = AppManager.resolve_activity(intent)
            if not handlers:
                print("No handler for action:", intent.action)
                return
            if len(handlers) == 1:
                intent.activity_class = handlers[0]
                return ActivityNavigator._launch_activity(intent, result_callback)
            elif handlers:
                ActivityNavigator._show_chooser(intent, handlers)
                return None  # Chooser handles result forwarding
        else:
            return ActivityNavigator._launch_activity(intent, result_callback)

    @staticmethod
    def _launch_activity(intent, result_callback=None):
        """Launch an activity and set up result callback."""
        activity = intent.activity_class
        if callable(activity):
            # Instantiate the class if necessary
            activity = activity()
        activity.intent = intent
        activity._result_callback = result_callback  # Pass callback to activity
        start_time = utime.ticks_ms()
        mpos.ui.save_and_clear_current_focusgroup()
        try:
            activity.onCreate()
        except Exception as e:
            print(f"activity.onCreate caught exception:")
            sys.print_exception(e)
        end_time = utime.ticks_diff(utime.ticks_ms(), start_time)
        print(f"apps.py _launch_activity: activity.onCreate took {end_time}ms")
        return activity

    @staticmethod
    def _show_chooser(intent, handlers):
        chooser_intent = Intent(ChooserActivity, extras={"original_intent": intent, "handlers": [h.__name__ for h in handlers]})
        ActivityNavigator._launch_activity(chooser_intent)

