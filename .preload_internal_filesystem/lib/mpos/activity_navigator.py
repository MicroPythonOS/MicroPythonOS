import logging
import sys

import utime

import mpos.ui

logger = logging.getLogger(__name__)
from mpos.ui.view import screen_stack

from .content.app_manager import AppManager
from .content.intent import Intent


def get_foreground_app():
    if screen_stack:
        current_activity, _, _, _ = screen_stack[-1]
        if current_activity:
            return current_activity.appFullName
    return None


class ActivityNavigator:

    @staticmethod
    def startActivity(intent):
        if not isinstance(intent, Intent):
            raise ValueError("Must provide an Intent")
        if intent.action:  # Implicit intent: resolve handlers
            handlers = AppManager.resolve_activity(intent)
            if not handlers:
                if __debug__: logger.debug("No handler for action: %s", intent.action)
                return
            if len(handlers) == 1:
                ActivityNavigator._dispatch(intent, handlers[0])
            else:
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
                if __debug__: logger.debug("No handler for action: %s", intent.action)
                return
            if len(handlers) == 1:
                return ActivityNavigator._dispatch(intent, handlers[0], result_callback)
            elif handlers:
                ActivityNavigator._show_chooser(intent, handlers, result_callback)
                return None  # Chooser handles result forwarding
        else:
            return ActivityNavigator._launch_activity(intent, result_callback)

    @staticmethod
    def _dispatch(intent, handler_info, result_callback=None):
        """Launch a resolved handler.

        Installed apps are launched via ``AppManager.start_app`` so they receive
        the correct app context and status-bar handling. Framework handlers
        (e.g. ViewActivity) are launched directly.
        """
        if handler_info.app_fullname:
            return AppManager.start_app(
                handler_info.app_fullname, intent=intent, result_callback=result_callback
            )

        intent.activity_class = handler_info.activity_class
        return ActivityNavigator._launch_activity(intent, result_callback)

    @staticmethod
    def _launch_activity(intent, result_callback=None):
        """Launch an activity and set up result callback."""
        if intent.app_fullname is None:
            intent.app_fullname = get_foreground_app()
        activity = intent.activity_class
        if callable(activity):
            # Instantiate the class if necessary
            activity = activity()
        activity.intent = intent
        activity._result_callback = result_callback  # Pass callback to activity
        activity.appFullName = intent.app_fullname
        start_time = utime.ticks_ms()
        mpos.ui.save_and_clear_current_focusgroup()
        try:
            activity.onCreate()
        except Exception as e:
            logger.error("activity.onCreate caught exception:")
            sys.print_exception(e)
            from mpos.ui.errordialog import show_app_error_dialog
            show_app_error_dialog(
                activity.appFullName, e, is_lifecycle=True
            )
        end_time = utime.ticks_diff(utime.ticks_ms(), start_time)
        if __debug__: logger.debug("activity.onCreate took %sms", end_time)
        return activity

    @staticmethod
    def _show_chooser(intent, handlers, result_callback=None):
        from .app.activities.chooser import ChooserActivity

        chooser_intent = Intent(
            ChooserActivity,
            extras={"original_intent": intent, "handlers": handlers, "result_callback": result_callback},
        )
        chooser_intent.app_fullname = intent.app_fullname
        ActivityNavigator._launch_activity(chooser_intent)
