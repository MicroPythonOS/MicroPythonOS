"""Graphical tests for the Media Player's audio mode."""

import os
import sys
import unittest

import lvgl as lv

from mpos import AppManager, AudioManager, Intent
from mpos.ui.view import remove_and_stop_current_activity, screen_stack

sys.path.insert(0, "apps/com.micropythonos.media_player")

import media_player

WAV = "data/media_player_audio_test.wav"
RTTTL = "data/media_player_rtttl_test.rtttl"
RTTTL_TEXT = "Tune:d=4,o=5,b=120:c"


class FakeOutput:
    def __init__(self, kind="buzzer"):
        self.kind = kind


class FakePlayer:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.started = False
        self.stopped = False
        self.paused = False
        self.seek_ms = None
        self.position = 0
        self.duration = None if "rtttl" in kwargs else 4000
        self.repeat = None
        FakePlayer.instances.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def seek(self, position_ms):
        self.seek_ms = position_ms
        return True

    def is_playing(self):
        return self.started and not self.stopped

    def get_progress_ms(self):
        return self.position

    def get_duration_ms(self):
        return self.duration

    def set_repeat(self, count):
        self.repeat = count


class TestMediaPlayerAudio(unittest.TestCase):

    def setUp(self):
        FakePlayer.instances = []
        self._real_player = AudioManager.__dict__["player"]
        self._real_output = AudioManager.__dict__["get_default_output"]
        AudioManager.player = staticmethod(lambda **kwargs: FakePlayer(**kwargs))
        AudioManager.get_default_output = staticmethod(lambda: FakeOutput())
        try:
            os.mkdir("data")
        except OSError:
            pass
        with open(WAV, "wb") as handle:
            handle.write(b"RIFF")
        with open(RTTTL, "w") as handle:
            handle.write(RTTTL_TEXT)

    def tearDown(self):
        for activity in self._activities():
            try:
                activity._stop_audio()
            except Exception:
                pass
        AudioManager.player = self._real_player
        AudioManager.get_default_output = self._real_output
        while len(screen_stack) > 1:
            remove_and_stop_current_activity()
        for path in (WAV, RTTTL):
            try:
                os.remove(path)
            except OSError:
                pass

    def _activities(self):
        return [entry[0] for entry in screen_stack]

    def _activity(self):
        for entry in screen_stack:
            if hasattr(entry[0], "audio_label"):
                return entry[0]
        return None

    def _launch(self, path=WAV):
        self.assertTrue(AppManager.start_app(
            "com.micropythonos.media_player", Intent(action="view", data=path)))
        activity = self._activity()
        self.assertIsNotNone(activity, "Media Player activity not on the stack")
        return activity

    def test_audio_intent_opens_the_audio_view_and_starts_the_player(self):
        activity = self._launch()
        player = activity._audio_player
        self.assertIsNotNone(player)
        self.assertEqual(player.kwargs["file_path"], WAV)
        self.assertTrue(player.started)
        self.assertEqual(player.repeat, 1)
        self.assertEqual(activity.audio_label.get_text(), "media_player_audio_test.wav")
        self.assertFalse(activity._bar.has_flag(lv.obj.FLAG.HIDDEN))
        self.assertFalse(activity.audio_icon.has_flag(lv.obj.FLAG.HIDDEN))
        self.assertTrue(activity.image.has_flag(lv.obj.FLAG.HIDDEN))
        self.assertTrue(activity._is_active())
        self.assertIsNotNone(activity._audio_timer)

    def test_pause_seek_and_duration_go_to_the_player(self):
        activity = self._launch()
        player = activity._audio_player

        activity._toggle_pause()
        self.assertTrue(player.paused)
        self.assertTrue(activity._paused)
        self.assertEqual(activity._play_icon.get_text(), lv.SYMBOL.PLAY)
        activity._toggle_pause()
        self.assertFalse(player.paused)
        self.assertFalse(activity._paused)
        self.assertEqual(activity._play_icon.get_text(), lv.SYMBOL.PAUSE)

        activity._request_seek(1234)
        self.assertEqual(player.seek_ms, 1234)
        activity._request_seek(-5)
        self.assertEqual(player.seek_ms, 0)

        player.position = 1500
        self.assertEqual(activity._position_ms(), 1500)
        self.assertEqual(activity._duration_ms(), 4000)

    def test_the_control_bar_scrubs_audio(self):
        activity = self._launch()
        player = activity._audio_player

        class _Event:
            def __init__(self, code):
                self.code = code

            def get_code(self):
                return self.code

        activity._seek.set_value(900, False)
        activity._seek_event(_Event(lv.EVENT.RELEASED))
        self.assertEqual(player.seek_ms, 900)

    def test_audio_keeps_playing_when_the_activity_is_paused(self):
        activity = self._launch()
        player = activity._audio_player

        activity.onPause(None)
        self.assertFalse(player.stopped, "audio stopped in the background")
        self.assertIs(activity._audio_player, player)
        self.assertIsNone(activity._audio_timer)

        activity.onResume(None)
        self.assertIsNotNone(activity._audio_timer)
        self.assertFalse(activity._bar.has_flag(lv.obj.FLAG.HIDDEN))

    def test_completion_shows_the_finished_message(self):
        activity = self._launch()
        generation = activity._audio_generation
        activity._on_audio_finished(generation, "Finished: test")
        self.assertIsNone(activity._audio_player)
        self.assertTrue(activity.status_label.get_text().startswith("Finished:"))
        self.assertIsNone(activity._audio_timer)

    def test_switching_files_ignores_the_old_players_callback(self):
        activity = self._launch()
        old_generation = activity._audio_generation
        activity._start_media(WAV)
        new_player = activity._audio_player
        self.assertIsNot(new_player, None)
        # A late completion from the replaced player must not tear down the new
        # one.
        activity._on_audio_finished(old_generation, "Finished: old")
        self.assertIs(activity._audio_player, new_player)

    def test_folder_picks_can_mix_video_and_audio(self):
        folder = "data/media_player_folder_test"
        try:
            os.mkdir(folder)
        except OSError:
            pass
        names = ("01_first.wav", "02_second.avi", "03_third.mjpeg",
                 "04_tune.rtttl", "05_note.txt")
        for name in names:
            with open(folder + "/" + name, "wb") as handle:
                handle.write(b"x")
        try:
            activity = self._launch()
            media = activity._media_from([folder + "/"])
            self.assertEqual(media, [
                folder + "/01_first.wav",
                folder + "/02_second.avi",
                folder + "/03_third.mjpeg",
                folder + "/04_tune.rtttl",
            ])
        finally:
            for name in names:
                try:
                    os.remove(folder + "/" + name)
                except OSError:
                    pass
            try:
                os.rmdir(folder)
            except OSError:
                pass


    def test_rtttl_plays_through_the_buzzer_with_degraded_controls(self):
        activity = self._launch(RTTTL)
        player = activity._audio_player
        self.assertTrue(activity._audio_is_rtttl)
        self.assertEqual(player.kwargs["rtttl"], RTTTL_TEXT)
        self.assertFalse("file_path" in player.kwargs)
        self.assertEqual(player.kwargs["output"].kind, "buzzer")
        self.assertTrue(player.started)
        self.assertTrue(activity._seek.has_flag(lv.obj.FLAG.HIDDEN))
        for label in (activity._rewind_icon, activity._play_icon,
                      activity._forward_icon):
            self.assertTrue(label.get_parent().has_flag(lv.obj.FLAG.HIDDEN))
        self.assertFalse(activity._restart_icon.get_parent().has_flag(
            lv.obj.FLAG.HIDDEN))
        self.assertIsNone(activity._audio_timer)
        self.assertEqual(activity._duration_ms(), 0)
        self.assertEqual(activity._position_ms(), 0)
        activity._request_seek(500)
        self.assertIsNone(player.seek_ms)
        activity._toggle_pause()
        self.assertFalse(player.paused)

    def test_rtttl_restart_reopens_the_tune(self):
        activity = self._launch(RTTTL)
        first = activity._audio_player
        activity._restart_from_start()
        second = activity._audio_player
        self.assertIsNot(second, first)
        self.assertTrue(first.stopped)
        self.assertTrue(second.started)
        self.assertTrue(activity._audio_is_rtttl)

    def test_mp3_is_only_accepted_when_the_firmware_can_decode_it(self):
        # Use the source module directly: AppManager executes the app without
        # registering it under a name the test can reach in sys.modules.
        activity = self._launch()
        original = media_player._MP3_SUPPORTED
        try:
            media_player._MP3_SUPPORTED = True
            self.assertTrue(media_player.MediaPlayer._is_audio_path(activity, "LOUD.MP3"))
            media_player._MP3_SUPPORTED = False
            self.assertFalse(media_player.MediaPlayer._is_audio_path(activity, "LOUD.MP3"))
            self.assertTrue(media_player.MediaPlayer._is_audio_path(activity, "LOUD.WAV"))
        finally:
            media_player._MP3_SUPPORTED = original


if __name__ == "__main__":
    unittest.main()
