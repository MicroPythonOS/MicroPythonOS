"""
Graphical test for FileExplorerActivity listing in pick mode.

With a path_pattern, pick mode must list only matching files (non-matching
files could never be selected — taps on them were silently ignored, so
listing them was pure clutter). Directories are always listed: they stay
navigable in browse mode and selectable as a whole in pick mode. Browse
mode must keep listing everything.
"""

import os
import unittest

import mpos.ui
from mpos import FileExplorerActivity, Intent, wait_for_render
from mpos.activity_navigator import ActivityNavigator

FIXTURE_DIR = "tmp_picker_filter_test"


class TestGraphicalFileExplorerPickFilter(unittest.TestCase):

    def setUp(self):
        os.mkdir(FIXTURE_DIR)
        os.mkdir(FIXTURE_DIR + "/sub")
        for name in ("song.wav", "notes.md", "video.rgb565"):
            with open(FIXTURE_DIR + "/" + name, "w") as f:
                f.write("x")
        self._to_launcher()

    def tearDown(self):
        self._to_launcher()
        for name in ("song.wav", "notes.md", "video.rgb565"):
            try:
                os.remove(FIXTURE_DIR + "/" + name)
            except OSError:
                pass
        for path in (FIXTURE_DIR + "/sub", FIXTURE_DIR):
            try:
                os.rmdir(path)
            except OSError:
                pass

    def _to_launcher(self):
        for _ in range(10):
            if len(mpos.ui.screen_stack) <= 1:
                break
            mpos.ui.back_screen()
            wait_for_render(5)

    def _open_explorer(self, action=None, extras=None):
        intent = Intent(
            action=action,
            activity_class=FileExplorerActivity,
            extras=extras or {},
        )
        ActivityNavigator.startActivity(intent)
        wait_for_render(10)
        explorer = mpos.ui.screen_stack[-1][0]
        self.assertEqual(type(explorer).__name__, "FileExplorerActivity")
        return explorer

    @staticmethod
    def _listed_names(explorer):
        return set(
            path.rstrip("/").rsplit("/", 1)[-1]
            for path in explorer._path_to_btn.keys()
        )

    def test_pick_mode_lists_only_matching_files_and_dirs(self):
        explorer = self._open_explorer(
            action="pick_file",
            extras={
                "start_dir": FIXTURE_DIR + "/",
                "path_pattern": [".wav", ".rgb565"],
            },
        )
        names = self._listed_names(explorer)
        self.assertIn("song.wav", names)
        self.assertIn("video.rgb565", names)
        self.assertIn("sub", names)
        self.assertFalse(
            "notes.md" in names,
            "non-matching file should not be listed in pick mode",
        )

    def test_pick_mode_without_pattern_lists_everything(self):
        explorer = self._open_explorer(
            action="pick_file",
            extras={"start_dir": FIXTURE_DIR + "/"},
        )
        names = self._listed_names(explorer)
        for expected in ("song.wav", "notes.md", "video.rgb565", "sub"):
            self.assertIn(expected, names)

    def test_browse_mode_lists_everything(self):
        explorer = self._open_explorer(
            extras={
                "start_dir": FIXTURE_DIR + "/",
                "mode": FileExplorerActivity.MODE_BROWSE,
                "path_pattern": [".wav"],
            },
        )
        names = self._listed_names(explorer)
        for expected in ("song.wav", "notes.md", "video.rgb565", "sub"):
            self.assertIn(expected, names)


if __name__ == "__main__":
    unittest.main()
