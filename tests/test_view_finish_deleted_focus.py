"""
Graphical tests for finish_current_activity with deleted focused objects.

Covers the notification-drawer → app-launch → auto-cancel → dangling-focus
scenario that crashes the expander input driver via an unhandled
LvReferenceError in finish_current_activity.
"""

import lvgl as lv

from mpos.ui.testing import GraphicalTestCase


class TestFinishActivityDeletedFocus(GraphicalTestCase):
    """Verify finish_current_activity survives a deleted prev_focused reference."""

    def test_focus_deleted_object_raises_reference_error(self):
        """lv.group_focus_obj on a deleted object raises LvReferenceError."""
        btn = lv.button(self.screen)
        lbl = lv.label(btn)
        lbl.set_text("test-btn")
        btn.set_size(80, 40)
        self.wait_for_render()

        group = lv.group_get_default()
        group.add_obj(btn)
        self.wait_for_render()

        btn.delete()
        self.wait_for_render()

        with self.assertRaises(lv.LvReferenceError):
            lv.group_focus_obj(btn)

    def test_finish_activity_with_deleted_prev_focused(self):
        """finish_current_activity must not raise when prev_focused is deleted.

        The notification-drawer path:
        1. User opens drawer → taps notification → app launches
        2. save_and_clear_current_focusgroup captures the focused
           notification widget in the home screen's stack entry
        3. Notification auto-cancel deletes the widget
        4. User presses ESC to go back → finish_current_activity
           calls lv.group_focus_obj(deleted_widget) → LvReferenceError
           → unhandled exception kills expander input driver
        """
        from mpos.ui import view as view_module
        from mpos.ui.focus import move_focusgroup_objects

        original_stack = view_module.screen_stack[:]
        screen2 = None
        try:
            # Build a focusable button on self.screen (represents the
            # focused drawer notification widget at the time of tap).
            btn = lv.button(self.screen)
            lbl = lv.label(btn)
            lbl.set_text("NotificationBtn")
            btn.set_size(100, 40)
            self.wait_for_render()

            default_group = lv.group_get_default()
            default_group.add_obj(btn)
            lv.group_focus_obj(btn)
            self.wait_for_render()
            self.assertIs(default_group.get_focused(), btn)

            # Simulate save_and_clear_current_focusgroup:
            # Move all tracked objects out of the default group into a
            # saved focusgroup, and capture the currently focused widget.
            focused = default_group.get_focused()
            fg = lv.group_create()
            move_focusgroup_objects(default_group, fg)

            # Stack entry 0: home screen, its focusgroup + focused widget
            view_module.screen_stack = [
                (None, self.screen, fg, focused),
            ]

            # Push screen2 as the "Nostr app" entry, making it active.
            screen2 = lv.obj()
            screen2.set_size(320, 240)
            lv.screen_load(screen2)
            self.wait_for_render()
            view_module.screen_stack.append(
                (None, screen2, lv.group_create(), None)
            )

            # Simulate auto-cancel cleanup: the notification widget is
            # deleted from the drawer container (via .clean()).
            btn.delete()
            self.wait_for_render()

            # ESC (second press: drawer closed on first press) →
            # finish_current_activity must NOT propagate LvReferenceError
            result = view_module.finish_current_activity()
            self.assertTrue(result)
            self.assertEqual(len(view_module.screen_stack), 1)
        finally:
            view_module.screen_stack[:] = original_stack
            # screen2 is deleted by screen_load_anim's auto_del=True
            # when finish_current_activity restores self.screen.
            # Just ensure self.screen is the active screen for teardown.
            try:
                lv.screen_load(self.screen)
                self.wait_for_render()
            except Exception:
                pass

    def test_finish_activity_prev_focused_none_works(self):
        """finish_current_activity still works with prev_focused=None (normal path)."""
        from mpos.ui import view as view_module
        from mpos.ui.focus import move_focusgroup_objects

        original_stack = view_module.screen_stack[:]
        screen2 = None
        try:
            default_group = lv.group_get_default()
            fg = lv.group_create()
            move_focusgroup_objects(default_group, fg)

            view_module.screen_stack = [
                (None, self.screen, fg, None),
            ]

            screen2 = lv.obj()
            screen2.set_size(320, 240)
            lv.screen_load(screen2)
            self.wait_for_render()
            view_module.screen_stack.append(
                (None, screen2, lv.group_create(), None)
            )

            result = view_module.finish_current_activity()
            self.assertTrue(result)
            self.assertEqual(len(view_module.screen_stack), 1)
        finally:
            view_module.screen_stack[:] = original_stack
            try:
                lv.screen_load(self.screen)
                self.wait_for_render()
            except Exception:
                pass
