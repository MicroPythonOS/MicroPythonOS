"""
Unit test for AppDetail install button double-click guard.

Verifies:
- Missing download_url is ignored
- Install/uninstall/restore button is disabled immediately on click
- Second click while action is in progress is rejected
- fetch_and_set_app_details skips button rebuild during action
"""

import sys
import unittest
import lvgl as lv

sys.path.insert(0, "builtin/apps/com.micropythonos.appstore")
import app_detail
AppDetail = app_detail.AppDetail

from mpos.ui.testing import wait_for_render
from mpos import TaskManager


class _MockApp:
    download_url = None
    fullname = "com.test.app"


class TestAppDetailInstallButton(unittest.TestCase):
    def setUp(self):
        self.screen = lv.obj()
        self.screen.set_size(320, 240)
        lv.screen_load(self.screen)

        self.detail = type("MockDetail", (), {})()
        self.detail.install_button = lv.button(self.screen)
        self.detail.install_label = lv.label(self.detail.install_button)
        self.detail.install_label.set_text("Install")
        self.detail._action_in_progress = False
        self.detail.action_label_install = "Install"
        self.detail.action_label_uninstall = "Uninstall"
        self.detail.action_label_restore = "Restore Built-in"

        self.app = _MockApp()
        self.app.download_url = "https://example.com/app.zip"
        self.app.fullname = "com.test.app"

        async def _noop(*args, **kwargs):
            pass
        self.detail.download_and_install = _noop
        self.detail.uninstall_app = _noop

        self._tasks_created = 0

        def _fake_create_task(coro):
            self._tasks_created += 1
        self._orig_create_task = TaskManager.create_task
        TaskManager.create_task = _fake_create_task

        wait_for_render(2)

    def tearDown(self):
        TaskManager.create_task = self._orig_create_task
        lv.screen_load(lv.obj())
        wait_for_render(2)

    def _call_toggle(self):
        AppDetail.toggle_install(self.detail, self.app)

    def test_no_download_url_ignores_click(self):
        self.app.download_url = None
        self._call_toggle()
        self.assertFalse(
            bool(self.detail.install_button.get_state() & lv.STATE.DISABLED),
            "button must not be disabled when download_url is missing",
        )
        self.assertEqual(self._tasks_created, 0)

    def test_install_disables_button_immediately(self):
        self._call_toggle()
        self.assertTrue(
            bool(self.detail.install_button.get_state() & lv.STATE.DISABLED),
            "button must be disabled immediately on install click",
        )
        self.assertEqual(self.detail.install_label.get_text(), "Please wait...")

    def test_second_click_while_disabled_rejected(self):
        self._call_toggle()
        tasks_after_first = self._tasks_created
        self._call_toggle()
        self.assertEqual(
            self._tasks_created, tasks_after_first,
            "second click must not create another task",
        )

    def test_uninstall_disables_button_immediately(self):
        self.detail.install_label.set_text("Uninstall")
        self._call_toggle()
        self.assertTrue(
            bool(self.detail.install_button.get_state() & lv.STATE.DISABLED),
            "uninstall button must be disabled immediately",
        )

    def test_restore_disables_button_immediately(self):
        self.detail.install_label.set_text("Restore Built-in")
        self._call_toggle()
        self.assertTrue(
            bool(self.detail.install_button.get_state() & lv.STATE.DISABLED),
            "restore button must be disabled immediately",
        )

    def test_fetch_details_skips_rebuild_during_action(self):
        """fetch_and_set_app_details must not call add_action_buttons during install/uninstall."""
        self.detail._action_in_progress = True
        self.detail.app = self.app
        self.detail.version_label = lv.label(self.screen)
        self.detail.long_desc_label = lv.label(self.screen)
        self.detail.publisher_label = lv.label(self.screen)
        self.detail.buttoncont = lv.obj(self.screen)
        self.detail.fetch_badgehub_app_details = lambda s: None
        self.detail._sync_open_button = lambda: None
        self.detail._start_icon_download = lambda: None

        self._add_action_called = False
        def _mock_add_action(cont, app):
            self._add_action_called = True
        self.detail.add_action_buttons = _mock_add_action

        app_detail.AppDetail.fetch_and_set_app_details(self.detail)
        self.assertFalse(
            self._add_action_called,
            "fetch_and_set_app_details must skip add_action_buttons during action",
        )
