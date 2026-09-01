import sys
import unittest
import time
sys.path.insert(0, ".")

import lvgl as lv
from mpos.ui.testing import GraphicalTestCase, wait_for_render, simulate_drag
from mpos.ui.infinite_list import InfiniteList

_ESP32 = sys.platform == "esp32"
TOTAL_ITEMS = 5000


class _Base:

    def _make_items(self, count=TOTAL_ITEMS):
        return [(f"rom_{i:04d}.wad", None, None, None) for i in range(count)]

    def _make_list(self, item_count=TOTAL_ITEMS):
        lst = InfiniteList(self.screen)
        lst.set_size(lv.pct(100), lv.pct(70))
        lst.center()

        focus_group = lv.group_get_default()
        if focus_group is None:
            focus_group = lv.group_create()
            lv.group_set_default(focus_group)

        def render(container, idx, item):
            row = lv.obj(container)
            row.set_flex_flow(lv.FLEX_FLOW.ROW)
            row.set_size(lv.pct(100), lv.SIZE_CONTENT)
            row.add_flag(lv.obj.FLAG.CLICKABLE)
            row.add_flag(lv.obj.FLAG.SCROLL_ON_FOCUS)
            focus_group.add_obj(row)
            row.add_event_cb(
                lambda e, l=lst, i=idx: l.ensure_loaded(i + 10),
                lv.EVENT.FOCUSED, None,
            )
            label = lv.label(row)
            label.set_text(item[0])
            label.center()
            return row

        items = self._make_items(item_count)
        lst.set_data(items, render)
        self.wait_for_render(10)
        return lst

    def _drag_scroll_down(self, lst, steps=None):
        if steps is None:
            steps = 15 if _ESP32 else 8
        start_x = 160
        lst_h = lst.obj.get_height()
        if lst_h <= 0:
            lst_h = 168
        start_y = lst_h - 20
        end_y = 40
        simulate_drag(start_x, start_y, start_x, end_y, steps=steps, step_delay_ms=30)
        self.wait_for_render(20 if _ESP32 else 10)

    def _drag_scroll_up(self, lst, steps=None):
        if steps is None:
            steps = 15 if _ESP32 else 8
        start_x = 160
        start_y = 40
        lst_h = lst.obj.get_height()
        if lst_h <= 0:
            lst_h = 168
        end_y = lst_h - 20
        simulate_drag(start_x, start_y, start_x, end_y, steps=steps, step_delay_ms=30)
        self.wait_for_render(20 if _ESP32 else 10)


class TestInfiniteListBoundedChildren(GraphicalTestCase, _Base):

    def test_item_count_matches_input(self):
        lst = self._make_list(5000)
        self.assertEqual(lst.item_count, 5000)

    def test_rendered_count_is_bounded(self):
        lst = self._make_list(5000)
        count = lst.rendered_count
        self.assertTrue(count < 30, f"Expected <30 rendered children, got {count}")
        self.assertTrue(count > 0, "Expected at least 1 rendered child")

    def test_first_items_visible_initially(self):
        lst = self._make_list(5000)
        self.assertTextPresent("rom_0000.wad")
        self.assertTextPresent("rom_0001.wad")

    def test_last_items_not_visible_initially(self):
        lst = self._make_list(5000)
        self.assertTextNotPresent("rom_4999.wad")
        self.assertTextNotPresent("rom_4998.wad")

    def test_few_items_all_rendered(self):
        lst = self._make_list(5)
        self.assertEqual(lst.rendered_count, 5)
        for i in range(5):
            self.assertTextPresent(f"rom_{i:04d}.wad")

    def test_empty_list(self):
        lst = InfiniteList(self.screen)
        lst.set_size(lv.pct(100), lv.pct(70))

        def render(container, idx, item):
            pass

        lst.set_data([], render)
        self.wait_for_render(10)
        self.assertEqual(lst.rendered_count, 0)
        self.assertEqual(lst.item_count, 0)


class TestInfiniteListScrolling(GraphicalTestCase, _Base):

    def test_rendered_count_stays_bounded_while_scrolling(self):
        lst = self._make_list(2000)
        for _ in range(15):
            self._drag_scroll_down(lst)
            count = lst.rendered_count
            self.assertTrue(count < 30, f"rendered count {count} exceeded bound 30")

    def test_scroll_down_hides_early_items(self):
        lst = self._make_list(1000)
        self.assertTextPresent("rom_0000.wad")

        drags = 25 if _ESP32 else 10
        for _ in range(drags):
            self._drag_scroll_down(lst)

        self.assertTextNotPresent("rom_0000.wad")

    def test_scroll_up_after_scroll_down_restores_items(self):
        lst = self._make_list(1000)
        self.assertTextPresent("rom_0000.wad")

        drags = 18 if _ESP32 else 8
        for _ in range(drags):
            self._drag_scroll_down(lst)
        self.assertTextNotPresent("rom_0000.wad")

        for _ in range(drags):
            self._drag_scroll_up(lst)
        self.assertTextPresent("rom_0000.wad")

    def test_rendered_range_starts_at_zero(self):
        lst = self._make_list(1000)
        first, last = lst.rendered_range
        self.assertEqual(first, 0)
        self.assertTrue(last - first < 30)
        self.assertTextPresent("rom_0000.wad")
        self.assertTextNotPresent("rom_0999.wad")

    def test_focusing_last_item_loads_more(self):
        lst = self._make_list(200)
        initial = lst.rendered_count
        initial_last = lst.rendered_range[1]

        focus_on = lst.obj.get_child(initial - 1)
        lv.group_focus_obj(focus_on)

        # The FOCUSED callback triggers ensure_loaded() which loads more
        # items.  LVGL may also scroll to the focused item and the InfiniteList
        # cleanup may recycle rows, so rendered_count can drop again.  Check the
        # rendered range (not the count) to prove more items were loaded.
        def _loaded_more():
            first, last = lst.rendered_range
            return last > initial_last

        max_iterations = 120 if _ESP32 else 40
        for _ in range(max_iterations):
            if _loaded_more():
                break
            self.wait_for_render()

        # Focus alone may not be enough — simulate a DOWN key to trigger
        # the ensure_loaded callback on ESP32 where LVGL event delivery
        # is more sensitive to task_handler scheduling.
        if _ESP32 and not _loaded_more():
            from mpos.ui.focus_direction import move_focus_direction, DOWN
            move_focus_direction(DOWN)
            for _ in range(60):
                if _loaded_more():
                    break
                self.wait_for_render()

        self.assertTrue(
            _loaded_more(),
            f"Expected rendered range to advance beyond {initial_last} after focusing last item, got {lst.rendered_range}"
        )


class TestInfiniteListPerformance(GraphicalTestCase, _Base):

    def _make_list_timed(self, count):
        items = self._make_items(count)
        lst = InfiniteList(self.screen)
        lst.set_size(lv.pct(100), lv.pct(70))
        lst.center()

        def render(container, idx, item):
            row = lv.obj(container)
            row.set_flex_flow(lv.FLEX_FLOW.ROW)
            row.set_size(lv.pct(100), lv.SIZE_CONTENT)
            row.add_flag(lv.obj.FLAG.CLICKABLE)
            row.add_flag(lv.obj.FLAG.SCROLL_ON_FOCUS)
            label = lv.label(row)
            label.set_text(item[0])
            label.center()
            return row

        t0 = time.ticks_ms()
        lst.set_data(items, render)
        self.wait_for_render(10)
        elapsed = time.ticks_diff(time.ticks_ms(), t0)
        return lst, elapsed

    def test_set_data_is_fast_and_virtualized(self):
        """set_data should be fast for large lists and not scale with item count.

        Self-calibrate against a small list on the same machine; absolute
        thresholds are too flaky on slow CI runners. The 5000/10000 item lists
        should not be dramatically slower than the 100-item baseline (all three
        render the same bounded window).
        """
        absolute_cap = 4000 if _ESP32 else 2000

        base_lst, base_elapsed = self._make_list_timed(100)
        self.assertTrue(base_lst.rendered_count < 30)

        lst_5k, elapsed_5k = self._make_list_timed(5000)
        self.assertTrue(lst_5k.rendered_count < 30)

        lst_10k, elapsed_10k = self._make_list_timed(10000)
        self.assertTrue(lst_10k.rendered_count < 30)

        ratio_5k = elapsed_5k / base_elapsed if base_elapsed > 0 else 0
        ratio_10k = elapsed_10k / base_elapsed if base_elapsed > 0 else 0

        self.assertTrue(
            ratio_5k < 10,
            f"set_data with 5000 items is {ratio_5k:.1f}x slower than 100 items; expected <10x"
        )
        self.assertTrue(
            ratio_10k < 10,
            f"set_data with 10000 items is {ratio_10k:.1f}x slower than 100 items; expected <10x"
        )

        self.assertTrue(
            elapsed_5k < absolute_cap,
            f"set_data with 5000 items took {elapsed_5k}ms, expected <{absolute_cap}ms"
        )
        self.assertTrue(
            elapsed_10k < absolute_cap,
            f"set_data with 10000 items took {elapsed_10k}ms, expected <{absolute_cap}ms"
        )

    def test_scroll_render_time_is_low(self):
        # Self-calibrate on a modest list on the same machine, then compare the
        # 5000-item list to that baseline.  Absolute thresholds are flaky on slow
        # CI runners; a ratio test proves the infinite list is virtualized and
        # does not scale with the number of items.
        cal_lst = self._make_list(100)
        cal_times = []
        for _ in range(3):
            t0 = time.ticks_ms()
            self._drag_scroll_down(cal_lst)
            cal_times.append(time.ticks_diff(time.ticks_ms(), t0))
        cal_avg = sum(cal_times) / len(cal_times)

        lst = self._make_list(5000)
        times = []
        for _ in range(5):
            t0 = time.ticks_ms()
            self._drag_scroll_down(lst)
            times.append(time.ticks_diff(time.ticks_ms(), t0))

        avg = sum(times) / len(times)
        ratio = avg / cal_avg if cal_avg > 0 else 0

        self.assertTrue(
            ratio < 5,
            f"Large-list scroll avg {avg:.0f}ms is {ratio:.1f}x the calibrated {cal_avg:.0f}ms; expected <5x"
        )

        # Absolute guard against catastrophic slowdowns on any machine.
        absolute_cap = 5000 if _ESP32 else 3000
        self.assertTrue(
            avg < absolute_cap,
            f"Average scroll drag+render took {avg:.0f}ms, expected <{absolute_cap}ms"
        )

    def test_initially_visible_range_rendered_properly(self):
        lst = self._make_list(10)
        rcount = lst.rendered_count
        self.assertTrue(rcount >= 5, f"Expected >=5 rendered, got {rcount}")
        self.assertTrue(rcount < 12)
        for i in range(rcount):
            self.assertTextPresent(f"rom_{i:04d}.wad")
