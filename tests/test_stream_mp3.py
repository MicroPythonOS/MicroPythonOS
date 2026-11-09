# Unit tests for MP3 routing in AudioManager and MP3Stream's desktop fallback.
import os
import unittest

from mpos.testing import (
    MockMachine,
    MockThread,
    inject_mocks,
)
from mpos.testing.mocks import MockSharedPreferences, create_mock_module

inject_mocks({
    "machine": MockMachine(),
    "_thread": MockThread,
    "mpos.shared_preferences": create_mock_module("mpos.shared_preferences", SharedPreferences=MockSharedPreferences),
})

from mpos.audio.audiomanager import AudioManager
from mpos.audio import stream_mp3
from mpos.audio import stream_wav

I2S_PINS = {"sck": 2, "ws": 47, "sd": 16}


class _FakeStream:
    instances = []

    def __init__(self, **kwargs):
        _FakeStream.instances.append(kwargs)

    def play(self):
        pass


class TestPlayerRate(unittest.TestCase):

    def setUp(self):
        AudioManager._instance = None
        MockSharedPreferences.reset_all()
        AudioManager()
        AudioManager.add(AudioManager.Output("speaker", "i2s", i2s_pins=I2S_PINS))
        AudioManager.set_volume(70)

    def test_mp3_uses_header_sample_rate(self):
        calls = []

        def fake_get_info(path):
            calls.append(path)
            return {"sample_rate": 22050, "channels": 1}

        import mpos.audio.mp3 as mp3_info

        real = mp3_info.get_info
        mp3_info.get_info = fake_get_info
        try:
            player = AudioManager.player(file_path="/music/a.mp3")
            player.output = AudioManager.get_outputs()[0]
            rate = AudioManager.get()._determine_player_rate(player)
        finally:
            mp3_info.get_info = real
        self.assertEqual(rate, 22050)
        self.assertEqual(calls, ["/music/a.mp3"])

    def test_uppercase_mp3_extension(self):
        calls = []

        def fake_get_info(path):
            calls.append(path)
            return {"sample_rate": 44100, "channels": 2}

        import mpos.audio.mp3 as mp3_info

        real = mp3_info.get_info
        mp3_info.get_info = fake_get_info
        try:
            player = AudioManager.player(file_path="/music/LOUD.MP3")
            player.output = AudioManager.get_outputs()[0]
            rate = AudioManager.get()._determine_player_rate(player)
        finally:
            mp3_info.get_info = real
        self.assertEqual(rate, 44100)
        self.assertEqual(len(calls), 1)

    def test_wav_uses_wav_header_sample_rate(self):
        import mpos.audio.stream_wav as wav_module

        real = wav_module.WAVStream.get_wav_info
        wav_module.WAVStream.get_wav_info = (
            lambda path: {"sample_rate": 48000, "channels": 2}
        )
        try:
            player = AudioManager.player(file_path="/music/a.wav")
            player.output = AudioManager.get_outputs()[0]
            rate = AudioManager.get()._determine_player_rate(player)
        finally:
            wav_module.WAVStream.get_wav_info = real
        self.assertEqual(rate, 48000)


class TestStreamDispatch(unittest.TestCase):

    def setUp(self):
        _FakeStream.instances = []
        AudioManager._instance = None
        MockSharedPreferences.reset_all()
        AudioManager()
        AudioManager.add(AudioManager.Output("speaker", "i2s", i2s_pins=I2S_PINS))
        AudioManager.set_volume(70)
        self.real_mp3 = stream_mp3.MP3Stream
        self.real_wav = stream_wav.WAVStream

    def tearDown(self):
        stream_mp3.MP3Stream = self.real_mp3
        stream_wav.WAVStream = self.real_wav

    def _play(self, path):
        player = AudioManager.player(file_path=path)
        player.output = AudioManager.get_outputs()[0]
        player._play_wav()
        return player

    def test_mp3_path_creates_mp3_stream(self):
        stream_mp3.MP3Stream = _FakeStream
        stream_wav.WAVStream = _FakeStream
        self._play("/music/song.mp3")
        self.assertEqual(len(_FakeStream.instances), 1)
        self.assertEqual(_FakeStream.instances[0]["file_path"], "/music/song.mp3")

    def test_mp3_stream_receives_volume_and_repeat(self):
        stream_mp3.MP3Stream = _FakeStream
        stream_wav.WAVStream = _FakeStream
        done = []
        player = AudioManager.player(
            file_path="/music/song.mp3", volume=40, on_complete=done.append
        )
        player.output = AudioManager.get_outputs()[0]
        player.set_repeat(7)
        player._play_wav()
        created = _FakeStream.instances[0]
        self.assertEqual(created["volume"], 40)
        self.assertEqual(created["repeat_count"], 7)
        self.assertEqual(created["warm_ms"], 0)
        self.assertEqual(created["on_complete"], done.append)

    def test_wav_path_creates_wav_stream(self):
        stream_mp3.MP3Stream = _FakeStream
        stream_wav.WAVStream = _FakeStream
        self._play("/music/song.wav")
        self.assertEqual(len(_FakeStream.instances), 1)
        self.assertEqual(_FakeStream.instances[0]["file_path"], "/music/song.wav")


class _FakeSys:
    def __init__(self, platform):
        self.platform = platform


class TestMP3StreamDesktop(unittest.TestCase):

    def setUp(self):
        self.stream = stream_mp3.MP3Stream("/music/song.mp3", 0, 70, I2S_PINS, None)
        self.real_system = os.system
        # The player selection is host specific: pin a Linux platform so the
        # ffplay/mpg123/aplay paths are exercised on every CI runner.
        self.real_sys = stream_mp3.sys
        self.real_wav_sys = stream_wav.sys
        stream_mp3.sys = _FakeSys("linux")
        stream_wav.sys = _FakeSys("linux")

    def tearDown(self):
        os.system = self.real_system
        stream_mp3.sys = self.real_sys
        stream_wav.sys = self.real_wav_sys

    def _only(self, *available):
        def fake_system(command):
            return 0 if any(c in command for c in available) else 1

        os.system = fake_system

    def test_prefers_ffplay(self):
        self._only("ffplay")
        self.assertEqual(self.stream._desktop_player(), "ffplay")

    def test_prefers_afplay_on_macos(self):
        stream_mp3.sys = _FakeSys("darwin")
        self._only("ffplay")
        self.assertEqual(self.stream._desktop_player(), "afplay")

    def test_macos_path_needs_no_decoding(self):
        stream_mp3.sys = _FakeSys("darwin")
        self._only("aplay")
        self.assertEqual(self.stream._desktop_audio_path(), "/music/song.mp3")

    def test_falls_back_to_mpg123(self):
        self._only("mpg123")
        self.assertEqual(self.stream._desktop_player(), "mpg123")

    def test_falls_back_to_aplay_without_decoder(self):
        self._only("aplay", "paplay")
        self.assertEqual(self.stream._desktop_player(), "aplay")

    def test_native_path_needs_no_decoding(self):
        self._only("ffplay")
        self.assertEqual(self.stream._desktop_audio_path(), "/music/song.mp3")

    def test_aplay_path_decodes_to_wav(self):
        self._only("aplay", "paplay")
        calls = []

        def fake_decode(src, dst, volume):
            calls.append((src, dst, volume))
            with open(dst, "wb") as f:
                f.write(b"RIFF")

        real = stream_mp3.decode_to_wav
        stream_mp3.decode_to_wav = fake_decode
        try:
            path = self.stream._desktop_audio_path()
        finally:
            stream_mp3.decode_to_wav = real
        self.assertTrue(path.endswith(".wav"))
        self.assertEqual(calls[0][0], "/music/song.mp3")
        self.assertEqual(calls[0][2], 70)
        os.remove(path)


if __name__ == "__main__":
    unittest.main()
