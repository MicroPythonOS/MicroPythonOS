"""
Graphical stress test for the AppStore app list.
Measures memory usage, icon render time, and scroll latency at increasing
app counts to find the practical limit.

Each app gets a unique blurhash (last 2 chars varied) and unique fullname,
so raw icons and blurhash decodes are all distinct — no caching.

Usage:
  python3 scripts/test_runner.py tests/test_graphical_appstore_stress.py
  python3 scripts/test_runner.py tests/test_graphical_appstore_stress.py --ondevice --port /dev/ttyACM0 --timeout 1800
"""

import gc
import time
import unittest

import lvgl as lv
import mpos
import mpos.ui

from mpos import App, AppManager
from mpos.ui.testing import wait_for_render


_BASE_BLURHASH = "L6PZfSi_.AyE_3t7t7R**0o#DgR4"
_B83 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz#$%*+,-.:;=?@[]^_{|}~"
#_SIZES = [50, 100, 200, 400, 800, 1600]
#_SIZES = [50, 100, 200]
_SIZES = [50, 100, 200, 400]


def _wait_ms(ms):
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < ms:
        lv.task_handler()
        time.sleep(0.01)


def _get_appstore_activity():
    if not mpos.ui.screen_stack:
        return None
    activity, _, _, _ = mpos.ui.screen_stack[-1]
    return activity


def _make_fake_app(i):
    a = _B83[i % 83]
    b = _B83[(i // 83) % 83]
    bh = _BASE_BLURHASH[:-2] + a + b
    return App(
        f"App {i}",
        "StressTest",
        f"Description for app {i}",
        f"A much longer long description for stress test app number {i}.",
        None,
        f"https://example.com/app{i}.mpk",
        f"com.stresstest.app{i}",
        "1.0.0",
        "tools",
        [{"entrypoint": "main", "classname": "FakeActivity"}],
        blur_hash=bh,
    )


def _mem_report():
    gc.collect()
    return gc.mem_free(), gc.mem_alloc()


def _scroll_test():
    apps_list = _get_appstore_activity().apps_list
    start = time.ticks_ms()
    apps_list.scroll_to_y(400, True)
    _wait_ms(100)
    el = time.ticks_diff(time.ticks_ms(), start)
    apps_list.scroll_to_y(0, True)
    _wait_ms(100)
    return el


def _wait_pipeline_done(timeout_ms):
    deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
    activity = _get_appstore_activity()
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        if not activity._icon_queue and not activity._raw_timer:
            return True
        lv.task_handler()
        time.sleep(0.02)
    return False


def _cleanup_apps_list(activity):
    activity._stop_all_timers()
    activity._icon_queue.clear()
    for app in activity.apps:
        app.image_icon_widget = None
        app._icon_dsc = None
        app._icon_buf = None
    if hasattr(activity, "apps_list") and activity.apps_list:
        activity.apps_list.delete()
        activity.apps_list = None
    activity.apps = []


# ---------------------------------------------------------------------------


class TestAppStoreStress(unittest.TestCase):

    def setUp(self):
        result = AppManager.start_app("com.micropythonos.appstore")
        self.assertTrue(result, "AppStore failed to launch")
        wait_for_render(40)
        activity = _get_appstore_activity()
        self.assertIsNotNone(activity, "Could not get AppStore activity instance")
        if not hasattr(mpos, "TESTING") or not mpos.TESTING:
            activity._icon_pipeline = "blurhash"
        self.activity = activity

    def tearDown(self):
        mpos.ui.back_screen()
        _wait_ms(200)

    def _run_one_batch(self, n):
        activity = self.activity
        activity._stop_all_timers()
        print("  generating %d apps..." % n)

        activity.apps = [_make_fake_app(i) for i in range(n)]

        free_before, alloc_before = _mem_report()

        t0 = time.ticks_ms()
        activity.create_apps_list()
        t_list = time.ticks_diff(time.ticks_ms(), t0)

        _wait_ms(100)
        free_after_list, alloc_after_list = _mem_report()

        icon_done = _wait_pipeline_done(300000)
        t_icons = time.ticks_diff(time.ticks_ms(), t0)

        _wait_ms(100)
        free_after_icons, alloc_after_icons = _mem_report()

        try:
            t_scroll = _scroll_test() if icon_done else -1
        except Exception:
            t_scroll = -2

        _cleanup_apps_list(activity)
        _wait_ms(200)

        return {
            "n": n,
            "free_before": free_before,
            "alloc_before": alloc_before,
            "free_after_list": free_after_list,
            "alloc_after_list": alloc_after_list,
            "free_after_icons": free_after_icons,
            "alloc_after_icons": alloc_after_icons,
            "t_list_ms": t_list,
            "t_icons_ms": t_icons,
            "icon_done": icon_done,
            "t_scroll_ms": t_scroll,
        }

    def _print_header(self):
        print()
        print(" n    | free_start | alloc_start | free_list  | alloc_list | free_icons | alloc_icons | t_list_ms | t_icons_ms | icons? | scroll_ms")
        print("------+------------+-------------+------------+------------+------------+-------------+-----------+------------+--------+-----------")

    def _print_row(self, r):
        if r["icon_done"]:
            icons = "yes"
        elif r["t_icons_ms"] >= 300000:
            icons = "TIMEOUT"
        else:
            icons = "no"
        if r["t_scroll_ms"] >= 0:
            scroll = str(r["t_scroll_ms"])
        elif r["t_scroll_ms"] == -2:
            scroll = "err"
        else:
            scroll = "n/a"
        print(" %-4d | %-10d | %-11d | %-10d | %-10d | %-10d | %-11d | %-9d | %-10d | %-6s | %-7s" % (
            r["n"],
            r["free_before"], r["alloc_before"],
            r["free_after_list"], r["alloc_after_list"],
            r["free_after_icons"], r["alloc_after_icons"],
            r["t_list_ms"], r["t_icons_ms"],
            icons, scroll,
        ))

    def test_stress(self):
        self._print_header()
        for n in _SIZES:
            print("\nBatch n=%d:" % n)
            try:
                r = self._run_one_batch(n)
                self._print_row(r)
            except MemoryError:
                print("  MemoryError at n=%d — can't go higher." % n)
                return
            except Exception as e:
                print("  Exception at n=%d: %s" % (n, e))
                return
        print()
        print("All sizes completed. Try larger n if memory permits.")
