"""
test_graphical_infinite_list_dynamic.py - Verify InfiniteList sizes its
initial render window dynamically from the container height.

- A taller container renders more rows than a shorter one (same items).
- The rendered window always covers the viewport (content overflows it).
- Few items still render fully; empty still renders nothing.

Usage:
    python3 scripts/test_runner.py tests/test_graphical_infinite_list_dynamic.py
"""

import sys
import unittest

sys.path.insert(0, ".")

import lvgl as lv
from mpos.ui.testing import GraphicalTestCase
from mpos.ui.infinite_list import InfiniteList


def _make_items(count):
    return [("rom_%04d.wad" % i,) for i in range(count)]


def _render_row(container, idx, item):
    row = lv.obj(container)
    row.set_flex_flow(lv.FLEX_FLOW.ROW)
    row.set_size(lv.pct(100), lv.SIZE_CONTENT)
    label = lv.label(row)
    label.set_text(item[0])
    return row


class TestInfiniteListDynamicWindow(GraphicalTestCase):

    def _make_list(self, height_pct, item_count=5000):
        lst = InfiniteList(self.screen)
        lst.set_size(lv.pct(100), lv.pct(height_pct))
        lst.center()
        lst.set_data(_make_items(item_count), _render_row)
        self.wait_for_render(10)
        return lst

    def test_taller_container_renders_more_rows(self):
        short = self._make_list(30)
        tall = self._make_list(90)
        self.assertTrue(
            tall.rendered_count > short.rendered_count,
            "tall=%d should render more than short=%d"
            % (tall.rendered_count, short.rendered_count),
        )
        for lst in (short, tall):
            self.assertTrue(lst.rendered_count < 60)
            first, _ = lst.rendered_range
            self.assertEqual(first, 0)

    def test_initial_window_covers_viewport(self):
        lst = self._make_list(70)
        self.assertTrue(
            lst.obj.get_scroll_bottom() > 0,
            "rendered content should overflow the viewport",
        )
        self.assertTextPresent("rom_0000.wad")

    def test_few_items_still_all_rendered(self):
        lst = self._make_list(70, item_count=4)
        self.assertEqual(lst.rendered_count, 4)

    def test_empty_still_renders_nothing(self):
        lst = InfiniteList(self.screen)
        lst.set_size(lv.pct(100), lv.pct(70))
        lst.set_data([], lambda c, i, item: None)
        self.wait_for_render(10)
        self.assertEqual(lst.rendered_count, 0)


if __name__ == "__main__":
    unittest.main()
