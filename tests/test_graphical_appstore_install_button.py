"""
Unit test for AppDetail install button double-click guard and button visibility.

Verifies:
- Missing download_url is ignored
- Install/uninstall button is disabled immediately on click
- Second click while action is in progress is rejected
- fetch_and_set_app_details skips button rebuild during action
- Button visibility combinations (Install/Uninstall/Update/Open)
- update_button_click sets _action_in_progress
"""

import sys
import unittest
import lvgl as lv

sys.path.insert(0, "builtin/apps/com.micropythonos.appstore")
import app_detail
AppDetail = app_detail.AppDetail

from mpos.ui.testing import wait_for_render
from mpos import TaskManager, AppManager

_ORIGINAL_IS_UPDATE_AVAILABLE = AppManager.is_update_available


class _MockApp:
    download_url = None
    fullname = "com.test.app"
    version = None


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

    def test_fetch_details_skips_rebuild_during_action(self):
        self.detail._action_in_progress = True
        self.detail.app = self.app
        self.detail.version_label = lv.label(self.screen)
        self.detail.installed_version_label = lv.label(self.screen)
        self.detail.long_desc_label = lv.label(self.screen)
        self.detail.publisher_label = lv.label(self.screen)
        self.detail.buttoncont = lv.obj(self.screen)
        self.detail.fetch_badgehub_app_details = lambda s: None
        self.detail._sync_open_button = lambda: None
        self.detail._start_icon_download = lambda: None
        self.detail._update_version_labels = lambda: None

        self._add_action_called = False
        def _mock_add_action(cont, app):
            self._add_action_called = True
        self.detail.add_action_buttons = _mock_add_action

        app_detail.AppDetail.fetch_and_set_app_details(self.detail)
        self.assertFalse(
            self._add_action_called,
            "fetch_and_set_app_details must skip add_action_buttons during action",
        )


class TestAppDetailButtonVisibility(unittest.TestCase):
    """Tests add_action_buttons output for all button visibility combinations."""

    def setUp(self):
        self.screen = lv.obj()
        self.screen.set_size(320, 240)
        lv.screen_load(self.screen)

        self.buttoncont = lv.obj(self.screen)
        self.buttoncont.set_flex_flow(lv.FLEX_FLOW.ROW)
        self.buttoncont.set_size(lv.pct(100), lv.SIZE_CONTENT)

        self.detail = type("MockDetail", (), {})()
        self.detail.action_label_install = "Install"
        self.detail.action_label_uninstall = "Uninstall"
        self.detail.install_button = None
        self.detail.install_label = None
        self.detail.update_button = None
        self.detail._open_button = None
        self.detail._sync_open_button = lambda: AppDetail._sync_open_button(self.detail)
        self.detail._sync_rate_cont = lambda: None
        self.detail._update_version_labels = lambda: None
        self.detail.set_install_label = self._mock_set_install_label
        self.detail.app = _MockApp()
        self.detail.app.fullname = "com.test.app"

    def _mock_set_install_label(self, app_fullname):
        if AppManager.is_installed_by_name(app_fullname):
            self.detail.install_label.set_text("Uninstall")
        else:
            self.detail.install_label.set_text("Install")

        self._orig_is_installed = AppManager.is_installed_by_name
        self._orig_is_update = AppManager.is_update_available

        wait_for_render(2)

    def tearDown(self):
        AppManager.is_installed_by_name = self._orig_is_installed
        AppManager.is_update_available = self._orig_is_update
        lv.screen_load(lv.obj())
        wait_for_render(2)

    def _assert_install_label(self, expected):
        self.assertEqual(self.detail.install_label.get_text(), expected)

    def _button_visible(self, button):
        return button is not None and not button.has_flag(lv.obj.FLAG.HIDDEN)

    def test_not_installed_no_version(self):
        """Not installed, no version info -> only Install button, Open hidden, no Update."""
        AppManager.is_installed_by_name = lambda fn: False
        AppManager.is_update_available = lambda fn, v: False
        self.detail.app.version = None

        AppDetail.add_action_buttons(self.detail, self.buttoncont, self.detail.app)

        self._assert_install_label("Install")
        self.assertIsNotNone(self.detail.install_button)
        self.assertIsNone(self.detail.update_button)
        self.assertFalse(self._button_visible(self.detail._open_button))

    def test_not_installed_but_version_available_no_update(self):
        """Not installed, version fetched, no update -> Install only, Open hidden."""
        AppManager.is_installed_by_name = lambda fn: False
        AppManager.is_update_available = lambda fn, v: False
        self.detail.app.version = "2.0"

        AppDetail.add_action_buttons(self.detail, self.buttoncont, self.detail.app)

        self._assert_install_label("Install")
        self.assertIsNone(self.detail.update_button)
        self.assertFalse(self._button_visible(self.detail._open_button))

    def test_installed_no_update(self):
        """Installed, no update -> Uninstall + Open, no Update."""
        AppManager.is_installed_by_name = lambda fn: True
        AppManager.is_update_available = lambda fn, v: False
        self.detail.app.version = "1.0"

        AppDetail.add_action_buttons(self.detail, self.buttoncont, self.detail.app)

        self._assert_install_label("Uninstall")
        self.assertIsNone(self.detail.update_button)
        self.assertTrue(self._button_visible(self.detail._open_button))

    def test_installed_with_update(self):
        """Installed, update available -> Uninstall + Update + Open."""
        AppManager.is_installed_by_name = lambda fn: True
        AppManager.is_update_available = lambda fn, v: True
        self.detail.app.version = "2.0"

        AppDetail.add_action_buttons(self.detail, self.buttoncont, self.detail.app)

        self._assert_install_label("Uninstall")
        self.assertIsNotNone(self.detail.update_button)
        self.assertTrue(self._button_visible(self.detail.update_button))
        self.assertTrue(self._button_visible(self.detail._open_button))

    def test_install_button_label_changes_after_install_simulation(self):
        """After install completes, add_action_buttons shows Uninstall + Open."""
        AppManager.is_installed_by_name = lambda fn: False
        AppManager.is_update_available = lambda fn, v: False
        self.detail.app.version = "2.0"

        AppDetail.add_action_buttons(self.detail, self.buttoncont, self.detail.app)
        self._assert_install_label("Install")
        self.assertFalse(self._button_visible(self.detail._open_button))

        AppManager.is_installed_by_name = lambda fn: True
        AppDetail.add_action_buttons(self.detail, self.buttoncont, self.detail.app)
        self._assert_install_label("Uninstall")
        self.assertTrue(self._button_visible(self.detail._open_button))

    def test_labels_after_uninstall(self):
        """After uninstall, add_action_buttons shows Install, Open hidden."""
        AppManager.is_installed_by_name = lambda fn: True
        AppManager.is_update_available = lambda fn, v: False
        self.detail.app.version = "2.0"

        AppDetail.add_action_buttons(self.detail, self.buttoncont, self.detail.app)
        self._assert_install_label("Uninstall")
        self.assertTrue(self._button_visible(self.detail._open_button))

        AppManager.is_installed_by_name = lambda fn: False
        AppDetail.add_action_buttons(self.detail, self.buttoncont, self.detail.app)
        self._assert_install_label("Install")
        self.assertFalse(self._button_visible(self.detail._open_button))

    def test_open_button_in_same_container(self):
        """Open button is a child of buttoncont, not a floating widget."""
        AppManager.is_installed_by_name = lambda fn: True
        AppManager.is_update_available = lambda fn, v: False
        self.detail.app.version = "1.0"

        AppDetail.add_action_buttons(self.detail, self.buttoncont, self.detail.app)

        parent = self.detail._open_button.get_parent()
        self.assertIs(parent, self.buttoncont, "Open button must be child of buttoncont")

    def test_update_button_click_sets_action_in_progress(self):
        self.detail._action_in_progress = False
        self.detail.install_button = lv.button(self.screen)
        self.detail.install_label = lv.label(self.detail.install_button)
        self.detail.update_button = lv.button(self.screen)
        async def _noop(*args, **kwargs):
            pass
        self.detail.download_and_install = _noop

        app = _MockApp()
        app.download_url = "https://example.com/app.zip"
        app.fullname = "com.test.app"

        orig = TaskManager.create_task
        TaskManager.create_task = lambda c: None
        try:
            AppDetail.update_button_click(self.detail, app)
        finally:
            TaskManager.create_task = orig

        self.assertTrue(
            self.detail._action_in_progress,
            "update_button_click must set _action_in_progress = True",
        )


class TestCompareVersions(unittest.TestCase):
    """Directly test AppManager.compare_versions with real data."""

    def test_compare_versions_041_vs_040(self):
        """0.4.1 > 0.4.0."""
        self.assertTrue(
            AppManager.compare_versions("0.4.1", "0.4.0"),
            "0.4.1 must be greater than 0.4.0",
        )

    def test_compare_versions_equal(self):
        """Same version is not an update."""
        self.assertFalse(AppManager.compare_versions("0.4.0", "0.4.0"))

    def test_compare_versions_older_remote(self):
        """Store version older than installed is not an update."""
        self.assertFalse(AppManager.compare_versions("0.3.9", "0.4.0"))

    def test_compare_versions_different_lengths(self):
        """1.2 > 1.1.9."""
        self.assertTrue(AppManager.compare_versions("1.2", "1.1.9"))

    def test_compare_versions_simple(self):
        """2.0.0 > 1.0.0."""
        self.assertTrue(AppManager.compare_versions("2.0.0", "1.0.0"))


class TestAppDetailRealUpdateDetection(unittest.TestCase):
    """Tests add_action_buttons with the real AppManager.is_update_available
    by registering an installed app directly in the AppManager cache."""

    TEST_FULLNAME = "com.test.showfonts"
    TEST_FULLNAME2 = "com.test.other"

    def setUp(self):
        self.screen = lv.obj()
        self.screen.set_size(320, 240)
        lv.screen_load(self.screen)

        self.buttoncont = lv.obj(self.screen)
        self.buttoncont.set_flex_flow(lv.FLEX_FLOW.ROW)
        self.buttoncont.set_size(lv.pct(100), lv.SIZE_CONTENT)

        self.detail = type("MockDetail", (), {})()
        self.detail.action_label_install = "Install"
        self.detail.action_label_uninstall = "Uninstall"
        self.detail.install_button = None
        self.detail.install_label = None
        self.detail.update_button = None
        self.detail._open_button = None
        self.detail._sync_open_button = lambda: AppDetail._sync_open_button(self.detail)
        self.detail._sync_rate_cont = lambda: None
        self.detail._update_version_labels = lambda: AppDetail._update_version_labels(self.detail)
        self.detail._read_installed_version = AppDetail._read_installed_version
        self.detail.installed_version_label = lv.label(self.screen)
        self.detail.version_label = lv.label(self.screen)
        self.detail.set_install_label = self._mock_set_install_label
        self.detail.app = _MockApp()
        self.detail.app.fullname = self.TEST_FULLNAME

        self._orig_is_installed = AppManager.is_installed_by_name
        AppManager.is_update_available = _ORIGINAL_IS_UPDATE_AVAILABLE

        self._saved_by_fullname = dict(AppManager._by_fullname)
        self._saved_app_list = list(AppManager._app_list)

        wait_for_render(2)

    def tearDown(self):
        AppManager.is_installed_by_name = self._orig_is_installed
        AppManager.is_update_available = _ORIGINAL_IS_UPDATE_AVAILABLE
        AppManager._by_fullname = self._saved_by_fullname
        AppManager._app_list = self._saved_app_list
        lv.screen_load(lv.obj())
        wait_for_render(2)

    def _mock_set_install_label(self, app_fullname):
        if AppManager.is_installed_by_name(app_fullname):
            self.detail.install_label.set_text("Uninstall")
        else:
            self.detail.install_label.set_text("Install")

    def _register_installed(self, fullname, version="0.4.0"):
        from mpos.app.app import App
        installed = App(
            name="Test",
            fullname=fullname,
            version=version,
            installed_path="apps/%s" % fullname,
        )
        AppManager._by_fullname[fullname] = installed
        if not AppManager._app_list:
            AppManager._app_list = [installed]
        else:
            AppManager._app_list.append(installed)
        return installed

    def _assert_install_label(self, expected):
        self.assertEqual(self.detail.install_label.get_text(), expected)

    def _button_visible(self, button):
        return button is not None and not button.has_flag(lv.obj.FLAG.HIDDEN)

    def test_is_update_available_with_real_cache(self):
        """Directly verify is_update_available returns True when store > installed."""
        self._register_installed(self.TEST_FULLNAME, "0.4.0")
        self.assertTrue(
            AppManager.is_update_available(self.TEST_FULLNAME, "0.4.1"),
            "is_update_available must return True when 0.4.1 > 0.4.0",
        )

    def test_update_button_shown_when_store_version_is_newer(self):
        """Installed v0.4.0, store has v0.4.1 -> real is_update_available returns True -> Update shown."""
        self._register_installed(self.TEST_FULLNAME, "0.4.0")

        AppManager.is_installed_by_name = lambda fn: True

        self.detail.app = _MockApp()
        self.detail.app.fullname = self.TEST_FULLNAME
        self.detail.app.version = "0.4.1"

        AppDetail.add_action_buttons(self.detail, self.buttoncont, self.detail.app)

        self._assert_install_label("Uninstall")
        self.assertIsNotNone(
            self.detail.update_button,
            "Update button must be created when store version > installed version",
        )
        self.assertTrue(
            self._button_visible(self.detail.update_button),
            "Update button must be visible when update is available",
        )
        self.assertTrue(self._button_visible(self.detail._open_button))

    def test_no_update_button_when_installed_not_in_cache(self):
        """Installed (by filesystem) but NOT in _by_fullname -> no Update button."""
        from mpos import AppManager as AM
        AM._by_fullname.pop(self.TEST_FULLNAME2, None)

        AppManager.is_installed_by_name = lambda fn: True

        self.detail.app = _MockApp()
        self.detail.app.fullname = self.TEST_FULLNAME2
        self.detail.app.version = "0.4.1"

        AppDetail.add_action_buttons(self.detail, self.buttoncont, self.detail.app)

        self._assert_install_label("Uninstall")
        self.assertIsNone(
            self.detail.update_button,
            "Update button must NOT be created when app is not in _by_fullname cache",
        )
        self.assertTrue(self._button_visible(self.detail._open_button))

    def test_update_button_shows_immediately_when_version_from_index(self):
        """If the store index already includes the version (not BadgeHub),
        the Update button should appear even before detail fetch."""
        self._register_installed(self.TEST_FULLNAME, "0.4.0")

        AppManager.is_installed_by_name = lambda fn: True

        self.detail.app = _MockApp()
        self.detail.app.fullname = self.TEST_FULLNAME
        self.detail.app.version = "0.4.1"

        AppDetail.add_action_buttons(self.detail, self.buttoncont, self.detail.app)

        self.assertIsNotNone(
            self.detail.update_button,
            "Update button must be created when store index has version and is_update works",
        )
        self.assertTrue(self._button_visible(self.detail.update_button))

    def test_remote_version_takes_precedence_over_app_version(self):
        """_remote_version from BadgeHub summary takes precedence over app.version
        when the App object is a reused installed-app reference."""
        self._register_installed(self.TEST_FULLNAME, "0.4.0")

        AppManager.is_installed_by_name = lambda fn: True

        self.detail.app = _MockApp()
        self.detail.app.fullname = self.TEST_FULLNAME
        self.detail.app.version = "0.4.0"        # installed version (reused object)
        self.detail.app._remote_version = "0.4.1"  # from BadgeHub summary

        AppDetail.add_action_buttons(self.detail, self.buttoncont, self.detail.app)

        self.assertIsNotNone(
            self.detail.update_button,
            "Update button must be created when _remote_version > installed version",
        )
        self.assertTrue(self._button_visible(self.detail.update_button))

    def test_no_update_button_when_app_version_equals_installed(self):
        """Regression: without _remote_version, when app.version == installed version
        (the reused-object bug), no Update button appears."""
        self._register_installed(self.TEST_FULLNAME, "0.4.0")

        AppManager.is_installed_by_name = lambda fn: True

        self.detail.app = _MockApp()
        self.detail.app.fullname = self.TEST_FULLNAME
        self.detail.app.version = "0.4.0"  # same as installed — no _remote_version

        AppDetail.add_action_buttons(self.detail, self.buttoncont, self.detail.app)

        self.assertIsNone(
            self.detail.update_button,
            "No Update button when app.version equals installed version (no _remote_version)",
        )
        self.assertTrue(self._button_visible(self.detail._open_button))

    def test_update_button_persists_after_detail_fetch_simulation(self):
        """add_action_buttons called a second time (as fetch_and_set_app_details does
        after the async detail fetch) still shows the Update button.
        The detail fetch no longer overwrites app.version (prevents cache corruption)."""
        self._register_installed(self.TEST_FULLNAME, "0.4.0")

        AppManager.is_installed_by_name = lambda fn: True

        self.detail.app = _MockApp()
        self.detail.app.fullname = self.TEST_FULLNAME
        self.detail.app.version = "0.4.0"
        self.detail.app._remote_version = "0.4.1"

        # First call — simulates onCreate
        AppDetail.add_action_buttons(self.detail, self.buttoncont, self.detail.app)
        self.assertIsNotNone(self.detail.update_button)
        self.assertTrue(self._button_visible(self.detail.update_button))

        # Second call — simulates fetch_and_set_app_details re-calling add_action_buttons
        # (detail fetch no longer overwrites app.version, so nothing changes)
        AppDetail.add_action_buttons(self.detail, self.buttoncont, self.detail.app)
        self.assertIsNotNone(
            self.detail.update_button,
            "Update button must persist after detail-fetch rebuild",
        )
        self.assertTrue(self._button_visible(self.detail.update_button))

    def test_installed_version_read_from_filesystem_not_cache(self):
        """_read_installed_version reads from MANIFEST.JSON filesystem,
        bypassing the shared-object cache that can be corrupted."""
        from mpos.app.app import App
        installed = App(
            name="Test", fullname=self.TEST_FULLNAME, version="0.3.5",
            installed_path="apps/%s" % self.TEST_FULLNAME,
        )
        AppManager._by_fullname[self.TEST_FULLNAME] = installed
        if not AppManager._app_list:
            AppManager._app_list = [installed]

        import ujson
        import os as _os
        test_dir = "apps/com.test.showfonts"
        try:
            _os.stat(test_dir)
        except OSError:
            _os.mkdir(test_dir)
        try:
            with open("%s/MANIFEST.JSON" % test_dir, "w") as f:
                f.write(ujson.dumps({"name": "Test", "fullname": "com.test.showfonts", "version": "0.4.0"}))

            ver = AppDetail._read_installed_version("com.test.showfonts")
            self.assertEqual(ver, "0.4.0",
                "Must read 0.4.0 from filesystem, not cache (which has 0.3.5)")
        finally:
            _os.remove("%s/MANIFEST.JSON" % test_dir)
            _os.rmdir(test_dir)
