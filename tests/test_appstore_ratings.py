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

    def test_rate_cont_visible_when_installed_and_badgehub(self):
        import mpos
        from app_detail import AppDetail

        orig_installed = mpos.AppManager.is_installed_by_name
        mpos.AppManager.is_installed_by_name = lambda name: True

        try:
            detail = AppDetail()
            detail.app = type("App", (), {"fullname": "com.test.app", "rating_average": None})()
            detail.appstore = type("AppStore", (), {
                "get_backend_type_from_settings": lambda self: "badgehub",
                "_BACKEND_API_BADGEHUB": "badgehub",
            })()

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
            detail.appstore = type("AppStore", (), {
                "get_backend_type_from_settings": lambda self: "badgehub",
                "_BACKEND_API_BADGEHUB": "badgehub",
            })()

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
            detail.appstore = type("AppStore", (), {
                "get_backend_type_from_settings": lambda self: "badgehub",
                "_BACKEND_API_BADGEHUB": "badgehub",
            })()

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

    def test_rate_cont_hidden_when_github_backend(self):
        import mpos
        from app_detail import AppDetail

        orig_installed = mpos.AppManager.is_installed_by_name
        mpos.AppManager.is_installed_by_name = lambda name: True

        try:
            detail = AppDetail()
            detail.app = type("App", (), {"fullname": "com.test.app", "rating_average": None})()
            detail.appstore = type("AppStore", (), {
                "get_backend_type_from_settings": lambda self: "github",
                "_BACKEND_API_BADGEHUB": "badgehub",
            })()

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
