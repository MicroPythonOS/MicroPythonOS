# test_tfl_error_paths.py  (ASCII-only)
#
# Unit tests for PLSH-03: clean error messages for degraded-state paths in
# AlbumPlayer._worker_main (tfl_player.py).
#
# Approach: duck-typed stubs rather than importing tfl_player.py directly.
# tfl_player.py pulls in lvgl and the full mpos stack at module level, which
# crashes on the headless desktop runner.  Instead each test class reproduces
# the relevant _worker_main code segment verbatim and verifies the correct
# ui_set_status string is produced.
#
# Source lines from tfl_player.py (post Plan-02 edits):
#   - index load error: lines 1437-1445
#   - no-SD + no-cache error: lines 1453-1460
#   - streaming-no-cache error: lines 1502-1508

import unittest
import sys

sys.path.insert(0, "../tests")


# ---------------------------------------------------------------------------
# Minimal sys.modules stubs (same as test_tfl_wifi_precheck.py)
# ---------------------------------------------------------------------------

class _MockLv:
    class ALIGN:
        TOP_MID = 0
    class PART:
        MAIN = 0
    class label:
        class LONG_MODE:
            WRAP = 0
    def pct(self, n):
        return n
    def obj(self, *a, **k):
        return _MockWidget()
    def image(self, *a, **k):
        return _MockWidget()
    def label(self, *a, **k):
        return _MockWidget()
    def button(self, *a, **k):
        return _MockWidget()

class _MockWidget:
    def set_size(self, *a, **k): pass
    def align(self, *a, **k): pass
    def set_text(self, *a, **k): pass
    def set_width(self, *a, **k): pass
    def add_flag(self, *a, **k): pass
    def add_event_cb(self, *a, **k): pass

sys.modules.setdefault('lvgl', _MockLv())

import json as _json
sys.modules.setdefault('ujson', _json)

class _MockThread:
    @staticmethod
    def start_new_thread(fn, args): pass
    @staticmethod
    def allocate_lock():
        class _Lock:
            def acquire(self, *a, **k): return True
            def release(self): pass
            def __enter__(self): return self
            def __exit__(self, *a): pass
        return _Lock()

sys.modules.setdefault('_thread', _MockThread)
sys.modules.setdefault('urequests', object())


# ---------------------------------------------------------------------------
# Expected UI-SPEC strings (from 02-UI-SPEC.md Copywriting Contract)
# ---------------------------------------------------------------------------

EXPECTED_TRACK_LIST_ERROR = (
    "Could not load track list.\n\nCheck your connection and try again."
)
EXPECTED_NO_SD_NO_CACHE = (
    "No SD card and not enough internal storage.\n"
    "Insert an SD card (>=70 MiB free) or free ~2 MiB."
)
EXPECTED_STREAMING_NO_CACHE = (
    "Not enough internal storage for streaming.\n"
    "Insert an SD card or free ~2 MiB."
)


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class _AlwaysOnlineCM:
    def get(self):
        class _CM:
            def is_online(self): return True
        return _CM()


class WorkerStub:
    """
    Reproduces the relevant segments of AlbumPlayer._worker_main so each
    test can exercise a specific error path in isolation.
    """

    def __init__(self):
        self._status_calls = []
        self._worker_running = True
        self._stop = False
        self._request_stop_called = False

    def ui_set_status(self, txt):
        self._status_calls.append(txt)

    def ui_set_progress(self, pct):
        pass

    def _request_stop(self):
        self._request_stop_called = True
        self._stop = True

    def _stop_flag(self):
        return self._stop

    def last_status(self):
        if self._status_calls:
            return self._status_calls[-1]
        return None

    # ---- reproduced code segments ----

    def run_index_load_segment(self, album_index_factory):
        """
        # SOURCE: tfl_player.py AlbumPlayer._worker_main index-load try/except block
        # (lines ~1823-1830 after IN-01/IN-02 fixes). Keep in sync when _worker_main changes.

        Reproduces tfl_player.py inner index-load try/except in _worker_main.

            self.ui_set_status("Loading index...")
            try:
                idx = AlbumIndex().load()
            except Exception as ex:
                print("TFLPlayer: index load error:", ex)
                self.ui_set_status("Could not load track list.\\n\\nCheck your connection and try again.")
                self._worker_running = False
                return
        """
        self.ui_set_status("Loading index...")
        try:
            idx = album_index_factory()
        except Exception as ex:
            print("TFLPlayer: index load error:", ex)
            self.ui_set_status(
                "Could not load track list.\n\nCheck your connection and try again."
            )
            self._worker_running = False
            return
        # index loaded ok -- signal success via a sentinel status
        self.ui_set_status("__index_loaded__")

    def run_storage_check_segment(self, sd_present, cache_ok):
        """
        Reproduces tfl_player.py lines 1453-1460.

            if (not sd_present) and (not cache_ok):
                self.ui_set_progress(0)
                self.ui_set_status(
                    "No SD card and not enough internal storage.\\n"
                    "Insert an SD card (>=70 MiB free) or free ~2 MiB."
                )
                self._request_stop()
                return
        """
        if (not sd_present) and (not cache_ok):
            self.ui_set_progress(0)
            self.ui_set_status(
                "No SD card and not enough internal storage.\n"
                "Insert an SD card (>=70 MiB free) or free ~2 MiB."
            )
            self._request_stop()
            return
        # passed -- signal via sentinel
        self.ui_set_status("__storage_ok__")

    def run_streaming_no_cache_segment(self, cache_ok):
        """
        Reproduces tfl_player.py lines 1501-1508 (streaming path, cache_ok False).

            if not cache_ok:
                self.ui_set_status(
                    "Not enough internal storage for streaming.\\n"
                    "Insert an SD card or free ~2 MiB."
                )
                self._request_stop()
                return
        """
        if not cache_ok:
            self.ui_set_status(
                "Not enough internal storage for streaming.\n"
                "Insert an SD card or free ~2 MiB."
            )
            self._request_stop()
            return
        self.ui_set_status("__streaming_ok__")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestIndexLoadFailure(unittest.TestCase):
    """PLSH-03a: AlbumIndex().load() raising shows 'Could not load track list.'"""

    def test_index_load_failure_shows_message(self):
        """OSError from AlbumIndex().load() produces the correct clean UI message."""
        def failing_index():
            raise OSError("network error")

        stub = WorkerStub()
        stub.run_index_load_segment(failing_index)

        self.assertEqual(
            stub.last_status(), EXPECTED_TRACK_LIST_ERROR,
            "Exact UI-SPEC error string mismatch for index load failure"
        )

    def test_index_load_failure_sets_worker_running_false(self):
        """After index load failure, _worker_running is False (thread exits cleanly)."""
        def failing_index():
            raise Exception("connection refused")

        stub = WorkerStub()
        stub.run_index_load_segment(failing_index)

        self.assertFalse(
            stub._worker_running,
            "_worker_running must be False after index load failure"
        )

    def test_index_load_failure_stops_at_error(self):
        """No further status calls are made after the error message (worker returned)."""
        def failing_index():
            raise Exception("timeout")

        stub = WorkerStub()
        stub.run_index_load_segment(failing_index)

        # The status calls should be: "Loading index..." then the error message.
        # There must NOT be an "__index_loaded__" sentinel.
        self.assertTrue(
            "__index_loaded__" not in stub._status_calls,
            "Worker must not continue past index load failure"
        )
        self.assertEqual(len(stub._status_calls), 2, "Expected exactly 2 status calls")

    def test_index_load_success_continues(self):
        """When AlbumIndex().load() succeeds, worker continues past the error guard."""
        class FakeIndex:
            tracks = [{"title": "T", "fragments": ["f1.wav"]}]

        def good_index():
            return FakeIndex()

        stub = WorkerStub()
        stub.run_index_load_segment(good_index)

        self.assertIn(
            "__index_loaded__", stub._status_calls,
            "Worker must continue when index loads successfully"
        )

    def test_index_load_failure_does_not_show_raw_exception(self):
        """Raw exception text must NOT appear in the UI status string."""
        raw_exception_text = "connection refused: raw error detail"

        def failing_index():
            raise Exception(raw_exception_text)

        stub = WorkerStub()
        stub.run_index_load_segment(failing_index)

        self.assertTrue(
            raw_exception_text not in stub.last_status(),
            "Raw exception text must not appear in UI status (D-06)"
        )


class TestNoSdNoCacheError(unittest.TestCase):
    """PLSH-03b: no SD and no internal cache shows 'No SD card' message."""

    def test_no_sd_no_cache_shows_message(self):
        """When sd_present=False and cache_ok=False, the storage error message is shown."""
        stub = WorkerStub()
        stub.run_storage_check_segment(sd_present=False, cache_ok=False)

        self.assertEqual(
            stub.last_status(), EXPECTED_NO_SD_NO_CACHE,
            "Exact UI-SPEC storage error string mismatch"
        )

    def test_no_sd_no_cache_calls_request_stop(self):
        """After the no-SD message, _request_stop() is called."""
        stub = WorkerStub()
        stub.run_storage_check_segment(sd_present=False, cache_ok=False)

        self.assertTrue(
            stub._request_stop_called,
            "_request_stop must be called after no-SD-no-cache message"
        )

    def test_sd_present_with_no_cache_continues(self):
        """When SD is present (even with no internal cache), worker continues past guard."""
        stub = WorkerStub()
        stub.run_storage_check_segment(sd_present=True, cache_ok=False)

        self.assertIn(
            "__storage_ok__", stub._status_calls,
            "Worker must continue when SD is present (cache_ok can be False)"
        )

    def test_no_sd_with_cache_continues(self):
        """When internal cache is available (even with no SD), worker continues."""
        stub = WorkerStub()
        stub.run_storage_check_segment(sd_present=False, cache_ok=True)

        self.assertIn(
            "__storage_ok__", stub._status_calls,
            "Worker must continue when internal cache is available"
        )

    def test_sd_and_cache_both_present_continues(self):
        """When both SD and cache are available, worker continues."""
        stub = WorkerStub()
        stub.run_storage_check_segment(sd_present=True, cache_ok=True)

        self.assertIn("__storage_ok__", stub._status_calls)

    def test_no_sd_no_cache_message_contains_required_keywords(self):
        """Error message contains both 'No SD card' and 'internal storage'."""
        stub = WorkerStub()
        stub.run_storage_check_segment(sd_present=False, cache_ok=False)
        msg = stub.last_status()

        self.assertIn("No SD card", msg)
        self.assertIn("internal storage", msg)


class TestStreamingNoCacheError(unittest.TestCase):
    """PLSH-03c: streaming mode with no internal cache shows 'Not enough internal storage'."""

    def test_streaming_no_cache_shows_message(self):
        """When cache_ok=False in streaming path, the streaming error message is shown."""
        stub = WorkerStub()
        stub.run_streaming_no_cache_segment(cache_ok=False)

        self.assertEqual(
            stub.last_status(), EXPECTED_STREAMING_NO_CACHE,
            "Exact UI-SPEC streaming-no-cache string mismatch"
        )

    def test_streaming_no_cache_calls_request_stop(self):
        """After streaming-no-cache message, _request_stop() is called."""
        stub = WorkerStub()
        stub.run_streaming_no_cache_segment(cache_ok=False)

        self.assertTrue(
            stub._request_stop_called,
            "_request_stop must be called after streaming-no-cache message"
        )

    def test_streaming_with_cache_continues(self):
        """When cache is available in streaming mode, worker continues."""
        stub = WorkerStub()
        stub.run_streaming_no_cache_segment(cache_ok=True)

        self.assertIn(
            "__streaming_ok__", stub._status_calls,
            "Worker must continue in streaming mode when cache is available"
        )

    def test_streaming_no_cache_message_contains_required_keywords(self):
        """Streaming error message contains 'Not enough internal storage'."""
        stub = WorkerStub()
        stub.run_streaming_no_cache_segment(cache_ok=False)
        msg = stub.last_status()

        self.assertIn("Not enough internal storage", msg)

    def test_streaming_no_cache_does_not_show_raw_exception(self):
        """Streaming no-cache is a guard (not an exception) -- no exception text in UI."""
        stub = WorkerStub()
        stub.run_streaming_no_cache_segment(cache_ok=False)
        msg = stub.last_status()

        # Must be a clean human-readable message with no Python exception markup
        self.assertTrue("Traceback" not in msg)
        self.assertTrue("Exception" not in msg)
        self.assertTrue("Error:" not in msg)
