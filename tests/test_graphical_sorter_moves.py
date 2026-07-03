"""
Test that Sorter moves the top run of a tube, not the bottom run.

The user-reported scenario:
- Source tube (visually): A on top, two identical emojis B below it.
- Click the source, then an empty target.
- Expected: source now has B,B and target has A.
- Buggy behavior: source kept A and target received B,B.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_sorter_moves.py
    Device:  ./tests/unittest.sh tests/test_graphical_sorter_moves.py --ondevice
"""

import time
import unittest

from mpos import AppManager, SharedPreferences, wait_for_render
from mpos.ui import screen_stack


APP_NAME = "com.micropythonos.sorter"


def _clear_sorter_prefs():
    prefs = SharedPreferences(APP_NAME)
    editor = prefs.edit()
    editor.remove_all()
    editor.commit()


class TestSorterMoves(unittest.TestCase):
    """Verify moves use the top run of a tube."""

    def setUp(self):
        """Return to launcher and clear sorter prefs before each test."""
        AppManager.restart_launcher()
        wait_for_render(10)
        _clear_sorter_prefs()

    def tearDown(self):
        """Navigate back to launcher after each test."""
        try:
            from mpos import ui

            ui.back_screen()
            wait_for_render(5)
        except Exception:
            pass

    def test_top_emoji_moves_to_empty_tube(self):
        """Clicking a tube then an empty target moves only the top emoji."""
        result = AppManager.start_app(APP_NAME)
        self.assertTrue(result, "Sorter should start")
        wait_for_render(10)

        act = screen_stack[-1][0]
        act.capacity = 4
        # Internal list is bottom..top: B,B,A produces A visually on top.
        act.tubes = [[1, 1, 0], [], [], [], []]
        act.emoji_order = list(range(20))
        act.selected = -1
        act._last_ts = 0
        act.build_board()
        wait_for_render(5)

        act.on_tube(None, 0)
        time.sleep_ms(100)
        act.on_tube(None, 1)
        wait_for_render(5)

        self.assertEqual(
            [list(t) for t in act.tubes],
            [[1, 1], [0], [], [], []],
            "Top emoji (A) should move to the empty target, leaving B,B behind",
        )


if __name__ == "__main__":
    unittest.main()
