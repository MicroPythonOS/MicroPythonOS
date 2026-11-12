import os
import sys
import time
import unittest

import lvgl as lv

from mpos import AppManager, Intent
from mpos.ui.view import screen_stack

sys.path.insert(0, "apps/com.micropythonos.video_player")

import video_player


CLIP = "data/video_player_test.mjpeg"
CLIP_WAV = "data/video_player_test.wav"
AVI = "data/video_player_test.avi"
FRAMES = 20
FPS = 15
SIDECAR_MS = 2000


def make_jpeg(width, height, payload=b"x"):
    out = bytearray(b"\xff\xd8")
    out += b"\xff\xe0" + bytes([0, 16]) + b"JFIF\x00" + bytes(9)
    out += b"\xff\xc0" + bytes([0, 11, 8, height >> 8, height & 255,
                                width >> 8, width & 255, 3])
    out += b"\x01\x11\x00\x02\x11\x00\x03\x11\x00"
    out += b"\xff\xda" + bytes([0, 8]) + b"\x01\x01\x00\x00\x3f\x00"
    out += payload + b"\xff\xd9"
    return bytes(out)


def _avi_chunk(chunk_id, payload):
    out = chunk_id + len(payload).to_bytes(4, "little") + bytes(payload)
    if len(payload) & 1:
        out += b"\x00"
    return out


def _avi_list(kind, payload):
    return _avi_chunk(b"LIST", kind + bytes(payload))


def make_avi(frames, audio_chunks, audio_tag=1, bits=16, block_align=0,
             samples_per_block=0, fourcc=b"MJPG", fps=15, width=160, height=120):
    """A minimal AVI: hdrl with one MJPEG stream and one audio stream."""
    avih = bytearray(56)
    avih[0:4] = (1000000 // fps).to_bytes(4, "little")
    avih[16:20] = len(frames).to_bytes(4, "little")
    avih[32:36] = width.to_bytes(4, "little")
    avih[36:40] = height.to_bytes(4, "little")
    video_header = bytearray(56)
    video_header[0:4] = b"vids"
    video_header[4:8] = fourcc
    video_header[20:24] = (1).to_bytes(4, "little")
    video_header[24:28] = fps.to_bytes(4, "little")
    video_header[32:36] = len(frames).to_bytes(4, "little")
    bitmap = bytearray(40)
    bitmap[0:4] = (40).to_bytes(4, "little")
    bitmap[4:8] = width.to_bytes(4, "little")
    bitmap[8:12] = height.to_bytes(4, "little")
    bitmap[12:14] = (1).to_bytes(2, "little")
    bitmap[14:16] = (24).to_bytes(2, "little")
    bitmap[16:20] = fourcc
    hdrl = _avi_chunk(b"avih", avih)
    hdrl += _avi_list(b"strl", _avi_chunk(b"strh", video_header)
                      + _avi_chunk(b"strf", bitmap))
    align = block_align or 2
    audio_header = bytearray(56)
    audio_header[0:4] = b"auds"
    audio_header[20:24] = (align).to_bytes(4, "little")
    audio_header[24:28] = (22050 * align).to_bytes(4, "little")
    fmt = bytearray(16)
    fmt[0:2] = audio_tag.to_bytes(2, "little")
    fmt[2:4] = (1).to_bytes(2, "little")
    fmt[4:8] = (22050).to_bytes(4, "little")
    fmt[8:12] = (22050 * align).to_bytes(4, "little")
    fmt[12:14] = align.to_bytes(2, "little")
    fmt[14:16] = bits.to_bytes(2, "little")
    if audio_tag != 1:
        fmt += (2).to_bytes(2, "little") + samples_per_block.to_bytes(2, "little")
    hdrl += _avi_list(b"strl", _avi_chunk(b"strh", audio_header)
                      + _avi_chunk(b"strf", fmt))
    movi = bytearray()
    for index, frame in enumerate(frames):
        movi += _avi_chunk(b"00dc", frame)
        if index < len(audio_chunks):
            movi += _avi_chunk(b"01wb", audio_chunks[index])
    body = _avi_list(b"hdrl", hdrl) + _avi_list(b"movi", movi)
    return b"RIFF" + (4 + len(body)).to_bytes(4, "little") + b"AVI " + body


class FakeJpegDecoder:
    """Stands in for the native decoder so the pump can run on desktop.

    The real module is a C module on device; here only the decode call and its
    target buffer matter, not the pixels.
    """

    def __init__(self):
        self.calls = 0

    def decode(self, src, dst):
        self.calls += 1
        dst[0:4] = b"\x11\x22\x33\x44"


class TestVideoPlayback(unittest.TestCase):
    def setUp(self):
        self._saved_jpegdec = sys.modules.get("jpegdec")
        self._fake = FakeJpegDecoder()
        sys.modules["jpegdec"] = self._fake
        self._make_clip()

    def tearDown(self):
        for path in (CLIP, CLIP_WAV, AVI):
            try:
                os.remove(path)
            except OSError:
                pass
        if self._saved_jpegdec is None:
            sys.modules.pop("jpegdec", None)
        else:
            sys.modules["jpegdec"] = self._saved_jpegdec

    def _make_clip(self):
        try:
            os.mkdir("data")
        except OSError:
            pass
        with open(CLIP, "wb") as f:
            for _ in range(FRAMES):
                f.write(make_jpeg(160, 120))

    def _make_avi(self, audio=True, **kwargs):
        frames = [make_jpeg(160, 120, bytes([i]) * 16) for i in range(FRAMES)]
        chunks = []
        if audio:
            # One frame's worth of 22050 mono 16-bit, so the feed keeps up with
            # the pacer the way a real interleaved AVI does.
            chunks = [bytes(2940)] * FRAMES
        data = make_avi(frames, chunks, **kwargs)
        with open(AVI, "wb") as handle:
            handle.write(data)

    def _make_sidecar(self, sample_rate=22050):
        samples = sample_rate * SIDECAR_MS // 1000
        data_size = samples * 2
        header = bytearray(44)
        header[0:4] = b"RIFF"
        header[4:8] = (36 + data_size).to_bytes(4, "little")
        header[8:12] = b"WAVE"
        header[12:16] = b"fmt "
        header[16:20] = (16).to_bytes(4, "little")
        header[20:22] = (1).to_bytes(2, "little")
        header[22:24] = (1).to_bytes(2, "little")
        header[24:28] = sample_rate.to_bytes(4, "little")
        header[28:32] = (sample_rate * 2).to_bytes(4, "little")
        header[32:34] = (2).to_bytes(2, "little")
        header[34:36] = (16).to_bytes(2, "little")
        header[36:40] = b"data"
        header[40:44] = data_size.to_bytes(4, "little")
        with open(CLIP_WAV, "wb") as f:
            f.write(header)
            f.write(bytes(data_size))

    def _play_to_end(self, activity):
        deadline = time.ticks_ms() + 20000
        while time.ticks_ms() < deadline and activity._playing:
            lv.timer_handler()
            time.sleep_ms(2)

    def _current_activity(self):
        if not screen_stack:
            return None
        return screen_stack[-1][0]

    def test_intent_plays_clip_and_finishes(self):
        intent = Intent(action="view", data=CLIP)
        self.assertTrue(AppManager.start_app("com.micropythonos.video_player", intent))
        activity = self._current_activity()
        self.assertIsNotNone(activity)
        self.assertEqual(activity.appFullName, "com.micropythonos.video_player")
        self.assertTrue(activity._playing)

        self._play_to_end(activity)

        self.assertFalse(activity._playing)
        self.assertEqual(activity._stats["frames_read"], FRAMES)
        self.assertGreaterEqual(activity._stats["presented"], FRAMES // 2)
        self.assertEqual(activity._play_w, 160)
        self.assertEqual(activity._play_h, 120)
        self.assertIsNotNone(self._fake.calls)
        self.assertGreaterEqual(self._fake.calls, FRAMES // 2)

    def test_launch_without_a_clip_opens_the_picker(self):
        from mpos.ui.file_explorer_activity import FileExplorerActivity

        self.assertTrue(AppManager.start_app("com.micropythonos.video_player"))
        player = None
        for entry in screen_stack:
            activity = entry[0]
            # The app runs as its own module, so match by package name rather
            # than by class object; the picker inherits the caller's name.
            if (getattr(activity, "appFullName", "") == "com.micropythonos.video_player"
                    and not isinstance(activity, FileExplorerActivity)):
                player = activity
        self.assertIsNotNone(player, "video player not on the stack")
        self.assertTrue(player._intro_shown)
        self.assertIsNone(player._pending_path)
        # The picker was pushed on top of the player, not left on a blank screen.
        self.assertIsInstance(screen_stack[-1][0], FileExplorerActivity)

    def test_avi_plays_with_the_sound_inside_the_file(self):
        self._make_avi()
        intent = Intent(action="view", data=AVI)
        self.assertTrue(AppManager.start_app("com.micropythonos.video_player", intent))
        activity = self._current_activity()
        self.assertIsNotNone(activity)
        self.assertTrue(activity._playing)
        self.assertEqual(activity._audio_used_path, AVI)
        self.assertIsNotNone(activity._audio)

        self._play_to_end(activity)

        self.assertFalse(activity._playing)
        self.assertEqual(activity._stats["frames_read"], FRAMES)
        self.assertGreaterEqual(activity._stats["presented"], FRAMES // 2)
        audio = activity._audio_last
        self.assertIsNotNone(audio)
        self.assertEqual(audio.rate, 22050)
        self.assertTrue(audio.written > 0)
        self.assertEqual(audio.underruns, 0)

    def test_avi_with_an_unsupported_audio_codec_plays_without_sound(self):
        self._make_avi(audio_tag=0x55, bits=0)
        intent = Intent(action="view", data=AVI)
        self.assertTrue(AppManager.start_app("com.micropythonos.video_player", intent))
        activity = self._current_activity()
        self.assertIsNotNone(activity)
        self.assertIsNone(activity._audio)
        self.assertIn("MP3", activity.status_label.get_text())

        self._play_to_end(activity)
        self.assertEqual(activity._stats["frames_read"], FRAMES)

    def test_avi_with_an_unsupported_video_codec_explains_why(self):
        self._make_avi(fourcc=b"H264")
        intent = Intent(action="view", data=AVI)
        self.assertTrue(AppManager.start_app("com.micropythonos.video_player", intent))
        activity = self._current_activity()
        self.assertIsNotNone(activity)
        self.assertFalse(activity._playing)
        text = activity.status_label.get_text()
        self.assertIn("H264", text)
        self.assertIn("MJPEG", text)

    def test_loop_restarts_the_clip(self):
        self._make_avi()
        intent = Intent(action="view", data=AVI, extras={"loop": "1"})
        self.assertTrue(AppManager.start_app("com.micropythonos.video_player", intent))
        activity = self._current_activity()
        self.assertIsNotNone(activity)
        self.assertTrue(activity._loop)
        deadline = time.ticks_ms() + 8000
        while (time.ticks_ms() < deadline
               and activity._stats["frames_read"] < FRAMES + 5):
            lv.timer_handler()
            time.sleep_ms(2)
        self.assertTrue(activity._playing, "loop stopped instead of restarting")
        self.assertTrue(activity._stats["frames_read"] >= FRAMES + 5,
                        "only %d frames, no restart" % activity._stats["frames_read"])
        activity.finish()

    def test_seek_extra_starts_later_in_the_clip(self):
        self._make_avi()
        intent = Intent(action="view", data=AVI, extras={"seek": 700})
        self.assertTrue(AppManager.start_app("com.micropythonos.video_player", intent))
        activity = self._current_activity()
        self.assertIsNotNone(activity)
        self.assertTrue(activity._playing)
        # The seek runs inside the pump, so let it take a pass.
        for _ in range(40):
            lv.timer_handler()
            time.sleep_ms(2)
        # 700ms at 15fps is frame 10 of 20.
        self.assertTrue(activity._pacer.frame >= 9,
                        "started at frame %s" % activity._pacer.frame)
        self._play_to_end(activity)
        self.assertTrue(activity._stats["presented"] < FRAMES)

    def test_small_clip_is_played_from_memory(self):
        from video_engine import MemoryFile

        intent = Intent(action="view", data=CLIP, extras={"preload": "1"})
        self.assertTrue(AppManager.start_app("com.micropythonos.video_player", intent))
        activity = self._current_activity()
        self.assertTrue(activity._preloaded)
        self.assertIsInstance(activity._reader._file, MemoryFile)

        self._play_to_end(activity)
        self.assertEqual(activity._stats["frames_read"], FRAMES)
        self.assertTrue(activity._stats["presented"] >= FRAMES // 2)

    def test_clips_stream_by_default(self):
        from video_engine import MemoryFile

        intent = Intent(action="view", data=CLIP)
        self.assertTrue(AppManager.start_app("com.micropythonos.video_player", intent))
        activity = self._current_activity()
        self.assertFalse(activity._preloaded)
        self.assertFalse(isinstance(activity._reader._file, MemoryFile))
        self._play_to_end(activity)
        self.assertEqual(activity._stats["frames_read"], FRAMES)

    def test_a_second_launch_plays_the_new_clip(self):
        self._make_avi()
        self.assertTrue(AppManager.start_app(
            "com.micropythonos.video_player", Intent(action="view", data=CLIP)))
        first = self._current_activity()
        self.assertTrue(first._playing)
        self.assertTrue(AppManager.start_app(
            "com.micropythonos.video_player", Intent(action="view", data=AVI)))
        second = self._current_activity()
        self.assertIsNot(second, first, "same activity reused for a new clip")
        self.assertTrue(second._playing)
        self.assertEqual(second._play_path, AVI)
        self.assertFalse(first._playing, "the old clip kept running behind the new one")

    def test_tap_pauses_and_resumes(self):
        self._make_avi()
        intent = Intent(action="view", data=AVI)
        self.assertTrue(AppManager.start_app("com.micropythonos.video_player", intent))
        activity = self._current_activity()
        self.assertTrue(activity._playing)
        self.assertTrue(activity._bar.has_flag(lv.obj.FLAG.HIDDEN))

        activity._image_clicked(None)
        self.assertTrue(activity._paused)
        self.assertFalse(activity._bar.has_flag(lv.obj.FLAG.HIDDEN),
                         "the controls should show while paused")
        self.assertIsNone(activity._audio)

        # Frame ticking stops, so the picture stays put.
        before = activity._stats["presented"]
        activity._frame_tick()
        self.assertEqual(activity._stats["presented"], before)

        activity._image_clicked(None)
        self.assertFalse(activity._paused)
        self.assertIsNotNone(activity._audio, "resuming should reopen the sound")
        activity._stop_playback()

    def test_controls_hide_after_a_few_seconds(self):
        intent = Intent(action="view", data=CLIP, extras={"loop": "1"})
        self.assertTrue(AppManager.start_app("com.micropythonos.video_player", intent))
        activity = self._current_activity()
        activity._show_controls(0)
        self.assertFalse(activity._bar.has_flag(lv.obj.FLAG.HIDDEN))
        deadline = time.ticks_ms() + 3000
        while time.ticks_ms() < deadline and not activity._bar.has_flag(lv.obj.FLAG.HIDDEN):
            lv.timer_handler()
            time.sleep_ms(2)
        self.assertTrue(activity._bar.has_flag(lv.obj.FLAG.HIDDEN),
                        "controls never auto-hid")
        activity.finish()

    def test_play_button_toggles_and_close_is_deferred(self):
        intent = Intent(action="view", data=CLIP, extras={"loop": "1"})
        self.assertTrue(AppManager.start_app("com.micropythonos.video_player", intent))
        activity = self._current_activity()
        # The bar's play/pause button drives the same toggle as a tap.
        activity._toggle_pause()
        self.assertTrue(activity._paused)
        self.assertEqual(activity._play_icon.get_text(), lv.SYMBOL.PLAY)
        activity._toggle_pause()
        self.assertFalse(activity._paused)
        self.assertEqual(activity._play_icon.get_text(), lv.SYMBOL.PAUSE)

        # Closing from the pump must not tear the screen down inside the pass.
        activity._request_exit()
        self.assertTrue(activity._exit_requested)
        self.assertTrue(activity._playing, "finish ran inside the pump")
        activity._stop_playback()

    def test_deferred_exit_does_not_finish_another_activity(self):
        intent = Intent(action="view", data=CLIP, extras={"loop": "1"})
        self.assertTrue(AppManager.start_app("com.micropythonos.video_player", intent))
        activity = self._current_activity()
        activity._request_exit()
        # Something else came to the front before the deferred call ran.
        activity._has_foreground = False
        for _ in range(5):
            lv.timer_handler()
            time.sleep_ms(2)
        self.assertIs(self._current_activity(), activity,
                      "the deferred exit finished an activity that was gone")
        activity._has_foreground = True

    def test_report_survives_a_deleted_status_label(self):
        intent = Intent(action="view", data=CLIP, extras={"loop": "1"})
        self.assertTrue(AppManager.start_app("com.micropythonos.video_player", intent))
        activity = self._current_activity()
        doomed = lv.label(lv.screen_active())
        doomed.delete()
        activity.status_label = doomed
        # A queued stop can outlive the screen; reporting must not raise.
        activity._stop_playback()
        self.assertIsNone(activity.status_label)

    def test_picking_a_folder_plays_every_clip_in_order(self):
        folder = "data/video_playlist_test"
        try:
            os.mkdir(folder)
        except OSError:
            pass
        first = folder + "/01_first.mjpeg"
        second = folder + "/02_second.mjpeg"
        for path in (first, second):
            with open(path, "wb") as f:
                for _ in range(4):
                    f.write(make_jpeg(160, 120))

        intent = Intent(action="view", data=CLIP)
        self.assertTrue(AppManager.start_app("com.micropythonos.video_player", intent))
        activity = self._current_activity()
        activity._stop_playback()
        activity._on_file_picked(
            {"result_code": True, "data": {"paths": [folder + "/"]}})
        self.assertEqual(activity._playlist, [first, second])
        self.assertTrue(activity._playing)

        self._play_to_end(activity)

        self.assertEqual(activity._play_path, second,
                         "the folder did not advance to the second clip")
        os.remove(first)
        os.remove(second)
        os.rmdir(folder)

    def test_a_folder_pick_replaces_the_clip_that_is_playing(self):
        folder = "data/video_switch_test"
        try:
            os.mkdir(folder)
        except OSError:
            pass
        first = folder + "/01_first.mjpeg"
        second = folder + "/02_second.mjpeg"
        for path in (first, second):
            with open(path, "wb") as f:
                for _ in range(4):
                    f.write(make_jpeg(160, 120))

        intent = Intent(action="view", data=CLIP)
        self.assertTrue(AppManager.start_app("com.micropythonos.video_player", intent))
        activity = self._current_activity()
        self.assertTrue(activity._playing)

        # Picking a folder while a clip is already playing must stop it first:
        # two pumps would read from the same reader.
        stops = []
        original_stop = activity._stop_playback

        def counting_stop():
            stops.append(1)
            original_stop()

        activity._stop_playback = counting_stop
        activity._on_file_picked(
            {"result_code": True, "data": {"paths": [folder + "/"]}})
        self.assertTrue(stops, "the running clip was not stopped first")
        self.assertEqual(activity._playlist, [first, second])
        self.assertTrue(activity._playing)

        self._play_to_end(activity)

        self.assertEqual(activity._play_path, second,
                         "the folder did not replace the running clip")
        os.remove(first)
        os.remove(second)
        os.rmdir(folder)

    def test_seek_bar_scrubs_to_a_position(self):
        self._make_avi()
        intent = Intent(action="view", data=AVI, extras={"loop": "1"})
        self.assertTrue(AppManager.start_app("com.micropythonos.video_player", intent))
        activity = self._current_activity()
        for _ in range(20):
            lv.timer_handler()
            time.sleep_ms(2)
        self.assertTrue(activity._duration_ms() >= 1200,
                        "duration %s" % activity._duration_ms())

        activity._toggle_pause()
        self.assertFalse(activity._bar.has_flag(lv.obj.FLAG.HIDDEN),
                         "seeking needs the bar on screen")

        class _Event:
            def __init__(self, code):
                self.code = code

            def get_code(self):
                return self.code

        activity._seek.set_value(900, False)
        activity._seek_event(_Event(lv.EVENT.RELEASED))
        for _ in range(30):
            lv.timer_handler()
            time.sleep_ms(2)
        self.assertTrue(activity._paused, "a seek while paused resumed playback")
        self.assertTrue(activity._position_ms() >= 800,
                        "position %s" % activity._position_ms())

    def test_sidecar_audio_is_streamed_with_the_frames(self):
        self._make_sidecar()
        intent = Intent(action="view", data=CLIP)
        self.assertTrue(AppManager.start_app("com.micropythonos.video_player", intent))
        activity = self._current_activity()
        self.assertIsNotNone(activity)
        self.assertEqual(activity._audio_used_path, CLIP_WAV)
        self.assertIsNotNone(activity._audio)

        self._play_to_end(activity)

        audio = activity._audio_last
        self.assertIsNotNone(audio)
        self.assertEqual(audio.rate, 22050)
        self.assertEqual(audio.channels, 1)
        # ~1.3s of a 15fps 20 frame clip at 44.1kB/s: within a queue of the
        # real total, and never behind the video clock.
        expected = int(FRAMES * 1000 / FPS) * 44100 // 1000
        self.assertTrue(audio.written >= expected - 2 * 44100 // 10,
                        "wrote %d, expected about %d" % (audio.written, expected))
        self.assertTrue(audio.written <= expected + 2 * 44100 // 10,
                        "wrote %d, expected about %d" % (audio.written, expected))
        self.assertEqual(audio.underruns, 0)
        self.assertGreaterEqual(audio.min_pending_ms, 0)


if __name__ == "__main__":
    unittest.main()
