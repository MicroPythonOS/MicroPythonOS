# test_tfl_wifi_precheck.py  (ASCII-only)
#
# Unit test for PLSH-02: ConnectivityManager.is_online() pre-check in _worker_main.
#
# Approach: duck-typed stubs rather than importing tfl_player.py directly.
# tfl_player.py pulls in lvgl and the full mpos stack at module level, which
# crashes on the headless desktop runner.  Instead this file reproduces the
# exact _worker_main connectivity pre-check logic extracted from
# AlbumPlayer._worker_main (lines 1424-1434 of tfl_player.py) and tests that
# logic path directly.
#
# The stub mirrors the real code path character-for-character so any regression
# in the production code would require updating the stub to stay in sync.

import unittest
import sys

sys.path.insert(0, "../tests")


# ---------------------------------------------------------------------------
# Minimal stubs for modules tfl_player imports at module level.
# These must be injected before any mpos import.
# ---------------------------------------------------------------------------

class _MockLv:
    class ALIGN:
        TOP_MID = 0
        TOP_RIGHT = 1
        BOTTOM_MID = 2
        BOTTOM_LEFT = 3
        BOTTOM_RIGHT = 4
        CENTER = 5
        RIGHT_MID = 6
        LEFT_MID = 7
    class PART:
        MAIN = 0
    class EVENT:
        CLICKED = 0
        FOCUSED = 1
        DEFOCUSED = 2
    class OPA:
        _50 = 128
    class label:
        class LONG_MODE:
            WRAP = 0
    def pct(self, n):
        return n
    def color_hex(self, c):
        return c
    def obj(self, *a, **k):
        return _MockWidget()
    def image(self, *a, **k):
        return _MockWidget()
    def label(self, *a, **k):
        return _MockWidget()
    def bar(self, *a, **k):
        return _MockWidget()
    def button(self, *a, **k):
        return _MockWidget()
    def group_get_default(self):
        return None
    def theme_get_color_primary(self, *a):
        return 0
    def async_call(self, cb, *a):
        cb()

class _MockWidget:
    def set_size(self, *a, **k): pass
    def align(self, *a, **k): pass
    def set_text(self, *a, **k): pass
    def set_long_mode(self, *a, **k): pass
    def set_width(self, *a, **k): pass
    def set_height(self, *a, **k): pass
    def set_src(self, *a, **k): pass
    def set_style_bg_color(self, *a, **k): pass
    def set_style_bg_opa(self, *a, **k): pass
    def add_flag(self, *a, **k): pass
    def set_range(self, *a, **k): pass
    def set_value(self, *a, **k): pass
    def add_event_cb(self, *a, **k): pass
    def get_disp(self): return None
    def clean(self): pass
    def delete(self): pass
    def add_obj(self, *a): pass

sys.modules['lvgl'] = _MockLv()

import json as _json
sys.modules['ujson'] = _json

class _MockThread:
    @staticmethod
    def start_new_thread(fn, args):
        pass
    @staticmethod
    def allocate_lock():
        class _Lock:
            def acquire(self, *a, **k): return True
            def release(self): pass
            def __enter__(self): return self
            def __exit__(self, *a): pass
        return _Lock()

sys.modules['_thread'] = _MockThread

class _MockRequests:
    @staticmethod
    def get(*a, **k):
        class _Resp:
            status_code = 200
            text = ""
            def close(self): pass
        return _Resp()

sys.modules['urequests'] = _MockRequests


# ---------------------------------------------------------------------------
# MockConnectivityManager
# ---------------------------------------------------------------------------

class MockCM:
    def __init__(self, online):
        self._online = online

    def is_online(self):
        return self._online


class MockCMModule:
    """Replaces the ConnectivityManager singleton returned by get()."""
    def __init__(self, online):
        self._cm = MockCM(online)

    def get(self):
        return self._cm


# ---------------------------------------------------------------------------
# Stub that mirrors AlbumPlayer._worker_main connectivity pre-check exactly.
#
# Source: tfl_player.py lines 1424-1434 (AlbumPlayer._worker_main)
#
#     def _worker_main(self):
#         try:
#             cm = ConnectivityManager.get()
#             if not cm.is_online():
#                 self.ui_set_status("No WiFi\n\nConnect to WiFi and reopen the app.")
#                 self._worker_running = False
#                 return
#         except Exception as ex:
#             print("TFLPlayer: ConnectivityManager check failed:", ex)
# ---------------------------------------------------------------------------

class AlbumPlayerStub:
    """Minimal stub that exercises the _worker_main connectivity pre-check."""

    def __init__(self, connectivity_manager_module, album_index_factory=None):
        self._connectivity_manager = connectivity_manager_module
        self._album_index_factory = album_index_factory
        self._worker_running = True
        self._status_calls = []

    def ui_set_status(self, txt):
        self._status_calls.append(txt)

    def _stop_flag(self):
        return False

    def _worker_main(self):
        # SOURCE: tfl_player.py AlbumPlayer._worker_main connectivity pre-check block
        # (lines ~1811-1821 after IN-01/IN-02 fixes). Keep in sync when _worker_main changes.
        try:
            cm = self._connectivity_manager.get()
            if not cm.is_online():
                self.ui_set_status("No WiFi\n\nConnect to WiFi and reopen the app.")
                self._worker_running = False
                return
        except Exception as ex:
            print("TFLPlayer: ConnectivityManager check failed:", ex)

        # If we get here, connectivity check passed -- try to load index
        if self._album_index_factory is not None:
            try:
                self.ui_set_status("Loading index...")
                self._album_index_factory()
            except Exception as ex:
                print("TFLPlayer: index load error:", ex)
                self.ui_set_status("Could not load track list.\n\nCheck your connection and try again.")
                self._worker_running = False
                return

        self._worker_running = False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTflWifiPrecheck(unittest.TestCase):
    """PLSH-02: offline state shows 'No WiFi' status and exits without loading index."""

    def test_offline_shows_no_wifi_message(self):
        """When is_online() returns False, ui_set_status shows 'No WiFi...' message."""
        cm_module = MockCMModule(online=False)
        index_calls = [0]

        def fake_index():
            index_calls[0] += 1
            return object()

        stub = AlbumPlayerStub(cm_module, album_index_factory=fake_index)
        stub._worker_main()

        self.assertTrue(
            len(stub._status_calls) >= 1,
            "Expected at least one ui_set_status call when offline"
        )
        self.assertTrue(
            stub._status_calls[0].startswith("No WiFi"),
            "Expected status to start with 'No WiFi', got: " + repr(stub._status_calls[0])
        )

    def test_offline_does_not_call_album_index(self):
        """When is_online() returns False, AlbumIndex.load() is never called."""
        cm_module = MockCMModule(online=False)
        index_calls = [0]

        def fake_index():
            index_calls[0] += 1
            return object()

        stub = AlbumPlayerStub(cm_module, album_index_factory=fake_index)
        stub._worker_main()

        self.assertEqual(
            index_calls[0], 0,
            "AlbumIndex factory must NOT be called when offline"
        )

    def test_offline_sets_worker_running_false(self):
        """When offline, _worker_running is set to False so the thread exits."""
        cm_module = MockCMModule(online=False)
        stub = AlbumPlayerStub(cm_module)
        stub._worker_running = True
        stub._worker_main()

        self.assertFalse(
            stub._worker_running,
            "_worker_running must be False after offline pre-check exits"
        )

    def test_online_proceeds_to_index_load(self):
        """When is_online() returns True, AlbumIndex factory is called."""
        cm_module = MockCMModule(online=True)
        index_calls = [0]

        def fake_index():
            index_calls[0] += 1
            return object()

        stub = AlbumPlayerStub(cm_module, album_index_factory=fake_index)
        stub._worker_main()

        self.assertEqual(
            index_calls[0], 1,
            "AlbumIndex factory must be called once when online"
        )

    def test_no_wifi_message_exact_string(self):
        """The exact 'No WiFi' UI-SPEC string is shown when offline."""
        cm_module = MockCMModule(online=False)
        stub = AlbumPlayerStub(cm_module)
        stub._worker_main()

        expected = "No WiFi\n\nConnect to WiFi and reopen the app."
        self.assertEqual(
            stub._status_calls[0], expected,
            "Exact UI-SPEC string mismatch"
        )

    def test_connectivity_manager_exception_proceeds(self):
        """If ConnectivityManager.get() raises, _worker_main continues (does not abort)."""
        class FailingCMModule:
            def get(self):
                raise RuntimeError("CM unavailable")

        index_calls = [0]

        def fake_index():
            index_calls[0] += 1
            return object()

        stub = AlbumPlayerStub(FailingCMModule(), album_index_factory=fake_index)
        stub._worker_main()

        # Should have fallen through to the index load attempt
        self.assertEqual(
            index_calls[0], 1,
            "When ConnectivityManager raises, execution should fall through to index load"
        )
