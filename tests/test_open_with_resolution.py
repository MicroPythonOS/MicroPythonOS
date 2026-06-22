import unittest

from mpos import Intent
from mpos.content.app_manager import AppManager
from mpos.app.activity import Activity
from mpos.ui.file_explorer_activity import FileExplorerActivity


class _FakeMusicPlayer(Activity):
    pass


class _FakeImageView(Activity):
    pass


class _FakeViewActivity(Activity):
    pass


class _FakeFallback(Activity):
    pass


class TestFileTypeResolution(unittest.TestCase):
    """Non-graphical tests for the "Open With" file-type intent resolver."""

    def setUp(self):
        """Clear resolver state before each test."""
        AppManager._registry = {}
        AppManager._file_handler_specs = {}
        AppManager._handler_class_cache = {}
        AppManager._handler_app_fullname = {}

    def tearDown(self):
        """Leave resolver state clean after each test."""
        AppManager._registry = {}
        AppManager._file_handler_specs = {}
        AppManager._handler_class_cache = {}
        AppManager._handler_app_fullname = {}

    def _add_fake_app(self, fullname, name):
        app = type("App", (), {"fullname": fullname, "name": name, "activities": []})()
        AppManager._by_fullname[fullname] = app

    def _register_file_handler(self, action, fullname, entrypoint, classname,
                               activity_class, path_pattern=None, mime_type=None):
        AppManager._file_handler_specs.setdefault(action, []).append({
            "app_fullname": fullname,
            "entrypoint": entrypoint,
            "classname": classname,
            "mime_type": mime_type,
            "path_pattern": path_pattern,
        })
        AppManager._handler_class_cache[(fullname, entrypoint, classname)] = activity_class

    def test_wav_resolves_to_music_player(self):
        """A .wav file should resolve to the registered audio handler."""
        self._register_file_handler(
            "view", "com.micropythonos.musicplayer", "music_player.py", "MusicPlayer",
            _FakeMusicPlayer, path_pattern=[".wav"], mime_type="audio/wav",
        )

        handlers = AppManager.resolve_activity(Intent(action="view", data="/sdcard/music/song.wav"))

        self.assertEqual(len(handlers), 1)
        self.assertEqual(handlers[0].activity_class, _FakeMusicPlayer)
        self.assertEqual(handlers[0].app_fullname, "com.micropythonos.musicplayer")

    def test_png_jpg_raw_resolve_to_image_view(self):
        """Image files should resolve to the registered image handler."""
        self._register_file_handler(
            "view", "com.micropythonos.imageview", "imageview.py", "ImageView",
            _FakeImageView, path_pattern=[".png", ".jpg", ".jpeg", ".raw"], mime_type="image/*",
        )

        for ext in (".png", ".jpg", ".jpeg", ".raw"):
            with self.subTest(ext=ext):
                handlers = AppManager.resolve_activity(
                    Intent(action="view", data="/sdcard/pics/photo" + ext)
                )
                self.assertEqual(len(handlers), 1)
                self.assertEqual(handlers[0].activity_class, _FakeImageView)

    def test_multiple_handlers_for_same_file(self):
        """If several apps declare support for the same extension, all are returned."""
        self._register_file_handler(
            "view", "com.micropythonos.musicplayer", "music_player.py", "MusicPlayer",
            _FakeMusicPlayer, path_pattern=[".wav"], mime_type="audio/wav",
        )
        self._register_file_handler(
            "view", "com.micropythonos.soundrecorder", "sound_recorder.py", "SoundRecorder",
            _FakeFallback, path_pattern=[".wav"],
        )

        handlers = AppManager.resolve_activity(Intent(action="view", data="/sdcard/recording.wav"))
        classes = [h.activity_class for h in handlers]

        self.assertEqual(len(handlers), 2)
        self.assertTrue(_FakeMusicPlayer in classes)
        self.assertTrue(_FakeFallback in classes)

    def test_unknown_extension_falls_back_to_generic_view(self):
        """Files with no specific handler fall back to the generic view handler."""
        AppManager.register_activity("view", _FakeViewActivity)
        self._register_file_handler(
            "view", "com.micropythonos.imageview", "imageview.py", "ImageView",
            _FakeImageView, path_pattern=[".png"],
        )

        handlers = AppManager.resolve_activity(Intent(action="view", data="/sdcard/document.txt"))

        self.assertEqual(len(handlers), 1)
        self.assertEqual(handlers[0].activity_class, _FakeViewActivity)
        self.assertIsNone(handlers[0].app_fullname)

    def test_no_data_uses_action_only_registry(self):
        """An implicit view intent without data should use the generic action registry."""
        AppManager.register_activity("view", _FakeViewActivity)

        handlers = AppManager.resolve_activity(Intent(action="view"))

        self.assertEqual(len(handlers), 1)
        self.assertEqual(handlers[0].activity_class, _FakeViewActivity)

    def test_display_name_prefers_app_name(self):
        """Handler display names should come from the parent app name."""
        self._add_fake_app("com.micropythonos.musicplayer", "Music Player")
        AppManager._handler_app_fullname[_FakeMusicPlayer] = "com.micropythonos.musicplayer"

        name = AppManager.get_handler_display_name(_FakeMusicPlayer)

        self.assertEqual(name, "Music Player")

    def test_display_name_falls_back_to_class_name(self):
        """Handlers with no known parent app fall back to the class name."""
        name = AppManager.get_handler_display_name(_FakeViewActivity)

        self.assertEqual(name, "_FakeViewActivity")

    def test_resolve_populates_app_fullname_mapping(self):
        """Resolving a handler class should record its parent app for name lookup."""
        self._add_fake_app("com.micropythonos.imageview", "Image View")
        self._register_file_handler(
            "view", "com.micropythonos.imageview", "imageview.py", "ImageView",
            _FakeImageView, path_pattern=[".png"],
        )

        AppManager.resolve_activity(Intent(action="view", data="pic.png"))

        self.assertEqual(
            AppManager._handler_app_fullname.get(_FakeImageView),
            "com.micropythonos.imageview",
        )
        self.assertEqual(AppManager.get_handler_display_name(_FakeImageView), "Image View")

    def test_pick_file_resolves_to_file_explorer_activity(self):
        """A pick_file intent should resolve to the framework FileExplorerActivity."""
        AppManager.register_activity("pick_file", FileExplorerActivity)

        handlers = AppManager.resolve_activity(Intent(action="pick_file"))

        self.assertEqual(len(handlers), 1)
        self.assertEqual(handlers[0].activity_class, FileExplorerActivity)
        self.assertIsNone(handlers[0].app_fullname)

    def test_file_type_resolution_is_case_insensitive(self):
        """Uppercase extensions should resolve the same handler as lowercase ones."""
        self._register_file_handler(
            "view", "com.micropythonos.texteditor", "text_editor.py", "TextEditor",
            _FakeFallback, path_pattern=[".txt", ".json", ".md"],
        )

        for ext in (".json", ".JSON", ".Json", ".txt", ".TXT"):
            with self.subTest(ext=ext):
                handlers = AppManager.resolve_activity(
                    Intent(action="view", data="/sdcard/document" + ext)
                )
                self.assertEqual(len(handlers), 1)
                self.assertEqual(handlers[0].activity_class, _FakeFallback)
                self.assertEqual(handlers[0].app_fullname, "com.micropythonos.texteditor")


if __name__ == "__main__":
    unittest.main()
