import sys
import unittest
import time
sys.path.insert(0, ".")

import lvgl as lv
from mpos.ui.testing import GraphicalTestCase, wait_for_render, simulate_drag
from mpos.ui.infinite_list import InfiniteList

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

    def _drag_scroll_down(self, lst, steps=8):
        start_x = 160
        lst_h = lst.obj.get_height()
        if lst_h <= 0:
            lst_h = 168
        start_y = lst_h - 20
        end_y = 40
        simulate_drag(start_x, start_y, start_x, end_y, steps=steps, step_delay_ms=30)
        self.wait_for_render(10)

    def _drag_scroll_up(self, lst, steps=8):
        start_x = 160
        start_y = 40
        lst_h = lst.obj.get_height()
        if lst_h <= 0:
            lst_h = 168
        end_y = lst_h - 20
        simulate_drag(start_x, start_y, start_x, end_y, steps=steps, step_delay_ms=30)
        self.wait_for_render(10)


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

        for _ in range(10):
            self._drag_scroll_down(lst)

        self.assertTextNotPresent("rom_0000.wad")

    def test_scroll_up_after_scroll_down_restores_items(self):
        lst = self._make_list(1000)
        self.assertTextPresent("rom_0000.wad")

        for _ in range(8):
            self._drag_scroll_down(lst)
        self.assertTextNotPresent("rom_0000.wad")

        for _ in range(8):
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
        g = lv.group_get_default()

        focus_on = lst.obj.get_child(initial - 1)
        lv.group_focus_obj(focus_on)

        for _ in range(30):
            self.wait_for_render()

        self.assertTrue(
            lst.rendered_count > initial,
            f"Expected >{initial} rendered after focusing last item, got {lst.rendered_count}"
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

    def test_set_data_fast_with_5000_items(self):
        lst, elapsed = self._make_list_timed(5000)
        self.assertTrue(
            elapsed < 500,
            f"set_data with 5000 items took {elapsed}ms, expected <500ms"
        )
        self.assertTrue(lst.rendered_count < 30)

    def test_set_data_fast_with_10000_items(self):
        lst, elapsed = self._make_list_timed(10000)
        self.assertTrue(
            elapsed < 1000,
            f"set_data with 10000 items took {elapsed}ms, expected <1000ms"
        )
        self.assertTrue(lst.rendered_count < 30)

    def test_scroll_render_time_is_low(self):
        lst = self._make_list(5000)

        times = []
        for _ in range(10):
            t0 = time.ticks_ms()
            self._drag_scroll_down(lst)
            elapsed = time.ticks_diff(time.ticks_ms(), t0)
            times.append(elapsed)

        avg = sum(times) / len(times)
        self.assertTrue(
            avg < 600,
            f"Average scroll drag+render took {avg:.0f}ms, expected <600ms"
        )
        for t in times:
            self.assertTrue(t < 800, f"Single scroll drag+render took {t}ms")

    def test_initially_visible_range_rendered_properly(self):
        lst = self._make_list(10)
        rcount = lst.rendered_count
        self.assertTrue(rcount >= 5, f"Expected >=5 rendered, got {rcount}")
        self.assertTrue(rcount < 12)
        for i in range(rcount):
            self.assertTextPresent(f"rom_{i:04d}.wad")
