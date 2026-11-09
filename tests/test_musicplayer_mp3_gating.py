"""Regression tests for the MP3 gating in the Music Player app."""

import sys
import unittest

sys.path.insert(0, "lib")
sys.path.insert(0, "apps/com.micropythonos.musicplayer")

import music_player as music_player_module  # noqa: E402


class _FakeIntent:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        _FakeIntent.instances.append(self)


class _FakePlayer:
    started = False

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def set_repeat(self, repeat_count):
        pass

    def start(self):
        _FakePlayer.started = True


class TestMP3Gating(unittest.TestCase):

    def setUp(self):
        self.module = music_player_module
        self.real_supported = self.module._MP3_SUPPORTED
        self.real_intent = self.module.Intent
        self.real_audio_manager = self.module.AudioManager
        _FakeIntent.instances = []

    def tearDown(self):
        self.module._MP3_SUPPORTED = self.real_supported
        self.module.Intent = self.real_intent
        self.module.AudioManager = self.real_audio_manager

    def test_mp3_supported_is_boolean(self):
        self.assertIsInstance(self.module._MP3_SUPPORTED, bool)

    def test_picker_offers_mp3_when_supported(self):
        self.module._MP3_SUPPORTED = True
        self.module.Intent = _FakeIntent
        player = self._bare_player()
        player._open_file_clicked(None)
        pattern = _FakeIntent.instances[0].kwargs["extras"]["path_pattern"]
        self.assertIn(".mp3", pattern)

    def test_picker_hides_mp3_when_unsupported(self):
        self.module._MP3_SUPPORTED = False
        self.module.Intent = _FakeIntent
        player = self._bare_player()
        player._open_file_clicked(None)
        pattern = _FakeIntent.instances[0].kwargs["extras"]["path_pattern"]
        self.assertTrue(".mp3" not in pattern)
        self.assertIn(".wav", pattern)
        self.assertIn(".rtttl", pattern)

    def test_audio_path_accepts_mp3_when_supported(self):
        self.module._MP3_SUPPORTED = True
        self.assertTrue(self.module.MusicPlayer._is_audio_path("/music/song.MP3"))

    def test_audio_path_skips_mp3_when_unsupported(self):
        self.module._MP3_SUPPORTED = False
        self.assertFalse(self.module.MusicPlayer._is_audio_path("/music/song.mp3"))

    def test_folder_falls_through_to_wav_when_mp3_unsupported(self):
        self.module._MP3_SUPPORTED = False
        real_os = self.module.os
        self.module.os = _FakeOS()
        try:
            player = self._bare_player()
            self.assertEqual(player._find_first_audio(["/music/"]), "/music/b.wav")
        finally:
            self.module.os = real_os

    def test_unsupported_mp3_reports_firmware_error(self):
        self.module._MP3_SUPPORTED = False
        self.module.AudioManager = _FakeAudioManager()
        player = self._bare_player()

        def _set_text(text):
            player.shown = text

        player._filename_label = type("Label", (), {"set_text": staticmethod(_set_text)})()
        player.update_ui_threadsafe_if_foreground = lambda callback, *args: callback(*args)
        player._start_playback("/music/song.mp3")
        self.assertIn("firmware", player.shown)

    def _bare_player(self):
        player = object.__new__(self.module.MusicPlayer)
        player._filename = None
        player._playback_attempted_for = None
        player._filename_label = None
        player.startActivityForResult = lambda intent, callback: None
        return player


class _FakeAudioManager:
    STREAM_MUSIC = "music"

    @staticmethod
    def stop():
        raise AssertionError("audio must not start without mp3dec")


class _FakeOS:
    @staticmethod
    def listdir(path):
        return ["a.mp3", "b.wav"]


if __name__ == "__main__":
    unittest.main()
