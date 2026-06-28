import os
import unittest

from mpos.app.activities.view import ViewActivity


class TestViewActivityPreview(unittest.TestCase):
    """Tests for ViewActivity's generic file preview / binary fallback."""

    _TMP_DIR = "../tmp"

    def setUp(self):
        self.activity = ViewActivity()
        self._files = []
        try:
            os.stat(self._TMP_DIR)
        except OSError:
            os.mkdir(self._TMP_DIR)

    def tearDown(self):
        for path in self._files:
            try:
                os.unlink(path)
            except OSError:
                pass

    def _write(self, name, data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        path = self._TMP_DIR + "/" + name
        with open(path, "wb") as f:
            f.write(data)
        self._files.append(path)
        return path

    def test_text_file_preview(self):
        path = self._write("view_preview_text.txt", "hello world\ndummy")
        self.assertEqual(self.activity._read_preview(path), "hello world\ndummy")

    def test_text_with_non_ascii_preview(self):
        path = self._write("view_preview_unicode.txt", "café")
        self.assertEqual(self.activity._read_preview(path), "café")

    def test_image_extension_shows_image_hint(self):
        path = self._write("view_preview_image.png", b"not really an image")
        self.assertEqual(
            self.activity._read_preview(path),
            "This is an image file.\nInstall an image viewer to open it.",
        )

    def test_audio_extension_shows_audio_hint(self):
        path = self._write("view_preview_audio.wav", b"not really audio")
        self.assertEqual(
            self.activity._read_preview(path),
            "This is an audio file.\nInstall a music or audio player to open it.",
        )

    def test_rtttl_extension_shows_audio_hint(self):
        path = self._write("view_preview_audio.rtttl", b"not really audio")
        self.assertEqual(
            self.activity._read_preview(path),
            "This is an audio file.\nInstall a music or audio player to open it.",
        )

    def test_unknown_binary_data_shows_generic_binary_hint(self):
        path = self._write("view_preview_unknown.bin", bytes(range(256)))
        self.assertEqual(
            self.activity._read_preview(path),
            "This is a binary file.\nIt cannot be previewed.",
        )

    def test_missing_file_error_is_not_empty(self):
        path = self._TMP_DIR + "/view_preview_missing_file_xyz.txt"
        result = self.activity._read_preview(path)
        self.assertTrue(result.startswith("(could not read file:"))
        # Ensure the exception detail was included, not just an empty placeholder.
        self.assertTrue(len(result) > len("(could not read file: "))


if __name__ == "__main__":
    unittest.main()
