"""
test_graphical_appstore_detail_focus.py - The app detail page must keep
keyboard focus on the install button while its details load.

Issue #256: opening a detail page focuses the install button, but when the
long description arrives fetch_and_set_app_details() rebuilds the button row
with buttoncont.clean(). Deleting the focused button makes LVGL move focus to
the next widget in the group, which is the long description label, so pressing
A no longer installs.

Usage:
    python3 scripts/test_runner.py tests/test_graphical_appstore_detail_focus.py
"""

import sys
import unittest

import lvgl as lv

sys.path.insert(0, "builtin/apps/com.micropythonos.appstore")
import app_detail
AppDetail = app_detail.AppDetail

from mpos import AppManager
from mpos.ui import add_focus_highlight
from mpos.ui.testing import wait_for_render


class _MockApp:
    download_url = None
    fullname = "com.test.detailfocus"
    version = None
    publisher = "tester"
    short_description = "short"
    long_description = "long"


class TestAppDetailKeepsFocus(unittest.TestCase):
    def setUp(self):
        self.screen = lv.obj()
        self.screen.set_size(320, 240)
        lv.screen_load(self.screen)

        self.group = lv.group_get_default()
        while self.group.get_obj_count():
            lv.group_remove_obj(self.group.get_obj_by_index(0))

        self.buttoncont = lv.obj(self.screen)
        self.buttoncont.set_flex_flow(lv.FLEX_FLOW.ROW)
        self.buttoncont.set_size(lv.pct(100), lv.SIZE_CONTENT)

        # A first button row, as created by onCreate().
        self.detail = type("MockDetail", (), {})()
        self.detail.action_label_install = "Install"
        self.detail.action_label_uninstall = "Uninstall"
        self.detail.install_button = None
        self.detail.install_label = None
        self.detail.update_button = None
        self.detail._open_button = None
        self.detail._sync_open_button = lambda: None
        self.detail._sync_rate_cont = lambda: None
        self.detail._update_version_labels = lambda: None
        self.detail.set_install_label = lambda fullname: None
        self.detail.app = _MockApp()

        self._orig_is_installed = AppManager.is_installed_by_name
        self._orig_is_update = AppManager.is_update_available
        AppManager.is_installed_by_name = lambda fn: False
        AppManager.is_update_available = lambda fn, v: False

        AppDetail.add_action_buttons(self.detail, self.buttoncont, self.detail.app)

        # onCreate() creates the labels after the button row, so the group
        # order is install_button, then these focusable labels.
        self.version_label = lv.label(self.screen)
        self.version_label.set_text("Available: 2.0")
        add_focus_highlight(self.version_label)
        self.installed_version_label = lv.label(self.screen)
        self.installed_version_label.set_text("Installed: 1.0")
        add_focus_highlight(self.installed_version_label)
        self.long_desc_label = lv.label(self.screen)
        self.long_desc_label.set_text("long description")
        add_focus_highlight(self.long_desc_label)
        wait_for_render(2)

    def tearDown(self):
        AppManager.is_installed_by_name = self._orig_is_installed
        AppManager.is_update_available = self._orig_is_update
        lv.screen_load(lv.obj())
        wait_for_render(2)

    def test_install_button_keeps_focus_after_rebuild(self):
        first_button = self.detail.install_button
        lv.group_focus_obj(first_button)
        wait_for_render(2)
        self.assertEqual(self.group.get_focused(), first_button)

        # What fetch_and_set_app_details() does once the description arrives.
        AppDetail.add_action_buttons(self.detail, self.buttoncont, self.detail.app)
        wait_for_render(2)

        self.assertNotEqual(self.detail.install_button, first_button)
        self.assertEqual(
            self.group.get_focused(),
            self.detail.install_button,
            "focus must stay on the install button when the details load",
        )

    def test_rebuild_does_not_steal_focus_from_description(self):
        desc = lv.label(self.screen)
        desc.set_text("long description")
        add_focus_highlight(desc)
        lv.group_focus_obj(desc)
        wait_for_render(2)
        self.assertEqual(self.group.get_focused(), desc)

        AppDetail.add_action_buttons(self.detail, self.buttoncont, self.detail.app)
        wait_for_render(2)

        self.assertEqual(
            self.group.get_focused(),
            desc,
            "a rebuild must not move focus away from the description",
        )


if __name__ == "__main__":
    unittest.main()
