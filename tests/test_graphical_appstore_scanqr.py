"""
Graphical test for the AppStore "Scan QR" deep-link flow.

Verifies that:
- the Scan QR button exists in the AppStore top bar
- a scanned store link for an installed app opens its detail screen
- a scanned non-link QR shows the "Not an app link" dialog
- a scanned link for an unknown app shows the "No connection" dialog when
  the index cannot be downloaded
- launching the AppStore with a deeplink_fullname intent extra opens the
  detail screen once the index refresh finishes

The store index download is stubbed to fail so the tests are deterministic
without network access: installed (non-builtin) apps are still listed by
phase 1 of download_app_index, which is all the deep-link needs here.
The LVGL test process does not pump the TaskManager queue, so (like
test_appstore_async_refresh.py) created coroutines are captured and driven
to completion with run_until_complete.
"""

import unittest

import lvgl as lv

from mpos import AppManager, DownloadManager, Intent, TaskManager
from mpos.ui import QR_SYMBOL
from mpos.ui.testing import find_label_with_text, wait_for_render

HELLOWORLD = "com.micropythonos.helloworld"
STORE_LINK = "https://badgehub.eu/page/project/" + HELLOWORLD


def _get_top_activity():
    import mpos.ui
    if not mpos.ui.screen_stack:
        return None
    activity, _, _, _ = mpos.ui.screen_stack[-1]
    return activity


class TestGraphicalAppStoreScanQR(unittest.TestCase):

    def setUp(self):
        import asyncio
        asyncio.new_event_loop()
        AppManager.refresh_apps()

        self._saved_download_url = DownloadManager.download_url

        async def _no_network(url, **kwargs):
            raise OSError("no network in test")
        DownloadManager.download_url = staticmethod(_no_network)

        # Capture coroutines instead of scheduling them; _drain() runs them.
        self._captured_tasks = []
        self._saved_create_task = TaskManager.create_task
        captured = self._captured_tasks

        def _capture_task(coro):
            captured.append(coro)
            return None
        TaskManager.create_task = _capture_task

        self._top_children_before = lv.layer_top().get_child_count()

    def tearDown(self):
        TaskManager.create_task = self._saved_create_task
        DownloadManager.download_url = self._saved_download_url
        # Remove any msgbox the test left on the top layer.
        top = lv.layer_top()
        while top.get_child_count() > self._top_children_before:
            top.get_child(top.get_child_count() - 1).delete()
        try:
            from mpos.ui import back_screen
            for _ in range(3):
                back_screen()
                wait_for_render(iterations=5)
        except Exception:
            pass

    def _drain(self):
        """Run every captured TaskManager coroutine to completion."""
        import asyncio
        loop = asyncio.get_event_loop()
        while self._captured_tasks:
            coro = self._captured_tasks.pop(0)
            try:
                loop.run_until_complete(coro)
            except Exception as e:
                print("drained task raised:", e)
        wait_for_render(iterations=10)

    def _start_appstore(self, intent=None):
        AppManager.start_app("com.micropythonos.appstore", intent=intent)
        wait_for_render(iterations=10)
        self._drain()

    def test_scanqr_button_exists(self):
        self._start_appstore()
        label = find_label_with_text(lv.screen_active(), QR_SYMBOL)
        self.assertIsNotNone(label, "Scan QR button should be in the top bar")

    def test_scanned_store_link_opens_detail(self):
        self._start_appstore()
        appstore = _get_top_activity()
        self.assertIsNotNone(appstore)
        appstore.scanqr_result_callback({"result_code": True, "data": STORE_LINK})
        self._drain()
        label = find_label_with_text(lv.screen_active(), "HelloWorld")
        self.assertIsNotNone(label, "detail screen for HelloWorld should be open")

    def test_scanned_uppercase_store_link_opens_detail(self):
        # QR alphanumeric mode uppercases the payload.
        self._start_appstore()
        appstore = _get_top_activity()
        appstore.scanqr_result_callback({"result_code": True, "data": STORE_LINK.upper()})
        self._drain()
        self.assertIsNotNone(find_label_with_text(lv.screen_active(), "HelloWorld"))

    def test_scanned_garbage_shows_dialog(self):
        self._start_appstore()
        appstore = _get_top_activity()
        appstore.scanqr_result_callback({"result_code": True, "data": "WIFI:T:WPA;S:x;P:y;;"})
        self._drain()
        label = find_label_with_text(lv.layer_top(), "Not an app link")
        self.assertIsNotNone(label, "non-link QR should show the 'Not an app link' dialog")

    def test_scanned_unknown_app_shows_not_found(self):
        self._start_appstore()
        appstore = _get_top_activity()
        appstore.scanqr_result_callback({
            "result_code": True,
            "data": "https://badgehub.eu/page/project/com.example.does_not_exist",
        })
        self._drain()
        # Index refresh fails (stubbed offline), so the "No connection" dialog shows.
        label = find_label_with_text(lv.layer_top(), "No connection")
        self.assertIsNotNone(label, "unknown app with no index should show the 'No connection' dialog")

    def test_deeplink_to_installed_app_resolves_before_index_download(self):
        # A deep link to an installed app must open its detail screen from
        # phase 1 (local app list) alone — by the time the index download
        # starts, the pending deep link should already be consumed.
        pending_at_download = []

        async def _recording_download(url, **kwargs):
            import mpos.ui
            # Only record the app-index download; opening the detail screen also
            # fetches BadgeHub project details, which is unrelated to the timing
            # this test is checking.
            if "project-summaries" not in url:
                raise OSError("no network in test")
            for entry in mpos.ui.screen_stack:
                activity = entry[0]
                if activity.__class__.__name__ == "AppStore":
                    pending_at_download.append(activity._pending_deeplink)
            raise OSError("no network in test")
        DownloadManager.download_url = staticmethod(_recording_download)

        intent = Intent(extras={"deeplink_fullname": HELLOWORLD})
        self._start_appstore(intent=intent)
        self.assertIsNotNone(find_label_with_text(lv.screen_active(), "HelloWorld"))
        self.assertEqual(pending_at_download, [None],
                         "deep link should be resolved before the index download runs")

    def test_deeplink_intent_opens_detail(self):
        intent = Intent(extras={"deeplink_fullname": HELLOWORLD})
        self._start_appstore(intent=intent)
        label = find_label_with_text(lv.screen_active(), "HelloWorld")
        self.assertIsNotNone(label, "deeplink intent should open the HelloWorld detail screen")


if __name__ == "__main__":
    unittest.main()
