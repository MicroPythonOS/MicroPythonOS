"""
test_appstore_list_build.py - Verify the store index builds the visible list
exactly once per refresh (no throwaway incremental widget pass).

Regression tests for the ~8.8s Phase-2 incremental insert pass that built
one full widget row per new app and then deleted all of them in the
mandatory full rebuild right afterwards:
- download_app_index() must never call _insert_app_list_item.
- self.apps must still end up sorted by AppStore._sort_key.
- create_apps_list() must still run once for Phase 1 and once for Phase 2.

Usage:
    python3 scripts/test_runner.py tests/test_appstore_list_build.py
"""

import json
import unittest
import sys

sys.path.insert(0, "builtin/apps/com.micropythonos.appstore")


class MockLabel:
    """Minimal stand-in for an lv.label."""

    def __init__(self):
        self._text = ""
        self._flags = set()

    def set_text(self, text):
        self._text = text

    def add_flag(self, flag):
        self._flags.add(flag)

    def remove_flag(self, flag):
        self._flags.discard(flag)

    def has_flag(self, flag):
        return flag in self._flags


class MockPrefs:
    """Minimal SharedPreferences stand-in."""

    def __init__(self):
        self._data = {}

    def get_string(self, key, default=None):
        return self._data.get(key, default)

    def edit(self):
        return self

    def put_string(self, key, value):
        self._data[key] = value
        return self

    def commit(self):
        pass


def _index_entry(slug, name):
    return {
        "slug": slug,
        "name": name,
        "description": "desc %s" % name,
        "version": "1.0",
        "categories": ["Tools"],
    }


class TestAppStoreSingleListBuild(unittest.TestCase):
    """Phase 2 must sort apps in memory and build widgets exactly once."""

    def _make_store(self):
        from appstore import AppStore

        store = AppStore()
        store.prefs = MockPrefs()
        store.please_wait_label = MockLabel()
        store.update_all_button = MockLabel()
        store.main_screen = MockLabel()
        store._refresh_in_progress = False
        store._data_loaded = False
        store._wip_apps = []
        store._has_foreground = True
        store._hide_wip = True
        store._selected_category = None
        store._builtin_fullnames = set()
        store.apps = []
        self.build_calls = []
        orig_build = store.create_apps_list

        def _counting_build():
            self.build_calls.append(1)

        store.create_apps_list = _counting_build
        self._orig_build = orig_build
        return store

    def _run_download(self, store, entries):
        import asyncio
        from mpos import App, AppManager
        import mpos.net.download_manager as dm

        # NOTE: _app_list must stay non-empty, otherwise get_app_list()
        # refreshes it from disk. The installed app is also present in the
        # index entries, so it is patched (not counted as new).
        installed = App("ExistingApp", "Pub", "desc", "", "", "",
                        "com.test.existing", "1.0")
        orig_apps = AppManager._app_list
        AppManager._app_list = [installed]
        entries = [_index_entry("com.test.existing", "ExistingApp")] + entries

        json_data = json.dumps(entries)

        async def _fake_download(url):
            return json_data

        orig_dl = dm.DownloadManager.download_url
        dm.DownloadManager.download_url = staticmethod(_fake_download)
        try:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(
                store.download_app_index("http://example.com/index.json")
            )
        finally:
            dm.DownloadManager.download_url = orig_dl
            AppManager._app_list = orig_apps

    def test_phase2_does_not_insert_widgets_incrementally(self):
        """No per-app widget insertion may happen during the index merge."""
        store = self._make_store()
        insert_calls = []
        meth = getattr(store, "_insert_app_list_item", None)
        if meth is not None:
            def _counting_insert(app, index):
                insert_calls.append(app.fullname)
            store._insert_app_list_item = _counting_insert
        self._run_download(store, [
            _index_entry("com.test.zulu", "Zulu"),
            _index_entry("com.test.alpha", "alpha"),
            _index_entry("com.test.mike", "mike"),
        ])
        self.assertEqual(insert_calls, [])
        self.assertEqual(len(store.apps), 4)

    def test_phase2_apps_end_up_sorted(self):
        """Memory-only merge must preserve the sorted order guarantee."""
        store = self._make_store()
        self._run_download(store, [
            _index_entry("com.test.zulu", "Zulu"),
            _index_entry("com.test.bang", "!Bang"),
            _index_entry("com.test.alpha", "alpha"),
        ])
        names = [a.name for a in store.apps]
        expected = sorted(names, key=store._sort_key)
        self.assertEqual(names, expected)

    def test_phase2_rebuilds_list_exactly_once(self):
        """Phase 1 + Phase 2 final rebuild: exactly two list builds total."""
        store = self._make_store()
        self._run_download(store, [
            _index_entry("com.test.zulu", "Zulu"),
            _index_entry("com.test.alpha", "alpha"),
        ])
        self.assertEqual(len(self.build_calls), 2)


if __name__ == "__main__":
    unittest.main()
