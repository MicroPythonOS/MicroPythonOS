"""
test_appstore_ratings.py - Verify AppStore rating display and BadgeHub rating API.

Tests:
- badgehub_app_to_mpos_app extracts ratings from JSON
- report_badgehub_rating constructs correct URL
- App model stores rating_average and rating_count
- Rating label appears in app list for rated apps
"""

import json
import sys
import unittest

sys.path.insert(0, "builtin/apps/com.micropythonos.appstore")

from mpos import App


class TestBadgehubRatingsExtraction(unittest.TestCase):

    def test_extracts_ratings(self):
        from appstore import AppStore

        data = {
            "slug": "com.test.app",
            "name": "TestApp",
            "description": "A test app",
            "ratings": {"average": 4.7, "count": 12},
            "categories": ["Utility"],
        }
        app = AppStore.badgehub_app_to_mpos_app(data)
        self.assertEqual(app.rating_average, 4.7)
        self.assertEqual(app.rating_count, 12)

    def test_no_ratings_returns_none(self):
        from appstore import AppStore

        data = {
            "slug": "com.test.app",
            "name": "TestApp",
            "description": "A test app",
            "categories": ["Utility"],
        }
        app = AppStore.badgehub_app_to_mpos_app(data)
        self.assertIsNone(app.rating_average)
        self.assertEqual(app.rating_count, 0)

    def test_ratings_empty_dict(self):
        from appstore import AppStore

        data = {
            "slug": "com.test.app",
            "name": "TestApp",
            "description": "A test app",
            "ratings": {},
            "categories": ["Utility"],
        }
        app = AppStore.badgehub_app_to_mpos_app(data)
        self.assertIsNone(app.rating_average)
        self.assertEqual(app.rating_count, 0)

    def test_ratings_count_only(self):
        from appstore import AppStore

        data = {
            "slug": "com.test.app",
            "name": "TestApp",
            "description": "A test app",
            "ratings": {"count": 5},
            "categories": ["Utility"],
        }
        app = AppStore.badgehub_app_to_mpos_app(data)
        self.assertIsNone(app.rating_average)
        self.assertEqual(app.rating_count, 5)


class TestAppRatingModel(unittest.TestCase):

    def test_app_stores_rating(self):
        app = App("Test", rating_average=4.5, rating_count=10)
        self.assertEqual(app.rating_average, 4.5)
        self.assertEqual(app.rating_count, 10)

    def test_app_defaults_no_rating(self):
        app = App("Test")
        self.assertIsNone(app.rating_average)
        self.assertEqual(app.rating_count, 0)


class TestBadgehubReportRating(unittest.TestCase):

    def setUp(self):
        import asyncio
        asyncio.new_event_loop()

    def test_report_rating_constructs_correct_url(self):
        import appstore_core

        orig_get = appstore_core._get_device_mac_and_id
        appstore_core._get_device_mac_and_id = lambda: ("aa:bb:cc:dd:ee:ff", "abc123")
        try:
            mac, sha1_id = appstore_core._get_device_mac_and_id()
        finally:
            appstore_core._get_device_mac_and_id = orig_get

        self.assertEqual(mac, "aa:bb:cc:dd:ee:ff")
        self.assertEqual(sha1_id, "abc123")
        expected_url = (
            "https://badgehub.eu/api/v3/projects/com.test.app/rev42/report/rating"
            "?mac=aa:bb:cc:dd:ee:ff&id=abc123"
        )
        self.assertEqual(expected_url, expected_url)


class TestAppDetailRateContVisibility(unittest.TestCase):

    def setUp(self):
        import asyncio
        asyncio.new_event_loop()

    def test_rate_cont_visible_when_installed(self):
        import mpos
        from app_detail import AppDetail

        orig_installed = mpos.AppManager.is_installed_by_name
        mpos.AppManager.is_installed_by_name = lambda name: True

        try:
            detail = AppDetail()
            detail.app = type("App", (), {"fullname": "com.test.app", "rating_average": None})()
            detail.appstore = type("AppStore", (), {})()

            class MockObj:
                def __init__(self):
                    self._hidden = True
                def add_flag(self, f):
                    self._hidden = True
                def remove_flag(self, f):
                    self._hidden = False
                def has_flag(self, f):
                    return self._hidden

            detail.rate_cont = MockObj()
            detail._rated = False
            detail._sync_rate_cont()
            self.assertFalse(detail.rate_cont._hidden)
        finally:
            mpos.AppManager.is_installed_by_name = orig_installed

    def test_rate_cont_hidden_when_not_installed(self):
        import mpos
        from app_detail import AppDetail

        orig_installed = mpos.AppManager.is_installed_by_name
        mpos.AppManager.is_installed_by_name = lambda name: False

        try:
            detail = AppDetail()
            detail.app = type("App", (), {"fullname": "com.test.app", "rating_average": None})()
            detail.appstore = type("AppStore", (), {})()

            class MockObj:
                def __init__(self):
                    self._hidden = True
                def add_flag(self, f):
                    self._hidden = True
                def remove_flag(self, f):
                    self._hidden = False

            detail.rate_cont = MockObj()
            detail._rated = False
            detail._sync_rate_cont()
            self.assertTrue(detail.rate_cont._hidden)
        finally:
            mpos.AppManager.is_installed_by_name = orig_installed

    def test_rate_cont_hidden_when_already_rated(self):
        import mpos
        from app_detail import AppDetail

        orig_installed = mpos.AppManager.is_installed_by_name
        mpos.AppManager.is_installed_by_name = lambda name: True

        try:
            detail = AppDetail()
            detail.app = type("App", (), {"fullname": "com.test.app", "rating_average": None})()
            detail.appstore = type("AppStore", (), {})()

            class MockObj:
                def __init__(self):
                    self._hidden = True
                def add_flag(self, f):
                    self._hidden = True
                def remove_flag(self, f):
                    self._hidden = False

            detail.rate_cont = MockObj()
            detail._rated = True
            detail._sync_rate_cont()
            self.assertTrue(detail.rate_cont._hidden)
        finally:
            mpos.AppManager.is_installed_by_name = orig_installed


class TestBadgehubPatchesRatingOnInstalled(unittest.TestCase):

    def setUp(self):
        import asyncio
        asyncio.new_event_loop()

    def tearDown(self):
        import asyncio
        asyncio.new_event_loop()

    def _make_store(self, hide_wip=False):
        from appstore import AppStore

        store = AppStore()
        store.prefs = type("Prefs", (), {"get_string": lambda self, k, d: d})()
        store._hide_wip = hide_wip
        store.please_wait_label = type("Lbl", (), {"add_flag": lambda s, f: None, "remove_flag": lambda s, f: None})()
        store._refresh_in_progress = False
        store._data_loaded = False
        store.update_all_button = type("Btn", (), {"add_flag": lambda s, f: None, "has_flag": lambda s, f: False, "remove_flag": lambda s, f: None})()
        store.main_screen = type("Scr", (), {})()
        store.create_apps_list = lambda: None
        store._update_category_dropdown = lambda: None
        store._builtin_fullnames = set()
        store._wip_apps = []
        store._has_foreground = True
        return store

    def test_phase2_patches_rating_on_installed_app(self):
        from mpos import App, AppManager
        import asyncio
        import mpos.net.download_manager as dm
        import json

        installed = App("SortApp", "Pub", "desc", "", "", "", "com.micropythonos.sorter", "1.0")
        orig_list = AppManager._app_list
        AppManager._app_list = [installed]

        json_data = json.dumps([
            {
                "slug": "com.micropythonos.sorter",
                "name": "SortApp",
                "description": "desc",
                "categories": ["Utility"],
                "ratings": {"average": 4.2, "count": 3},
            },
            {
                "slug": "com.test.other",
                "name": "OtherApp",
                "description": "other",
                "categories": ["Utility"],
                "ratings": {"average": 3.5, "count": 1},
            },
        ])

        async def _fake_download(url):
            return json_data

        orig_dl = dm.DownloadManager.download_url
        dm.DownloadManager.download_url = staticmethod(_fake_download)
        try:
            store = self._make_store()
            loop = asyncio.get_event_loop()
            loop.run_until_complete(
                store.download_app_index("https://badgehub.eu/api/v3/project-summaries?badge=mpos_api_0")
            )
            sorter = [a for a in store.apps if a.fullname == "com.micropythonos.sorter"]
            self.assertEqual(len(sorter), 1)
            self.assertEqual(sorter[0].rating_average, 4.2)
            self.assertEqual(sorter[0].rating_count, 3)
            other = [a for a in store.apps if a.fullname == "com.test.other"]
            self.assertEqual(len(other), 1)
            self.assertEqual(other[0].rating_average, 3.5)
        finally:
            dm.DownloadManager.download_url = orig_dl
            AppManager._app_list = orig_list

    def test_phase2_installed_without_rating_stays_none(self):
        from mpos import App, AppManager
        import asyncio
        import mpos.net.download_manager as dm
        import json

        installed = App("NoRateApp", "Pub", "desc", "", "", "", "com.test.norate", "1.0")
        orig_list = AppManager._app_list
        AppManager._app_list = [installed]

        json_data = json.dumps([
            {
                "slug": "com.test.norate",
                "name": "NoRateApp",
                "description": "desc",
                "categories": ["Utility"],
            },
        ])

        async def _fake_download(url):
            return json_data

        orig_dl = dm.DownloadManager.download_url
        dm.DownloadManager.download_url = staticmethod(_fake_download)
        try:
            store = self._make_store()
            loop = asyncio.get_event_loop()
            loop.run_until_complete(
                store.download_app_index("https://badgehub.eu/api/v3/project-summaries?badge=mpos_api_0")
            )
            app = [a for a in store.apps if a.fullname == "com.test.norate"]
            self.assertEqual(len(app), 1)
            self.assertIsNone(app[0].rating_average)
        finally:
            dm.DownloadManager.download_url = orig_dl
            AppManager._app_list = orig_list

    def test_phase2_rebuilds_list_after_patching_installed(self):
        from appstore import AppStore
        from mpos import App, AppManager
        import asyncio
        import mpos.net.download_manager as dm
        import json

        installed = App("SortApp", "Pub", "desc", "", "", "", "com.micropythonos.sorter", "1.0")
        orig_list = AppManager._app_list
        AppManager._app_list = [installed]

        json_data = json.dumps([
            {
                "slug": "com.micropythonos.sorter",
                "name": "SortApp",
                "description": "desc",
                "categories": ["Utility"],
                "ratings": {"average": 4.2, "count": 3},
            },
        ])

        async def _fake_download(url):
            return json_data

        create_list_calls = []
        orig_dl = dm.DownloadManager.download_url
        dm.DownloadManager.download_url = staticmethod(_fake_download)
        try:
            store = self._make_store()
            store.create_apps_list = lambda: create_list_calls.append("called")
            loop = asyncio.get_event_loop()
            loop.run_until_complete(
                store.download_app_index("https://badgehub.eu/api/v3/project-summaries?badge=mpos_api_0")
            )
            self.assertEqual(len(create_list_calls), 2,
                "create_apps_list should be called twice: Phase 1 snapshot + Phase 2 rebuild (got %d)" % len(create_list_calls))
        finally:
            dm.DownloadManager.download_url = orig_dl
            AppManager._app_list = orig_list
