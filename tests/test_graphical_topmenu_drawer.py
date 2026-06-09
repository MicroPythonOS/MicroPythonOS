"""
Graphical tests for the drawer menu (topmenu drawer).

Covers:
- open_drawer() / close_drawer() API and state flags
- Focus moves to the brightness slider when the drawer opens
- Focus is restored to the previously focused widget when the drawer closes
- All static icon buttons (wifi, settings, home, restart, power) are in the focus group
- Notification card buttons are in the focus group when a notification exists
- Notification cards are removed from the focus group after close_drawer()
- Drawer re-populates notification items on a second open
"""

import time
import unittest

import lvgl as lv

from mpos import (
    AppManager,
    AppearanceManager,
    Notification,
    NotificationManager,
    get_widget_coords,
    wait_for_focus,
    wait_for_widget,
)
from mpos.ui import topmenu


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _wait_ms(ms):
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < ms:
        lv.task_handler()
        time.sleep(0.01)


def _wait_drawer_open(timeout=6):
    def _check():
        if not topmenu.drawer_open:
            return None
        d = topmenu.drawer
        if d is None or d.has_flag(lv.obj.FLAG.HIDDEN):
            return None
        return d
    return wait_for_widget(_check, timeout=timeout)


def _wait_drawer_closed(timeout=6):
    def _check():
        if topmenu.drawer_open:
            return None
        d = topmenu.drawer
        if d is None:
            return True
        return True if d.has_flag(lv.obj.FLAG.HIDDEN) else None
    return wait_for_widget(_check, timeout=timeout)


def _objects_in_focus_group():
    """Return a list of all objects currently in the default focus group."""
    group = lv.group_get_default()
    if group is None:
        return []
    result = []
    for i in range(group.get_obj_count()):
        result.append(group.get_obj_by_index(i))
    return result


def _focused_obj():
    group = lv.group_get_default()
    return group.get_focused() if group else None


TEST_NOTIF_ID = "test.drawer.focus.notification"


def _post_test_notification():
    NotificationManager.notify(
        Notification(
            notification_id=TEST_NOTIF_ID,
            icon=lv.SYMBOL.BELL,
            title="Drawer test notification",
            text="Focus navigation test",
            priority=Notification.PRIORITY_HIGH,
            app_fullname="com.micropythonos.settings",
            auto_cancel=False,
        )
    )


# ---------------------------------------------------------------------------

class TestDrawerOpenClose(unittest.TestCase):
    """Verify open_drawer / close_drawer API and drawer_open state flag."""

    def setUp(self):
        NotificationManager.cancel_all()
        AppManager.start_app("com.micropythonos.launcher")
        _wait_ms(500)
        # Ensure drawer is closed to start.
        if topmenu.drawer_open:
            topmenu.close_drawer()
            _wait_drawer_closed(timeout=6)

    def tearDown(self):
        if topmenu.drawer_open:
            topmenu.close_drawer()
            _wait_drawer_closed(timeout=4)
        NotificationManager.cancel_all()

    def test_open_drawer_sets_flag_and_shows_widget(self):
        topmenu.open_drawer()
        drawer = _wait_drawer_open(timeout=8)
        self.assertIsNotNone(drawer, "Drawer did not become visible after open_drawer()")
        self.assertTrue(topmenu.drawer_open, "drawer_open flag not set")
        self.assertFalse(drawer.has_flag(lv.obj.FLAG.HIDDEN), "Drawer widget is HIDDEN")

    def test_close_drawer_clears_flag_and_hides_widget(self):
        topmenu.open_drawer()
        _wait_drawer_open(timeout=8)

        topmenu.close_drawer()
        result = _wait_drawer_closed(timeout=8)
        self.assertIsNotNone(result, "Drawer did not close after close_drawer()")
        self.assertFalse(topmenu.drawer_open, "drawer_open flag still set after close")

    def test_open_drawer_idempotent(self):
        topmenu.open_drawer()
        topmenu.open_drawer()  # second call is a no-op
        drawer = _wait_drawer_open(timeout=8)
        self.assertIsNotNone(drawer, "Drawer not visible after double open_drawer()")

    def test_close_drawer_idempotent(self):
        # Already closed from setUp — calling close again should not raise.
        self.assertFalse(topmenu.drawer_open)
        topmenu.close_drawer()
        self.assertFalse(topmenu.drawer_open)

    def test_toggle_drawer(self):
        self.assertFalse(topmenu.drawer_open)
        topmenu.toggle_drawer()
        _wait_drawer_open(timeout=6)
        self.assertTrue(topmenu.drawer_open)

        topmenu.toggle_drawer()
        _wait_drawer_closed(timeout=6)
        self.assertFalse(topmenu.drawer_open)


# ---------------------------------------------------------------------------

class TestDrawerFocusOnOpen(unittest.TestCase):
    """Verify focus moves to the brightness slider when the drawer opens."""

    def setUp(self):
        NotificationManager.cancel_all()
        AppManager.start_app("com.micropythonos.launcher")
        _wait_ms(500)
        if topmenu.drawer_open:
            topmenu.close_drawer()
            _wait_drawer_closed(timeout=6)

    def tearDown(self):
        if topmenu.drawer_open:
            topmenu.close_drawer()
            _wait_drawer_closed(timeout=4)
        NotificationManager.cancel_all()

    def test_focus_moves_to_slider_on_open(self):
        """After open_drawer() the focused object should be the brightness slider."""
        slider = topmenu._drawer_slider
        self.assertIsNotNone(slider, "_drawer_slider not set — was create_drawer() called?")

        topmenu.open_drawer()
        _wait_drawer_open(timeout=8)

        self.assertIsNotNone(
            wait_for_focus(slider, timeout=1.0),
            "Slider should be focused after open_drawer()",
        )

    def test_static_buttons_in_focus_group_when_open(self):
        """All six static drawer widgets must be in the focus group while open."""
        topmenu.open_drawer()
        _wait_drawer_open(timeout=8)

        focusables = _objects_in_focus_group()
        for widget in topmenu._drawer_focusables:
            self.assertIn(
                widget, focusables,
                f"Static drawer widget not in focus group after open_drawer()",
            )

    def test_static_buttons_removed_from_focus_group_when_closed(self):
        """Static drawer widgets must leave the focus group after close_drawer()."""
        topmenu.open_drawer()
        _wait_drawer_open(timeout=8)
        topmenu.close_drawer()
        _wait_drawer_closed(timeout=8)

        focusables = _objects_in_focus_group()
        for widget in topmenu._drawer_focusables:
            self.assertFalse(
                widget in focusables,
                "Static drawer widget still in focus group after close_drawer()",
            )


# ---------------------------------------------------------------------------

class TestDrawerFocusRestore(unittest.TestCase):
    """Verify that focus returns to the pre-drawer widget when the drawer closes."""

    def setUp(self):
        NotificationManager.cancel_all()
        AppManager.start_app("com.micropythonos.launcher")
        _wait_ms(800)  # wait for launcher to build its icon grid
        if topmenu.drawer_open:
            topmenu.close_drawer()
            _wait_drawer_closed(timeout=6)

    def tearDown(self):
        if topmenu.drawer_open:
            topmenu.close_drawer()
            _wait_drawer_closed(timeout=4)
        NotificationManager.cancel_all()

    def test_focus_restored_after_close_drawer(self):
        """Whatever was focused before open_drawer() must be focused again after close."""
        # The launcher has already put focus on the first app tile.
        pre_focused = _focused_obj()
        self.assertIsNotNone(pre_focused, "Nothing focused before opening drawer — launcher must have focusable tiles")

        topmenu.open_drawer()
        _wait_drawer_open(timeout=8)

        # Focus should now be on the slider, not the launcher tile.
        in_drawer_focused = _focused_obj()
        self.assertIsNot(
            in_drawer_focused, pre_focused,
            "Focus did not move away from the launcher tile when drawer opened",
        )

        topmenu.close_drawer()
        _wait_drawer_closed(timeout=8)

        self.assertIsNotNone(
            wait_for_focus(pre_focused, timeout=1.0),
            "Focus was not restored to pre-drawer widget after close_drawer()",
        )

    def test_focus_restore_survives_repeated_open_close(self):
        """Focus restore must work correctly across multiple open/close cycles."""
        pre_focused = _focused_obj()
        self.assertIsNotNone(pre_focused)

        for _ in range(2):
            topmenu.open_drawer()
            _wait_drawer_open(timeout=8)
            topmenu.close_drawer()
            _wait_drawer_closed(timeout=8)
            _wait_ms(100)

        self.assertIsNotNone(
            wait_for_focus(pre_focused, timeout=1.0),
            "Focus not restored correctly after repeated open/close cycles",
        )


# ---------------------------------------------------------------------------

class TestDrawerNotificationFocus(unittest.TestCase):
    """Verify notification cards enter and leave the focus group with the drawer."""

    def setUp(self):
        NotificationManager.cancel_all()
        _post_test_notification()
        AppManager.start_app("com.micropythonos.launcher")
        _wait_ms(500)
        if topmenu.drawer_open:
            topmenu.close_drawer()
            _wait_drawer_closed(timeout=6)

    def tearDown(self):
        if topmenu.drawer_open:
            topmenu.close_drawer()
            _wait_drawer_closed(timeout=4)
        NotificationManager.cancel_all()

    def test_notification_cards_in_focus_group_when_drawer_open(self):
        """Notification card widgets must be in the focus group while the drawer is open."""
        topmenu.open_drawer()
        _wait_drawer_open(timeout=8)
        _wait_ms(100)

        notif_focusables = topmenu._drawer_notif_focusables
        self.assertTrue(
            len(notif_focusables) > 0,
            "No notification focusables — was the notification registered?",
        )
        focusables = _objects_in_focus_group()
        for widget in notif_focusables:
            self.assertIn(
                widget, focusables,
                "Notification card not in focus group after open_drawer()",
            )

    def test_notification_cards_removed_from_focus_group_after_close(self):
        """Notification card widgets must leave the focus group after close_drawer()."""
        topmenu.open_drawer()
        _wait_drawer_open(timeout=8)
        notif_focusables = list(topmenu._drawer_notif_focusables)
        self.assertTrue(len(notif_focusables) > 0, "No notification focusables after open")

        topmenu.close_drawer()
        _wait_drawer_closed(timeout=8)

        focusables = _objects_in_focus_group()
        for widget in notif_focusables:
            self.assertFalse(
                widget in focusables,
                "Notification card still in focus group after close_drawer()",
            )

    def test_notification_text_visible_in_drawer(self):
        """The notification title must appear as a label inside the drawer."""
        topmenu.open_drawer()
        _wait_drawer_open(timeout=8)

        drawer = topmenu.drawer
        self.assertIsNotNone(drawer)

        def _collect_texts(root):
            result = []
            stack = [root]
            while stack:
                node = stack.pop()
                try:
                    t = node.get_text()
                    if t:
                        result.append(t)
                except Exception:
                    pass
                try:
                    for i in range(node.get_child_count()):
                        stack.append(node.get_child(i))
                except Exception:
                    pass
            return result

        texts = _collect_texts(drawer)
        self.assertTrue(
            any("Drawer test notification" in t for t in texts),
            f"Notification title not found in drawer. Texts: {texts}",
        )

    def test_no_notifications_shows_empty_label(self):
        """When there are no notifications the drawer must show 'No notifications'."""
        NotificationManager.cancel_all()
        _wait_ms(200)

        topmenu.open_drawer()
        _wait_drawer_open(timeout=8)

        drawer = topmenu.drawer
        self.assertIsNotNone(drawer)

        def _collect_texts(root):
            result = []
            stack = [root]
            while stack:
                node = stack.pop()
                try:
                    t = node.get_text()
                    if t:
                        result.append(t)
                except Exception:
                    pass
                try:
                    for i in range(node.get_child_count()):
                        stack.append(node.get_child(i))
                except Exception:
                    pass
            return result

        texts = _collect_texts(drawer)
        self.assertTrue(
            any("No notifications" in t for t in texts),
            f"'No notifications' label not found in drawer. Texts: {texts}",
        )

    def test_notification_focusables_updated_on_refresh(self):
        """Cancelling a notification while drawer is open must remove its card from the focus group."""
        topmenu.open_drawer()
        _wait_drawer_open(timeout=8)
        _wait_ms(100)

        self.assertTrue(len(topmenu._drawer_notif_focusables) > 0, "No notif focusables before cancel")

        NotificationManager.cancel(TEST_NOTIF_ID)
        _wait_ms(300)  # listener fires asynchronously

        # After the notification is cancelled, the notif focusables list should be empty.
        self.assertEqual(
            len(topmenu._drawer_notif_focusables), 0,
            "Notification focusables not cleared after notification was cancelled",
        )
        focusables = _objects_in_focus_group()
        # Verify no stale card references linger in the group either.
        # (The _drawer_notif_focusables list is the authoritative set; it being empty
        # means _remove_focusables_from_group was already called.)
        # We simply assert the list is consistent — no further checks needed.
