import logging
import time

from .config import SharedPreferences
from .content.intent import Intent

logger = logging.getLogger(__name__)

_DEBOUNCE_MS = 500


class Notification:
    PRIORITY_MIN = -1
    PRIORITY_LOW = 0
    PRIORITY_DEFAULT = 1
    PRIORITY_HIGH = 2
    PRIORITY_MAX = 3

    def __init__(
        self,
        notification_id=None,
        uniqueidString=None,
        icon=None,
        title="",
        text="",
        priority=PRIORITY_DEFAULT,
        intent=None,
        auto_cancel=True,
        app_fullname=None,
        created_at=None,
        updated_at=None,
    ):
        resolved_id = notification_id if notification_id is not None else uniqueidString
        if not resolved_id:
            raise ValueError("Notification requires notification_id or uniqueidString")
        self.notification_id = str(resolved_id)
        # icon can be an lv.SYMBOL string, any other string, or an lv.image_dsc_t
        self.icon = icon
        self.title = "" if title is None else str(title)
        self.text = "" if text is None else str(text)
        self.priority = int(priority)
        self.intent = intent
        self.auto_cancel = bool(auto_cancel)
        self.app_fullname = app_fullname
        self.created_at = created_at
        self.updated_at = updated_at

    def update_from(self, other):
        self.icon = other.icon
        self.title = other.title
        self.text = other.text
        self.priority = other.priority
        self.intent = other.intent
        self.auto_cancel = other.auto_cancel
        self.app_fullname = other.app_fullname

    def _serialize_intent(self):
        if self.intent is None:
            return None
        return {
            "action": self.intent.action,
            "data": self.intent.data,
            "extras": self.intent.extras,
            "flags": self.intent.flags,
            "app_fullname": self.intent.app_fullname,
        }

    @staticmethod
    def _deserialize_intent(intent_data):
        if not isinstance(intent_data, dict):
            return None
        intent = Intent(
            action=intent_data.get("action"),
            data=intent_data.get("data"),
            extras=intent_data.get("extras") or {},
            app_fullname=intent_data.get("app_fullname"),
        )
        flags = intent_data.get("flags")
        if isinstance(flags, dict):
            intent.flags = flags
        return intent

    def to_persisted_dict(self):
        # Only string icons survive serialization; lv.image_dsc_t is not serializable
        icon_symbol = self.icon if isinstance(self.icon, str) else None
        return {
            "notification_id": self.notification_id,
            "icon_symbol": icon_symbol,
            "title": self.title,
            "text": self.text,
            "priority": self.priority,
            "intent": self._serialize_intent(),
            "auto_cancel": self.auto_cancel,
            "app_fullname": self.app_fullname,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_persisted_dict(cls, item):
        if not isinstance(item, dict):
            return None
        return cls(
            notification_id=item.get("notification_id"),
            icon=item.get("icon_symbol"),
            title=item.get("title", ""),
            text=item.get("text", ""),
            priority=item.get("priority", cls.PRIORITY_DEFAULT),
            intent=cls._deserialize_intent(item.get("intent")),
            auto_cancel=item.get("auto_cancel", True),
            app_fullname=item.get("app_fullname"),
            created_at=item.get("created_at"),
            updated_at=item.get("updated_at"),
        )


class NotificationManager:
    _MAX_NOTIFICATIONS = 20
    _PREFS_APP_NAME = "com.micropythonos.system"
    _PREFS_FILENAME = "notifications.json"
    _PREFS_KEY = "notifications"

    _prefs = None
    _initialized = False
    _notifications = {}
    _listeners = []
    _persist_write_count = 0
    _pending_persist = False
    _debounce_timer = None

    @classmethod
    def _now_seconds(cls):
        try:
            return int(time.time())
        except Exception:
            return 0

    @classmethod
    def _get_prefs(cls):
        if cls._prefs is None:
            cls._prefs = SharedPreferences(
                cls._PREFS_APP_NAME,
                filename=cls._PREFS_FILENAME,
                defaults={cls._PREFS_KEY: []},
            )
        return cls._prefs

    @classmethod
    def _ensure_initialized(cls):
        if cls._initialized:
            return
        cls._initialized = True
        cls._notifications = {}
        prefs = cls._get_prefs()
        for item in prefs.get_list(cls._PREFS_KEY, []):
            n = Notification.from_persisted_dict(item)
            if n is None:
                continue
            if n.created_at is None:
                n.created_at = cls._now_seconds()
            if n.updated_at is None:
                n.updated_at = n.created_at
            cls._notifications[n.notification_id] = n
        cls._trim_to_limit(persist=False)

    @classmethod
    def _trim_to_limit(cls, persist=True):
        if len(cls._notifications) <= cls._MAX_NOTIFICATIONS:
            return False
        ordered = cls._sorted_notifications()
        while len(ordered) > cls._MAX_NOTIFICATIONS:
            cls._notifications.pop(ordered.pop().notification_id, None)
        if persist:
            cls._persist()
        return True

    @classmethod
    def _sorted_notifications(cls):
        return sorted(
            cls._notifications.values(),
            key=lambda n: (int(n.priority), int(n.updated_at or 0), int(n.created_at or 0)),
            reverse=True,
        )

    @classmethod
    def _do_persist(cls, _timer=None):
        cls._pending_persist = False
        cls._debounce_timer = None
        prefs = cls._get_prefs()
        payload = [n.to_persisted_dict() for n in cls._sorted_notifications()]
        editor = prefs.edit()
        editor.put_list(cls._PREFS_KEY, payload)
        editor.commit()
        cls._persist_write_count += 1

    @classmethod
    def _persist(cls, immediate=False):
        """Schedule a deferred write. Pass immediate=True to skip debounce (e.g. on cancel)."""
        if immediate:
            # Cancel any pending debounce timer and write now
            if cls._debounce_timer is not None:
                try:
                    cls._debounce_timer.delete()
                except Exception:
                    pass
                cls._debounce_timer = None
            cls._pending_persist = False
            cls._do_persist()
            return

        if cls._pending_persist:
            return  # already scheduled, coalesce

        cls._pending_persist = True
        try:
            import lvgl as lv
            cls._debounce_timer = lv.timer_create(cls._do_persist, _DEBOUNCE_MS, None)
            cls._debounce_timer.set_repeat_count(1)
        except Exception:
            # LVGL not available (unit tests): write immediately
            cls._do_persist()

    @classmethod
    def _notify_listeners(cls):
        for callback in cls._listeners:
            try:
                callback()
            except Exception as e:
                logger.error("Listener callback failed: %s", e)

    @classmethod
    def register_listener(cls, callback, notify_immediately=True):
        cls._ensure_initialized()
        if callback not in cls._listeners:
            cls._listeners.append(callback)
        if notify_immediately:
            try:
                callback()
            except Exception as e:
                logger.error("Initial callback failed: %s", e)

    @classmethod
    def unregister_listener(cls, callback):
        cls._listeners = [cb for cb in cls._listeners if cb != callback]

    @classmethod
    def get_notifications(cls):
        cls._ensure_initialized()
        return cls._sorted_notifications()

    @classmethod
    def get_notification(cls, notification_id):
        cls._ensure_initialized()
        return cls._notifications.get(notification_id)

    @classmethod
    def notify(cls, notification):
        cls._ensure_initialized()
        if not isinstance(notification, Notification):
            raise ValueError("NotificationManager.notify expects a Notification instance")

        now_ts = cls._now_seconds()
        existing = cls._notifications.get(notification.notification_id)
        if existing:
            # Update content + timestamp but do NOT persist — same ID, no flash write
            existing.update_from(notification)
            existing.updated_at = now_ts
            cls._notify_listeners()
            return existing.notification_id

        if notification.created_at is None:
            notification.created_at = now_ts
        notification.updated_at = now_ts
        cls._notifications[notification.notification_id] = notification
        cls._trim_to_limit(persist=False)
        cls._persist()           # debounced write
        cls._notify_listeners()
        return notification.notification_id

    @classmethod
    def cancel(cls, notification_id):
        cls._ensure_initialized()
        if notification_id not in cls._notifications:
            return False
        del cls._notifications[notification_id]
        cls._persist(immediate=True)   # removal must be immediate; we don't want it to reappear on reboot
        cls._notify_listeners()
        return True

    @classmethod
    def cancel_all(cls):
        cls._ensure_initialized()
        if not cls._notifications:
            return
        cls._notifications = {}
        cls._persist(immediate=True)
        cls._notify_listeners()

    @classmethod
    def _dispatch_intent(cls, notification):
        intent = notification.intent
        target_app = notification.app_fullname

        if intent is not None:
            if intent.app_fullname is None and target_app is not None:
                intent.app_fullname = target_app
            if intent.activity_class is not None or intent.action is not None:
                try:
                    from .activity_navigator import ActivityNavigator
                    ActivityNavigator.startActivity(intent)
                    return True
                except Exception as e:
                    logger.error("Failed to start activity intent: %s", e)
            # intent exists but has no activity_class/action — use app_fullname fallback
            target_app = intent.app_fullname

        if target_app:
            try:
                from .content.app_manager import AppManager
                return bool(AppManager.start_app(target_app))
            except Exception as e:
                logger.error("Failed to start app: %s", e)
        return False

    @classmethod
    def trigger(cls, notification_or_id):
        """Dispatch the notification's intent and auto-cancel if configured."""
        cls._ensure_initialized()
        if isinstance(notification_or_id, Notification):
            notification = notification_or_id
        else:
            notification = cls._notifications.get(notification_or_id)
        if notification is None:
            return False

        launched = cls._dispatch_intent(notification)
        if launched and notification.auto_cancel:
            cls.cancel(notification.notification_id)
        return launched

    @classmethod
    def _reset_for_tests(cls, clear_storage=False):
        cls._initialized = False
        cls._notifications = {}
        cls._listeners = []
        cls._persist_write_count = 0
        cls._pending_persist = False
        cls._debounce_timer = None
        if clear_storage:
            prefs = SharedPreferences(
                cls._PREFS_APP_NAME,
                filename=cls._PREFS_FILENAME,
                defaults={cls._PREFS_KEY: []},
            )
            editor = prefs.edit()
            editor.remove_all()
            editor.commit()
        cls._prefs = None
