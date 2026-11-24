import gc
import logging
import os
import sys
import time

import lvgl as lv

import mpos
from mpos import Activity, AudioManager, DisplayMetrics, Intent, SDCardManager

from video_audio import AudioTrack, I2SSink, NullSink, WavSource, sidecar_path
from video_avi import AviReader, UnsupportedFormat
from video_engine import (MemoryFile, MjpegReader, Pacer, fps_from_name,
                          jpeg_dimensions, sniff_format)

logger = logging.getLogger(__name__)

try:
    import mp3dec  # noqa: F401
    _MP3_SUPPORTED = True
except ImportError:
    _MP3_SUPPORTED = False

try:
    import jpegdec
except ImportError:
    jpegdec = None

try:
    from machine import Timer
except ImportError:
    Timer = None


def _run_deferred(func):
    try:
        func()
    except Exception as e:
        logger.error("media_player: deferred %s failed: %s", func, e)


def _hide_widget(widget):
    """Hide a widget, tolerating one the screen has already deleted.

    A stop can be queued - a scheduled call on device, an LVGL async one
    elsewhere - and the activity can be torn down before it runs, so by the
    time it does, these references point at deleted objects. Nothing here
    carries the picture, so a dead widget is not an error.
    """
    if widget is None:
        return
    try:
        widget.add_flag(lv.obj.FLAG.HIDDEN)
    except lv.LvReferenceError:
        pass


def compute_stats(durations_ms):
    n = len(durations_ms)
    total = 0
    for d in durations_ms:
        total += d
    avg = total / n
    ordered = sorted(durations_ms)
    idx = n * 95 // 100
    if idx >= n:
        idx = n - 1
    return {
        "frames": n,
        "avg_ms": avg,
        "fps": 1000.0 / avg if avg > 0 else 0.0,
        "p95_ms": ordered[idx],
    }


def make_frame_rgb565(w, h, phase):
    row = bytearray()
    for x in range(w):
        r = (x * 32 // w + phase * 11) & 31
        g = (x * 64 // w + phase * 29) & 63
        b = ((w - 1 - x) * 32 // w + phase * 7) & 31
        v = (r << 11) | (g << 5) | b
        row.append(v & 255)
        row.append(v >> 8)
    buf = bytearray()
    for _ in range(h):
        buf.extend(row)
    return buf


def fps_from_name(path):
    """Get the frame rate from a name like ruler_320x240_15fps.mjpeg.

    MJPEG has no container, so the rate is not in the stream. The convention
    for the test clips is the only source; callers can also pass an explicit
    "fps" extra.
    """
    name = path.rsplit("/", 1)[-1].lower()
    end = name.find("fps")
    if end <= 0:
        return None
    start = end
    while start > 0 and name[start - 1].isdigit():
        start -= 1
    if start == end:
        return None
    try:
        value = int(name[start:end])
    except ValueError:
        return None
    return value if 1 <= value <= 120 else None


class MediaPlayer(Activity):

    FULL_W = 320
    FULL_H = 240
    HALF_W = 160
    HALF_H = 120
    N_FRAMES = 300
    DEFAULT_FPS = 15
    READ_CHUNK = 32768
    READ_CAP = 65536
    PUMP_TICK_MS = 5
    PUMP_FRAMES_PER_PASS = 4
    PUMP_MAX_WAIT_MS = 20
    VIDEO_EXTENSIONS = (".avi", ".mjpeg", ".mjpg")
    AUDIO_EXTENSIONS = (".wav", ".mp3", ".rtttl")
    AUDIO_TICK_MS = 100
    ENDLESS_REPEAT_COUNT = 1_000_000
    CONTROL_COUNT = 5
    CONTROL_WIDTH = 56
    CONTROL_PITCH = 62
    # Optional: read the clip into RAM before playing (`preload` extra). It is
    # off by default because on this board it loses: a 1.1MB clip goes from
    # 15.7 to 1.3 ms of read per frame, but the start grows by 1.7s and the
    # pump's own jitter rises from 7.5 to 19.4 ms/frame, so the framerate drops
    # (13.9 -> 11.9 fps). See docs/apps/video-performance.md.
    PRELOAD_MAX_BYTES = 3 * 1024 * 1024
    PRELOAD_HEADROOM = 1 * 1024 * 1024
    # Sound the demuxer runs ahead with before the first frame, so the sink can
    # be primed without waiting for the pump to present anything.
    AUDIO_PRIME_MS = 300
    # Media lives in a directory per kind at the card root, like /sdcard/audio.
    # The early entries keep cards that still carry the ClipTV-era clip set
    # usable without moving anything.
    PICK_START_DIRS = ("/data/video", "/sdcard/video", "/data/audio",
                       "/sdcard/audio", "/sdcard/clips", "/sdcard", "/data")
    # LVGL's sysmon prints once a second. Copying that to the console while the
    # app sits idle floods the REPL and makes an mpremote session fail, so it is
    # only echoed for a short window after the app resumes; the FPS label keeps
    # updating. 0 disables the echo entirely.
    SYSMON_LOG_MS = 8000

    def onCreate(self):
        self._timer = None
        self._bufs = {}
        self._dscs = None
        self._sysmon_samples = []
        self._sysmon_log_deadline = 0
        self._reset_run_state()
        # Playback state.
        self._playing = False
        self._reader = None
        self._play_bufs = None
        self._play_dscs = None
        self._play_dsc_i = 0
        self._play_w = 0
        self._play_h = 0
        self._stats = None
        self._pacer = None
        self._fps = self.DEFAULT_FPS
        self._play_started_ms = 0
        self._first_frame_ms = 0
        self._play_path = ""
        self._preloaded = False
        self._preload_forced = None
        self._paused = False
        self._pause_frame = 0
        self._controls_until = 0
        self._exit_requested = False
        self._seek_dragging = False
        self._seek_duration = 0
        self._reported = True
        self._own_pump = False
        self._pump_timer = None
        self._pass_pending = False
        self._task_handler = None
        # Audio state: a sidecar WAV or a stream inside the container.
        self._audio = None
        self._audio_last = None
        self._audio_used_path = ""
        self._embedded_audio = None
        # Audio-only playback through AudioManager (WAV/MP3), which brings its
        # own output selection, volume and desktop backends.
        self._audio_player = None
        self._audio_path = ""
        self._audio_timer = None
        self._audio_icon_data = None
        self._audio_icon_dsc = None
        self._audio_generation = 0
        self._audio_is_rtttl = False
        intent = self.getIntent()
        extras = getattr(intent, "extras", None) or {}
        path = extras.get("filename") or getattr(intent, "data", None)
        self._pending_path = path or None
        self._playlist = []
        self._playlist_i = 0
        self._intro_shown = False
        self._loop = False
        self._start_at_ms = 0
        self._seek_request_ms = None
        self._read_play_extras()
        self._audio_override = extras.get("audio") if "audio" in extras else None
        self._fps_forced = False
        try:
            self._fps = int(extras.get("fps")) or self.DEFAULT_FPS
            self._fps_forced = "fps" in extras and extras.get("fps") is not None
        except (TypeError, ValueError):
            self._fps = self.DEFAULT_FPS

        screen = lv.obj()
        screen.remove_flag(lv.obj.FLAG.SCROLLABLE)
        # A 1:1 clip leaves bars when it does not fill the panel; they should be
        # black rather than the theme background. This object sits behind
        # everything and only appears while a video is on screen, so the picker
        # and the labels keep the theme background.
        self.video_bg = lv.obj(screen)
        self.video_bg.set_size(lv.pct(100), lv.pct(100))
        self.video_bg.align(lv.ALIGN.CENTER, 0, 0)
        self.video_bg.set_style_bg_color(lv.color_hex(0x000000), lv.PART.MAIN)
        self.video_bg.set_style_bg_opa(lv.OPA.COVER, lv.PART.MAIN)
        self.video_bg.set_style_border_width(0, lv.PART.MAIN)
        self.video_bg.set_style_radius(0, lv.PART.MAIN)
        self.video_bg.set_style_pad_all(0, lv.PART.MAIN)
        self.video_bg.remove_flag(lv.obj.FLAG.CLICKABLE)
        self.video_bg.add_flag(lv.obj.FLAG.HIDDEN)
        self.image = lv.image(screen)
        self.image.center()
        self.image.add_flag(lv.obj.FLAG.CLICKABLE)
        self.image.add_event_cb(self._image_clicked, lv.EVENT.CLICKED, None)
        screen.add_event_cb(self._key_pressed, lv.EVENT.KEY, None)
        self.title_label = lv.label(screen)
        self.title_label.set_text("Media Player")
        self.title_label.align(lv.ALIGN.TOP_LEFT, 4, 4)
        self.status_label = lv.label(screen)
        self.status_label.set_text("idle")
        self.status_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.status_label.set_width(lv.pct(90))
        self.status_label.align(lv.ALIGN.TOP_LEFT, 4, 28)
        # Audio mode shows the app's own icon (a video frame with a music note)
        # and the file name instead of a picture.
        self.audio_icon = lv.image(screen)
        self.audio_icon.align(lv.ALIGN.CENTER, 0, -35)
        self.audio_icon.add_flag(lv.obj.FLAG.CLICKABLE)
        self.audio_icon.add_event_cb(self._image_clicked, lv.EVENT.CLICKED, None)
        self.audio_icon.add_flag(lv.obj.FLAG.HIDDEN)
        self.audio_label = lv.label(screen)
        self.audio_label.set_text("")
        self.audio_label.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.audio_label.set_width(lv.pct(90))
        self.audio_label.set_style_text_align(lv.TEXT_ALIGN.CENTER, lv.PART.MAIN)
        self.audio_label.align(lv.ALIGN.CENTER, 0, 35)
        self.audio_label.add_flag(lv.obj.FLAG.CLICKABLE)
        self.audio_label.add_event_cb(self._image_clicked, lv.EVENT.CLICKED, None)
        self.audio_label.add_flag(lv.obj.FLAG.HIDDEN)
        self._load_audio_icon()
        self.fps_label = lv.label(screen)
        self.fps_label.set_text("sysmon: - FPS")
        self.fps_label.align(lv.ALIGN.BOTTOM_LEFT, 4, -46)
        full_btn = lv.button(screen)
        full_btn.align(lv.ALIGN.BOTTOM_MID, -70, -4)
        full_btn.add_event_cb(lambda e: self.start_benchmark(self.FULL_W, self.FULL_H), lv.EVENT.CLICKED, None)
        full_lbl = lv.label(full_btn)
        full_lbl.set_text("320x240")
        full_lbl.center()
        half_btn = lv.button(screen)
        half_btn.align(lv.ALIGN.BOTTOM_MID, 70, -4)
        half_btn.add_event_cb(lambda e: self.start_benchmark(self.HALF_W, self.HALF_H), lv.EVENT.CLICKED, None)
        half_lbl = lv.label(half_btn)
        half_lbl.set_text("160x120 x2")
        half_lbl.center()
        self._full_btn = full_btn
        self._half_btn = half_btn
        open_btn = lv.button(screen)
        open_btn.align(lv.ALIGN.TOP_RIGHT, -4, -4)
        open_btn.add_event_cb(self._pick_file, lv.EVENT.CLICKED, None)
        open_lbl = lv.label(open_btn)
        open_lbl.set_text("Open")
        open_lbl.center()
        self._open_btn = open_btn
        self._bar = lv.obj(screen)
        self._bar.set_size(lv.pct(100), 66)
        self._bar.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        self._bar.set_style_bg_color(lv.color_hex(0x000000), lv.PART.MAIN)
        self._bar.set_style_bg_opa(lv.OPA._70, lv.PART.MAIN)
        self._bar.set_style_border_width(0, lv.PART.MAIN)
        self._bar.set_style_radius(0, lv.PART.MAIN)
        self._bar.set_style_pad_all(0, lv.PART.MAIN)
        self._bar.remove_flag(lv.obj.FLAG.SCROLLABLE)
        self._bar.add_flag(lv.obj.FLAG.HIDDEN)
        self._seek = lv.slider(self._bar)
        self._seek.set_size(lv.pct(100) - 16, 18)
        self._seek.align(lv.ALIGN.TOP_MID, 0, 3)
        self._seek.set_range(0, 1000)
        self._seek.set_value(0, False)
        self._seek.add_event_cb(self._seek_event, lv.EVENT.PRESSED, None)
        self._seek.add_event_cb(self._seek_event, lv.EVENT.RELEASED, None)
        # Evenly spread across the bar: rewind, restart, play/pause, forward,
        # close. The FF/REW glyphs are not in the badge font, so the seek
        # controls are drawn as "<<" / ">>".
        offsets, control_width = self._control_slots(
            DisplayMetrics.width() or self._bar.get_width() or self.FULL_W)
        self._rewind_icon = self._make_control(
            self._bar, "<<", lambda e: self._seek_by(-self.SEEK_STEP_MS),
            offsets[0], control_width)
        self._restart_icon = self._make_control(
            self._bar, lv.SYMBOL.REFRESH, lambda e: self._restart_from_start(),
            offsets[1], control_width)
        self._play_icon = self._make_control(
            self._bar, lv.SYMBOL.PLAY, self._toggle_pause, offsets[2],
            control_width)
        self._forward_icon = self._make_control(
            self._bar, ">>", lambda e: self._seek_by(self.SEEK_STEP_MS),
            offsets[3], control_width)
        self._close_icon = self._make_control(
            self._bar, lv.SYMBOL.CLOSE, lambda e: self._request_exit(),
            offsets[4], control_width)

        self._overlays = [self.title_label, self.status_label, self.fps_label,
                          open_btn, full_btn, half_btn, self._bar]
        self.setContentView(screen)

    def onResume(self, screen):
        super().onResume(screen)
        self._sysmon_log_deadline = time.ticks_add(time.ticks_ms(), self.SYSMON_LOG_MS)
        lv.log_register_print_cb(self._sysmon_cb)
        if self._pending_path:
            path = self._pending_path
            self._pending_path = None
            self._playlist = []
            self._playlist_i = 0
            if not self._is_audio_path(path) and jpegdec is None:
                self.status_label.set_text("JPEG decoder not available")
                return
            self._start_media(path)
            return
        if self._audio_player is not None:
            if self._audio_player.is_playing():
                self._show_audio_view()
                self._start_audio_timer()
                return
            self._stop_audio()
            self._show_audio_view()
            self._play_icon.set_text(lv.SYMBOL.PLAY)
            self.status_label.set_text("Finished: %s" % self.audio_label.get_text())
        if not self._intro_shown:
            # Launched from the app list: show the clips instead of a blank
            # screen. Only once, so cancelling the picker does not reopen it.
            self._intro_shown = True
            self._pick_file()

    def onPause(self, screen):
        # Video owns the display pump, so it must stop. Audio keeps playing in
        # the background like the Music Player does; only its UI timer goes.
        super().onPause(screen)
        self._stop_playback()
        self._stop_timer()
        self._stop_audio_timer()
        lv.log_register_print_cb(None)
        self._bufs = {}
        self._dscs = None
        gc.collect()

    def _load_audio_icon(self):
        """Show the app icon next to the file name in audio mode."""
        for base in ("apps/com.micropythonos.media_player",
                     "builtin/apps/com.micropythonos.media_player",
                     "/builtin/apps/com.micropythonos.media_player"):
            try:
                with open(base + "/icon_64x64.png", "rb") as handle:
                    data = handle.read()
            except OSError:
                continue
            self._audio_icon_data = data
            self._audio_icon_dsc = lv.image_dsc_t({
                "data_size": len(data),
                "data": data,
            })
            self.audio_icon.set_src(self._audio_icon_dsc)
            return
        self.audio_icon.set_src(lv.SYMBOL.AUDIO)

    def _show_audio_view(self):
        self.image.add_flag(lv.obj.FLAG.HIDDEN)
        self.fps_label.add_flag(lv.obj.FLAG.HIDDEN)
        self._full_btn.add_flag(lv.obj.FLAG.HIDDEN)
        self._half_btn.add_flag(lv.obj.FLAG.HIDDEN)
        self.audio_icon.remove_flag(lv.obj.FLAG.HIDDEN)
        self.audio_label.remove_flag(lv.obj.FLAG.HIDDEN)
        self.title_label.remove_flag(lv.obj.FLAG.HIDDEN)
        self.status_label.remove_flag(lv.obj.FLAG.HIDDEN)
        self._open_btn.remove_flag(lv.obj.FLAG.HIDDEN)
        self._bar.remove_flag(lv.obj.FLAG.HIDDEN)
        self._set_audio_controls(not self._audio_is_rtttl)

    def _set_audio_controls(self, seek_enabled):
        """Show the controls the current audio format can actually honour.

        RTTTL is a buzzer tune with no sample position, so only restart and
        close make sense; hiding the scrubber and pause controls is clearer
        than leaving dead buttons on screen.
        """
        if seek_enabled:
            self._seek.remove_flag(lv.obj.FLAG.HIDDEN)
        else:
            self._seek.add_flag(lv.obj.FLAG.HIDDEN)
        controls = (self._rewind_icon, self._play_icon, self._forward_icon)
        for label in controls:
            parent = label.get_parent()
            if parent is None:
                continue
            if seek_enabled:
                parent.remove_flag(lv.obj.FLAG.HIDDEN)
            else:
                parent.add_flag(lv.obj.FLAG.HIDDEN)

    def _show_video_view(self):
        self.audio_icon.add_flag(lv.obj.FLAG.HIDDEN)
        self.audio_label.add_flag(lv.obj.FLAG.HIDDEN)
        self.image.remove_flag(lv.obj.FLAG.HIDDEN)
        self._full_btn.remove_flag(lv.obj.FLAG.HIDDEN)
        self._half_btn.remove_flag(lv.obj.FLAG.HIDDEN)
        self._open_btn.remove_flag(lv.obj.FLAG.HIDDEN)
        self._set_audio_controls(True)

    def _read_play_extras(self):
        """Loop and seek flags belong to the clip being started.

        The framework may re-use this activity for a new intent, in which case
        onCreate does not run again and last clip's flags would stick.
        """
        extras = getattr(self.getIntent(), "extras", None) or {}
        self._loop = str(extras.get("loop", "")).lower() in ("1", "true", "yes")
        preload = str(extras.get("preload", "")).lower()
        self._preload_forced = True if preload in ("1", "true", "yes") else (
            False if preload in ("0", "false", "no") else None)
        try:
            self._start_at_ms = int(extras.get("seek", 0) or 0)
        except (TypeError, ValueError):
            self._start_at_ms = 0

    CONTROLS_MS = 3000

    @staticmethod
    def _control_slots(width):
        """Evenly spaced control slots that stay on a narrow bar.

        The pitch follows the bar (capped at the 320px design's 62px) and the
        buttons shrink with it, so five controls fit a 240px screen instead of
        the outermost pair hanging past both edges.
        """
        pitch = width // MediaPlayer.CONTROL_COUNT
        if pitch > MediaPlayer.CONTROL_PITCH:
            pitch = MediaPlayer.CONTROL_PITCH
        if pitch < 16:
            pitch = 16
        button_width = MediaPlayer.CONTROL_WIDTH
        if button_width > pitch - 2:
            button_width = pitch - 2
        middle = MediaPlayer.CONTROL_COUNT // 2
        offsets = []
        for index in range(MediaPlayer.CONTROL_COUNT):
            offsets.append((index - middle) * pitch)
        return offsets, button_width

    def _make_control(self, parent, symbol, callback, x_offset, width=None):
        button = lv.button(parent)
        button.set_size(self.CONTROL_WIDTH if width is None else width, 40)
        button.align(lv.ALIGN.BOTTOM_MID, x_offset, -2)
        button.set_style_bg_opa(lv.OPA.TRANSP, lv.PART.MAIN)
        button.set_style_border_width(0, lv.PART.MAIN)
        button.set_style_shadow_width(0, lv.PART.MAIN)
        button.add_event_cb(lambda event, action=callback: action(event), lv.EVENT.CLICKED, None)
        label = lv.label(button)
        label.set_text(symbol)
        label.set_style_text_color(lv.color_hex(0xFFFFFF), lv.PART.MAIN)
        label.set_style_text_font(lv.font_montserrat_20, lv.PART.MAIN)
        label.center()
        return label

    def _focus_image(self):
        """Make the picture the focused object for the duration of playback.

        A/ENTER then sends CLICKED to it (pause) instead of activating an
        overlay button that is not even on screen.
        """
        group = lv.group_get_default()
        if group is None:
            return
        try:
            group.add_obj(self.image)
            lv.group_focus_obj(self.image)
        except Exception as e:
            logger.error("media_player: cannot focus the picture: %s", e)

    def _show_controls(self, ms=None):
        self._bar.remove_flag(lv.obj.FLAG.HIDDEN)
        self._controls_until = 0 if ms is None else time.ticks_ms() + ms
        self._update_play_icon()
        # The bar was hidden while playing, so the scrubber still holds the
        # position it had when it last showed (usually 0). Put it where
        # playback actually is, or tapping to pause shows a stale slider.
        self._sync_scrubber()

    def _hide_controls(self):
        _hide_widget(self._bar)
        self._controls_until = 0

    def _update_play_icon(self):
        self._play_icon.set_text(lv.SYMBOL.PLAY if self._paused else lv.SYMBOL.PAUSE)

    def _request_exit(self):
        """Leave without tearing down from inside the pump's callback.

        On device the pump runs from a machine.Timer callback. Finishing the
        activity (and deinit()-ing that timer) from inside it left the device
        unresponsive; the same applies when the request arrives from a gesture
        event, which the pump dispatches inside its own LVGL pass.
        """
        if self._exit_requested:
            return
        self._exit_requested = True
        self._defer(self._finish_now)

    def _defer(self, func):
        """Run func outside the pump callback and outside the LVGL pass."""
        if self._own_pump:
            try:
                import micropython
                micropython.schedule(_run_deferred, func)
                return
            except Exception as e:
                logger.error("media_player: cannot schedule the exit: %s", e)
        lv.async_call(lambda _: _run_deferred(func), None)

    def _finish_now(self):
        """Stop playback, then finish only while this is the top activity.

        Another activity can be pushed while the exit is deferred (an app was
        launched, the caller went back); finish() would then pop that activity
        instead of this one.
        """
        self._stop_playback()
        self._stop_audio()
        if self.has_foreground():
            self.finish()

    def onBackPressed(self, screen):
        """Consume the back gesture and leave through the deferred path."""
        self._request_exit()
        return True

    def _pick_file(self, event=None):
        self.status_label.set_text("pick a file")
        patterns = list(self.VIDEO_EXTENSIONS) + list(self.AUDIO_EXTENSIONS)
        if not _MP3_SUPPORTED:
            patterns.remove(".mp3")
        intent = Intent(
            action="pick_file",
            extras={"start_dir": self._pick_start_dir(),
                    "path_pattern": patterns},
        )
        self.startActivityForResult(intent, self._on_file_picked)

    def _pick_start_dir(self):
        for path in self.PICK_START_DIRS:
            try:
                if os.stat(path)[0] & 0x4000:
                    return path
            except OSError:
                continue
        return "/"

    def _on_file_picked(self, result):
        if not result or not result.get("result_code"):
            self.status_label.set_text("Tap Open to choose a file")
            return
        paths = result.get("data", {}).get("paths", [])
        media = self._media_from(paths)
        if not media:
            self.status_label.set_text("No playable media in there")
            return
        self._playlist = media
        self._playlist_i = 0
        self._start_media(media[0])

    def _media_from(self, paths):
        """Expand picked files and folders into the media to play, in order.

        Picking a folder means "play everything in it": the items run in name
        order, which is the order a naming scheme like 01_... already gives.
        Folders may mix video and audio; each item is routed when it starts.
        """
        media = []
        seen = set()
        for path in paths:
            if path.endswith("/"):
                try:
                    names = sorted(os.listdir(path.rstrip("/") or "/"))
                except OSError:
                    continue
                for name in names:
                    if not self._is_media_path(name):
                        continue
                    item = path + name
                    if item not in seen:
                        seen.add(item)
                        media.append(item)
            elif self._is_media_path(path):
                if path not in seen:
                    seen.add(path)
                    media.append(path)
        return media

    def _is_audio_path(self, path):
        lower = path.lower()
        if lower.endswith(".mp3"):
            return _MP3_SUPPORTED
        return lower.endswith((".wav", ".rtttl"))

    def _is_media_path(self, path):
        lower = path.lower()
        if lower.endswith(self.VIDEO_EXTENSIONS):
            return True
        return self._is_audio_path(path)

    def _advance_playlist(self):
        """Start the next item of a folder pick; wrap around only when looping."""
        if not self._playlist:
            return False
        nxt = self._playlist_i + 1
        if nxt >= len(self._playlist):
            if not self._loop:
                return False
            nxt = 0
        self._playlist_i = nxt
        self._start_media(self._playlist[nxt])
        return True

    def _start_media(self, path):
        """Route one file to the video pump or the AudioManager player."""
        self._stop_playback()
        self._stop_audio(wait=True)
        if path.lower().endswith(".mp3") and not _MP3_SUPPORTED:
            self._show_audio_view()
            self.audio_label.set_text(path.rsplit("/", 1)[-1])
            self._audio_failed("Error: MP3 playback needs a newer firmware")
            return
        if self._is_audio_path(path):
            self._start_audio(path)
        elif jpegdec is None:
            self._show_video_view()
            self._show_overlays()
            self.status_label.set_text("JPEG decoder not available")
        else:
            self._start_clip(path)

    def _start_clip(self, path):
        # A clip can be started while another one is playing (picking a new
        # file, a folder result, a second launch). Two pumps on one screen
        # fight over the reader and the display, so the old one goes first.
        if self._playing:
            self._stop_playback()
        if not self._fps_forced:
            self._fps = fps_from_name(path) or self._fps
        self._show_video_view()
        self._play(path)

    def _is_active(self):
        return self._playing or self._audio_player is not None

    def _image_clicked(self, event):
        if not self._is_active():
            return
        self._toggle_pause()
        self._show_controls(None if self._audio_player is not None else self.CONTROLS_MS)

    def _key_pressed(self, event):
        if not self._is_active():
            return
        key = event.get_key()
        if key == lv.KEY.NEXT:
            self._seek_by(self.SEEK_STEP_MS)
            self._show_controls(None if self._audio_player is not None else self.CONTROLS_MS)
        elif key == lv.KEY.PREV:
            self._seek_by(-self.SEEK_STEP_MS)
            self._show_controls(None if self._audio_player is not None else self.CONTROLS_MS)
        elif key == lv.KEY.ESC:
            self._request_exit()

    # ------------------------------------------------------------------
    #  Audio playback (WAV/MP3) through AudioManager.
    #  The video pump owns the display; audio gets its own small timer that
    #  only refreshes the control bar.
    # ------------------------------------------------------------------

    def _start_audio(self, path):
        self._read_play_extras()
        self._playing = False
        self._paused = False
        self._exit_requested = False
        self._stats = None
        self._reader = None
        self._pacer = None
        self._play_path = path
        self._audio_path = path
        self._audio_is_rtttl = path.lower().endswith(".rtttl")
        self._audio_generation += 1
        generation = self._audio_generation
        self._show_audio_view()
        self.audio_label.set_text(path.rsplit("/", 1)[-1])
        self.status_label.set_text("")
        self._show_controls(None)
        self._update_play_icon()
        self._focus_audio()
        SDCardManager.mount()

        if path.lower().endswith(".mp3") and not _MP3_SUPPORTED:
            self._audio_failed("Error: MP3 playback needs a newer firmware")
            return

        output = AudioManager.get_default_output()
        if output is None:
            self._audio_failed("Error: No audio output available")
            return

        rtttl_string = None
        if self._audio_is_rtttl:
            if getattr(output, "kind", None) != "buzzer":
                output = self._find_buzzer_output()
                if output is None:
                    self._audio_failed("Error: RTTTL requires a buzzer output")
                    return
            try:
                with open(path) as handle:
                    rtttl_string = handle.read().strip()
            except Exception as exc:
                logger.error("media_player: cannot read %s: %s", path, exc)
                self._audio_failed("Error: Could not read RTTTL file")
                return
            if rtttl_string.count(":") < 2:
                self._audio_failed("Error: Invalid RTTTL file")
                return

        # Let any other AudioManager playback (the Music Player, a
        # notification) release the I2S or buzzer before taking it.
        self._quiet_other_audio()
        try:
            player_kwargs = dict(
                stream_type=AudioManager.STREAM_MUSIC,
                on_complete=lambda result, token=generation:
                    self._audio_complete(token, result),
                output=output,
            )
            if rtttl_string is not None:
                player_kwargs["rtttl"] = rtttl_string
            else:
                player_kwargs["file_path"] = path
            player = AudioManager.player(**player_kwargs)
            player.set_repeat(
                self.ENDLESS_REPEAT_COUNT
                if self._loop and len(self._playlist) <= 1 else 1)
            self._audio_player = player
            player.start()
        except Exception as exc:
            logger.error("media_player: cannot start %s: %s", path, exc)
            self._audio_player = None
            self._audio_failed("Error: Audio device unavailable or busy")
            return
        self._start_audio_timer()

    @staticmethod
    def _find_buzzer_output():
        for output in AudioManager.get_outputs():
            if getattr(output, "kind", None) == "buzzer":
                return output
        return None

    def _audio_failed(self, message):
        self._stop_audio_timer()
        self._audio_player = None
        self._audio_path = ""
        self._playing = False
        self._paused = False
        self._show_controls(None)
        self._play_icon.set_text(lv.SYMBOL.PLAY)
        self.status_label.set_text(message)
        print("media_player: %s" % message)

    def _audio_complete(self, generation, result=None):
        # Runs on the AudioManager player thread; LVGL is only touched through
        # the activity's deferred UI update.
        self.update_ui_threadsafe_if_foreground(
            self._on_audio_finished, generation, result)

    def _on_audio_finished(self, generation, result=None):
        if generation != self._audio_generation or self._audio_player is None:
            # A stop() from switching files also reports completion; ignore
            # the callbacks of players that are no longer current.
            return
        if result and str(result).lower().startswith("error"):
            self._audio_failed(result)
            return
        # The player thread is already finishing. Drop our handle first so a
        # playlist transition does not wait for a stop() that has nothing to
        # stop (the stream's finally block is about to release the output).
        self._audio_player = None
        self._stop_audio_timer()
        if self._advance_playlist():
            return
        if self._loop and self._restart_audio():
            return
        self._audio_path = ""
        self._paused = False
        self._update_play_icon()
        self.status_label.set_text("Finished: %s" % self.audio_label.get_text())
        self._show_controls(None)
        self._play_icon.set_text(lv.SYMBOL.PLAY)

    def _restart_audio(self):
        path = self._audio_path
        if not path:
            return False
        self._stop_audio(wait=True)
        self._start_audio(path)
        return True

    def _start_audio_timer(self):
        self._stop_audio_timer()
        if self._audio_player is None or self._audio_is_rtttl:
            return
        self._audio_timer = lv.timer_create(self._audio_tick, self.AUDIO_TICK_MS, None)
        self._audio_timer.set_repeat_count(-1)

    def _stop_audio_timer(self):
        timer = self._audio_timer
        self._audio_timer = None
        if timer is not None:
            try:
                timer.delete()
            except Exception as e:
                logger.error("media_player: audio timer stop failed: %s", e)

    def _audio_tick(self, timer=None):
        if self._audio_player is None:
            self._stop_audio_timer()
            return
        self._sync_scrubber()

    def _stop_audio(self, wait=False):
        self._stop_audio_timer()
        player = self._audio_player
        self._audio_player = None
        self._audio_path = ""
        self._paused = False
        if player is not None:
            try:
                player.stop()
            except Exception as e:
                logger.error("media_player: audio stop failed: %s", e)
            if wait:
                # The playback thread tears its I2S down in its finally block.
                # Opening the next stream before that happens would let the
                # old deinit() pull the peripheral out from under it.
                deadline = time.ticks_add(time.ticks_ms(), 500)
                while (player.is_playing()
                       and time.ticks_diff(deadline, time.ticks_ms()) > 0):
                    time.sleep_ms(10)

    def _focus_audio(self):
        group = lv.group_get_default()
        if group is None:
            return
        try:
            group.add_obj(self.audio_label)
            lv.group_focus_obj(self.audio_label)
        except Exception as e:
            logger.error("media_player: cannot focus the audio view: %s", e)

    # ------------------------------------------------------------------
    #  MJPEG playback: read -> decode -> set_src -> refr_now -> pace.
    #  One frame per timer callback, always 1:1 (no LVGL scaling).
    # ------------------------------------------------------------------

    def _play(self, path):
        self._read_play_extras()
        self._playing = True
        self._paused = False
        self._exit_requested = False
        self._hide_controls()
        self._focus_image()
        self._reported = False
        self._play_path = path
        self._play_started_ms = time.ticks_ms()
        self._stats = {
            "read_us": 0,
            "decode_us": 0,
            "set_src_us": 0,
            "refr_us": 0,
            "skip_us": 0,
            "present_us": 0,
            "lvgl_us": 0,
            "pass_us": 0,
            "audio_us": 0,
            "sleep_us": 0,
            "ticks": 0,
            "presented": 0,
            "dropped": 0,
            "seeked": 0,
            "frames_read": 0,
        }
        self.status_label.set_text("loading...")
        SDCardManager.mount()
        self._embedded_audio = None
        clip_data = self._load_clip(path)
        self._preloaded = clip_data is not None
        if self._preloaded:
            print("media_player: preloaded %s (%d bytes)"
                  % (path.rsplit("/", 1)[-1], len(clip_data)))
        try:
            self._reader = self._open_reader(path, clip_data)
            if isinstance(self._reader, AviReader):
                if self._reader.fps and not self._fps_forced:
                    self._fps = self._reader.fps
                try:
                    self._embedded_audio = self._reader.audio_source()
                except UnsupportedFormat as e:
                    # Play the pictures, say why there is no sound.
                    logger.warning("media_player: %s: %s", path, e.message)
                    print("media_player: %s" % e.message)
                    self.status_label.set_text(e.message)
            # Open the sound sink before reading the first frame: its startup
            # silence drains in real time (up to 372ms), so the read, the
            # buffer allocation and the first decode all happen inside that
            # wait instead of after it.
            self._open_audio(path)
            self._prefill_audio()
            frame = self._reader.next()
        except UnsupportedFormat as e:
            logger.error("media_player: %s: %s", path, e.message)
            self._play_failed(e.message)
            return
        except OSError as e:
            logger.error("media_player: cannot open %s: %s", path, e)
            self._play_failed("cannot open %s" % path)
            return
        if frame is None:
            self._play_failed("no frames in %s" % path)
            return
        w, h = jpeg_dimensions(frame)
        if not w or not h:
            logger.error("media_player: %s is not a JPEG stream", path)
            self._play_failed("not a JPEG stream")
            return
        self._play_w, self._play_h = w, h
        frame_bytes = w * h * 2
        self._play_bufs = [bytearray(frame_bytes)]
        try:
            # Two targets so the decoder never writes the frame the panel is
            # still flushing. One is a degraded but working fallback.
            self._play_bufs.append(bytearray(frame_bytes))
        except MemoryError:
            logger.warning("media_player: single decode buffer (MemoryError)")
        self._play_dscs = [self._make_dsc(w, h, b) for b in self._play_bufs]
        self._play_dsc_i = 0
        self._prepare_image(w, h)
        t = time.ticks_us()
        try:
            jpegdec.decode(frame, self._play_bufs[0])
        except Exception as e:
            logger.error("media_player: decode failed: %s", e)
            self._play_failed("decode failed")
            return
        self._stats["decode_us"] += time.ticks_diff(time.ticks_us(), t)
        self._stats["frames_read"] = 1
        self._hide_overlays()
        # Drain the sink's startup silence before anything is shown: that wait
        # is up to a fifth of a second and would otherwise sit between the
        # first frame and sample 0.
        self._audio_ready()
        self.image.set_src(self._play_dscs[0])
        lv.refr_now(None)
        # Frame 0 is on the panel now. The prime lands in microseconds, so
        # sample 0 starts on this same instant and both clocks start here.
        audio_ms = self._audio_start(time.ticks_ms())
        self._stats["presented"] = 1
        now = time.ticks_ms()
        first_ms = time.ticks_diff(now, self._play_started_ms)
        self._first_frame_ms = first_ms
        self._pacer = Pacer(self._fps, audio_ms)
        self._pacer.mark_shown(audio_ms)
        print("media_player: play %s %dx%d %dfps, first frame %dms" % (
            path, w, h, self._fps, first_ms))
        if self._start_at_ms > 0:
            self._seek_request_ms = self._start_at_ms
        self._start_pump()

    def _open_reader(self, path, data=None):
        """Open the demuxer that matches the file, with a readable failure."""
        lower = path.lower()
        source = MemoryFile(data) if data is not None else path
        if lower.endswith(".avi"):
            return AviReader(source)
        if lower.endswith((".mjpeg", ".mjpg")):
            kind = sniff_format(source)
            if kind and "MJPEG" not in kind and "JPEG" not in kind:
                raise UnsupportedFormat(
                    "%s is %s, not MJPEG (this player decodes MJPEG only)"
                    % (path.rsplit("/", 1)[-1], kind))
            return MjpegReader(source, self.READ_CHUNK, self.READ_CAP)
        raise UnsupportedFormat(
            "unsupported video file: %s (this player opens .avi, .mjpeg and .mjpg)"
            % path.rsplit("/", 1)[-1])

    def _play_failed(self, message):
        self._playing = False
        self._stop_playback()
        self._show_overlays()
        self.status_label.set_text(message)
        print("media_player: %s" % message)

    def _prepare_image(self, w, h):
        # 1:1 always. Scaling in the draw path costs ~10x the flush.
        self.image.set_scale(256)
        self.image.set_size(w, h)
        self.image.center()
        self.video_bg.remove_flag(lv.obj.FLAG.HIDDEN)
        # A frame bigger than the panel loses its edges to the centred image,
        # and nothing else would say so.
        disp_w = DisplayMetrics.width() or self.FULL_W
        disp_h = DisplayMetrics.height() or self.FULL_H
        if w > disp_w or h > disp_h:
            message = ("%dx%d clip: only the centre %dx%d is shown "
                       "(re-encode to fit)" % (w, h, disp_w, disp_h))
            logger.warning("media_player: %s", message)
            self.status_label.set_text(message)

    # ----- seeking and looping -------------------------------------------

    SEEK_STEP_MS = 15000

    def _position_ms(self):
        if self._audio_player is not None:
            position = self._audio_player.get_progress_ms()
            return position or 0
        pacer = self._pacer
        if pacer is None:
            return 0
        return pacer.frame * 1000 // self._fps

    def _seek_by(self, delta_ms):
        self._request_seek(self._position_ms() + delta_ms)

    def _request_seek(self, ms):
        """Ask for a seek; the pump performs it.

        The pump runs in a timer callback, so it is the only context that may
        touch the demuxer: seeking from here used to pull the frame queue out
        from under it. AudioManager's streams take a seek request from here
        and perform it on their own playback thread.
        """
        if self._audio_player is not None:
            if self._audio_is_rtttl:
                return
            if ms < 0:
                ms = 0
            self._audio_player.seek(ms)
            return
        self._seek_request_ms = ms

    def _apply_seek(self, ms):
        """Jump both streams to ms."""
        if ms < 0:
            ms = 0
        if self._fps <= 0:
            self._fps = self.DEFAULT_FPS
        return self._restart_at(ms * self._fps // 1000, resume=not self._paused)

    def _restart_from_start(self):
        if self._audio_is_rtttl:
            self._restart_audio()
        else:
            self._request_seek(0)

    def _toggle_pause(self, event=None):
        if self._audio_player is not None:
            if self._audio_is_rtttl:
                return
            if self._paused:
                self._paused = False
                self._audio_player.resume()
            else:
                self._paused = True
                self._audio_player.pause()
            self._show_controls(None)
            self._update_play_icon()
            return
        if not self._playing:
            return
        if self._paused:
            frame = self._pause_frame
            self._paused = False
            self._restart_at(frame)
            self._show_controls(self.CONTROLS_MS)
        else:
            self._paused = True
            self._pause_frame = self._pacer.frame if self._pacer else 0
            # Stop the sound with the picture; resuming reopens the sink, which
            # also gets rid of the ~180ms still queued before the pause.
            self._close_audio()
            self._show_controls(None)
        self._update_play_icon()

    def _restart(self):
        """Loop: start the clip again from the first frame."""
        return self._restart_at(0)

    def _restart_at(self, frame, resume=True):
        """Rewind and resume at `frame`, reopening the sound like a fresh start.

        The sink keeps ~180ms of the old sound queued, so priming on top of it
        would leave the new position mixed with the old one; closing and
        reopening it is the same path a normal start takes and costs the ring's
        drain (~370ms). With resume=False (a seek while paused) it shows the
        frame at the new position and stays paused.
        """
        reader = self._reader
        if not self._playing or reader is None:
            return False
        if frame < 0:
            frame = 0
        try:
            reader.rewind()
            if frame:
                if isinstance(reader, AviReader):
                    # Walk the frames, but not their sound: a seek moves the
                    # soundtrack, it does not play what it passed.
                    reader.skip(frame, False)
                else:
                    reader.skip(frame)
        except Exception as e:
            logger.error("media_player: seek failed: %s", e)
            return False
        if not resume:
            # Scrub preview: present the frame at the new position, no sound.
            self._close_audio()
            self._pacer = Pacer(self._fps, time.ticks_ms() - frame * 1000 // self._fps)
            self._pacer.frame = frame
            self._paused = False
            self._frame_tick()
            self._paused = True
            return True
        self._close_audio()
        if isinstance(reader, AviReader):
            try:
                self._embedded_audio = reader.audio_source()
            except UnsupportedFormat as e:
                logger.warning("media_player: %s", e.message)
                self._embedded_audio = None
        self._open_audio(self._play_path)
        self._prefill_audio()
        now = time.ticks_ms()
        # The pacer counts frames from its start, so back-date it by the frames
        # skipped: otherwise it would wait that long before the next frame.
        self._pacer = Pacer(self._fps, now - frame * 1000 // self._fps)
        self._pacer.frame = frame
        self._pacer.mark_shown(now)
        self._audio_start(now)
        self._playing = True
        if frame == 0:
            print("media_player: loop restart at %d frames" % self._stats["presented"])
        return True

    # ----- audio sidecar -------------------------------------------------
    #
    # The pump feeds the sink, it does not run an AudioManager player: that
    # starts a reader thread of its own, and the two would take turns on the
    # one SD card (already the bottleneck). A refill is one small read plus one
    # I2S write, and it happens between frames, so it costs the frame budget
    # a few ms instead of a whole frame.

    def _open_audio(self, video_path):
        self._audio = None
        self._audio_last = None
        self._audio_used_path = ""
        path = None
        source = self._embedded_audio
        self._embedded_audio = None
        if source is None:
            override = self._audio_override
            if override is not None:
                path = override or None
            else:
                path = sidecar_path(video_path)
            if not path:
                return
        output = None
        if sys.platform == "esp32":
            audio_manager = getattr(mpos, "AudioManager", None)
            output = audio_manager.get_default_output() if audio_manager else None
            if output is None or output.kind != "i2s":
                output = None
        if source is None:
            try:
                source = WavSource(path, preferred_rate=getattr(output, "preferred_sample_rate", None))
            except (OSError, ValueError) as e:
                logger.error("media_player: audio %s unusable: %s", path, e)
                print("media_player: audio %s unusable: %s" % (path, e))
                return
        try:
            if output is not None:
                self._quiet_other_audio()
                sink = I2SSink(output, source.playback_rate, source.channels)
            else:
                sink = NullSink()
            sink.open()
        except Exception as e:
            logger.error("media_player: audio sink failed: %s", e)
            print("media_player: audio sink failed: %s" % e)
            source.close()
            return
        # Preload after the sink is open: reading a few hundred kilobytes
        # takes longer than the ring's startup silence, so the wait costs
        # nothing on the way to the first frame.
        source.preload()
        self._audio = AudioTrack(source, sink)
        self._audio_used_path = path or video_path
        print("media_player: audio %s %s %dHz %s %s" % (
            path or ("in " + video_path.rsplit("/", 1)[-1]), source.format_name,
            source.playback_rate, "mono" if source.channels == 1 else "stereo",
            "in RAM" if source.in_memory else "streaming"))

    def _quiet_other_audio(self):
        """Stop a background player before taking the I2S peripheral.

        Two users of ``machine.I2S(0)`` is not a supported state, and the
        music player closes its own handle from its thread. Stop it and give
        that thread time to finish, or it would deinit our new sink a moment
        after it opens.
        """
        audio_manager = getattr(mpos, "AudioManager", None)
        if audio_manager is None:
            return
        try:
            if audio_manager.get_active_player() is None:
                return
            audio_manager.stop()
            deadline = time.ticks_ms() + 500
            while time.ticks_ms() < deadline:
                if audio_manager.get_active_player() is None:
                    break
                time.sleep_ms(20)
        except Exception as e:
            logger.error("media_player: cannot stop background audio: %s", e)

    def _load_clip(self, path):
        """Read the whole clip into RAM when that is worth it; else None."""
        if self._preload_forced is False:
            return None
        try:
            size = os.stat(path)[6]
        except OSError:
            return None
        if size <= 0 or size > self.PRELOAD_MAX_BYTES:
            return None
        if self._preload_forced is None:
            return None
        if gc.mem_free() < size + self.PRELOAD_HEADROOM:
            logger.warning("media_player: not enough RAM to preload %s", path)
            return None
        data = bytearray(size)
        view = memoryview(data)
        read = 0
        try:
            handle = open(path, "rb")
        except OSError as e:
            logger.error("media_player: cannot preload %s: %s", path, e)
            return None
        try:
            while read < size:
                count = size - read
                if count > 65536:
                    count = 65536
                got = handle.readinto(view[read:read + count])
                if not got:
                    break
                read += got
        finally:
            handle.close()
        if read != size:
            logger.warning("media_player: short preload of %s", path)
            return None
        return data

    def _prefill_audio(self):
        reader = self._reader
        if not isinstance(reader, AviReader) or reader.feed is None:
            return
        try:
            reader.prefill_audio(self.AUDIO_PRIME_MS)
        except Exception as e:
            logger.error("media_player: audio prefill failed: %s", e)

    def _audio_ready(self):
        if self._audio is None:
            return
        try:
            self._audio.ready()
        except Exception as e:
            logger.error("media_player: audio sink not ready: %s", e)
            self._close_audio()

    def _audio_start(self, now_ms):
        if self._audio is None:
            return now_ms
        try:
            return self._audio.start(now_ms)
        except Exception as e:
            logger.error("media_player: audio start failed: %s", e)
            self._close_audio()
            return now_ms

    def _audio_tick(self, now_ms):
        audio = self._audio
        if audio is None or audio.finished:
            return
        try:
            audio.tick(now_ms)
        except Exception as e:
            logger.error("media_player: audio failed: %s", e)
            print("media_player: audio failed: %s" % e)
            try:
                sys.print_exception(e)  # NOQA
            except Exception:
                pass
            self._close_audio()

    def _close_audio(self):
        audio = self._audio
        self._audio = None
        if audio is None:
            return
        self._audio_last = audio
        try:
            audio.stop()
        except Exception as e:
            logger.error("media_player: audio stop failed: %s", e)

    def _audio_report(self):
        audio = self._audio_last
        if audio is None:
            return "no audio"
        frames = (self._stats or {}).get("presented") or 1
        # Both streams follow one clock and a resync jumps the sound forward,
        # so drift is zero by construction; what the run costs is the sound it
        # had to drop to keep that promise.
        rate = audio.clock.byte_rate
        dropped_ms = audio.skipped * 1000 // rate if rate else 0
        total = audio.written + audio.skipped
        dropped_pct = audio.skipped * 100.0 / total if total else 0.0
        return "%s %dHz %s%s: wrote %dB, dropped %dms of sound (%.1f%%) in %d " \
            "resyncs, %d underruns, queue min %dms, read %.2fms write %.2fms " \
            "per frame" % (
                audio.source.format_name, audio.rate,
                "mono" if audio.channels == 1 else "stereo",
                " RAM" if audio.preloaded else " stream",
                audio.written, dropped_ms, dropped_pct, audio.resyncs,
                audio.underruns, audio.min_pending_ms,
                audio.read_us / 1000.0 / frames,
                audio.write_us / 1000.0 / frames)

    # ----- frame pump -------------------------------------------------
    #
    # Where the frame work runs decides how much of the frame budget survives.
    # Inside a framework TaskHandler pass it is charged a quarter of its own
    # duration as a fairness gap before the next pass may start: at 320x240 a
    # frame costs ~65ms of reading, decoding and flushing, so the gap alone
    # (16-21ms) exceeds the 1.6ms of headroom a 15fps clip has. The pump
    # therefore runs its own LVGL passes from a hardware timer on device, and
    # hands them back to the framework when the clip ends.

    def _start_pump(self):
        self._pass_pending = False
        self._own_pump = False
        if self._take_over_passes():
            self._own_pump = True
            self._pump_timer = self._new_pump_timer()
            if self._pump_timer is None:
                self._own_pump = False
                self._give_back_passes()
        if self._own_pump:
            self._set_pump_period(1)
            return
        self._pump_timer = lv.timer_create(self._pump, 1, None)
        self._pump_timer.set_repeat_count(-1)

    def _take_over_passes(self):
        if sys.platform != "esp32":
            return False
        task_handler = getattr(getattr(mpos, "ui", None), "task_handler", None)
        if task_handler is None:
            return False
        try:
            task_handler.disable()
        except Exception as e:
            logger.error("media_player: cannot take over LVGL passes: %s", e)
            return False
        self._task_handler = task_handler
        return True

    def _give_back_passes(self):
        task_handler = self._task_handler
        self._task_handler = None
        if task_handler is None:
            return
        try:
            task_handler.enable()
        except Exception as e:
            logger.error("media_player: cannot return LVGL passes: %s", e)

    def _new_pump_timer(self):
        # ESP32 has hardware timers 0-3; the task handler owns 0 and the
        # connectivity manager takes 1.
        timer = None
        for timer_id in (3, 2, -1):
            try:
                timer = Timer(timer_id)
                break
            except Exception:
                continue
        if timer is None:
            return None
        try:
            timer.init(mode=Timer.PERIODIC, period=self.PUMP_TICK_MS,
                       callback=self._pump_isr)
        except Exception as e:
            logger.error("media_player: no pump timer: %s", e)
            return None
        return timer

    def _pump_isr(self, timer):
        # The pass runs here, not through micropython.schedule(): a scheduled
        # callback only runs when the main thread next yields, and that was
        # measured at 25-75ms, which is most of a small clip's frame budget.
        # The timer keeps a fixed tick; the pass sleeps out the rest of the
        # wait, because re-arming a timer from inside its own callback hangs.
        if self._pass_pending:
            return
        self._pass_pending = True
        try:
            self._pump_pass(0)
        finally:
            self._pass_pending = False

    def _pump_pass(self, _):
        try:
            if self._exit_requested:
                return
            # A seek must land even while paused: that is how scrubbing works.
            self._service_seek()
            if self._paused:
                # Keep the UI alive (the bar's buttons are LVGL widgets) without
                # touching the frame timeline.
                try:
                    lv.task_handler()
                except Exception as e:
                    logger.error("media_player: LVGL pass failed: %s", e)
                time.sleep_ms(self.PUMP_TICK_MS)
                return
            # Present every frame that is due in one callback. Waiting for the
            # next tick between frames would add up to a tick of dead time to
            # each one, which at 320x240 is 5ms out of a 66ms budget.
            for _ in range(self.PUMP_FRAMES_PER_PASS):
                if not self._playing:
                    return
                self._service_seek()
                now = time.ticks_ms()
                t = time.ticks_us()
                self._audio_tick(now)
                stats = self._stats
                if stats is not None:
                    stats["audio_us"] += time.ticks_diff(time.ticks_us(), t)
                wait = self._pacer.wait_ms(now)
                if wait > 1:
                    # The frame is not due yet: return and let the timer fire
                    # again in a tick. Sleeping out the gap inside this callback
                    # is what keeps the interpreter (and therefore the console)
                    # from running while a clip plays; the audio refill and the
                    # frame timing stay on the same tick grid either way.
                    return
                self._service_controls()
                stats = self._stats
                stats["ticks"] += 1
                pass_start = time.ticks_us()
                t = pass_start
                try:
                    lv.task_handler()
                except Exception as e:
                    logger.error("media_player: LVGL pass failed: %s", e)
                stats["lvgl_us"] += time.ticks_diff(time.ticks_us(), t)
                self._frame_tick()
                stats["pass_us"] += time.ticks_diff(time.ticks_us(), pass_start)
        except Exception as e:
            # Never leave the framework without its passes: that freezes the
            # whole UI, so stop playback and hand LVGL back instead. The stop
            # itself is deferred: deinit()-ing the pump timer from inside its
            # callback is what wedges the chip.
            logger.error("media_player: pump pass failed: %s", e)
            sys.print_exception(e)  # NOQA
            self._exit_requested = True
            self._defer(self._stop_playback)
        finally:
            self._pass_pending = False

    def _seek_event(self, event):
        if event.get_code() == lv.EVENT.PRESSED:
            self._seek_dragging = True
        elif event.get_code() == lv.EVENT.RELEASED:
            self._seek_dragging = False
            self._request_seek(self._seek.get_value())

    def _duration_ms(self):
        """Length of the clip or track, or 0 when it cannot be known yet."""
        if self._audio_player is not None:
            duration = self._audio_player.get_duration_ms()
            return duration or 0
        reader = self._reader
        if reader is None or self._fps <= 0:
            return 0
        frames = getattr(reader, "frame_count", 0) or 0
        if not frames:
            # Raw MJPEG has no index: estimate from the average frame size.
            size = getattr(reader, "_size", 0) or 0
            seen = getattr(reader, "frames", 0) or 0
            if size and seen:
                frames = size * seen // reader.sum_frame_bytes
        return frames * 1000 // self._fps

    def _sync_scrubber(self):
        if self._seek_dragging:
            return
        duration = self._duration_ms()
        if duration > 0:
            if duration != self._seek_duration:
                self._seek.set_range(0, duration)
                self._seek_duration = duration
            position = self._position_ms()
            if position > duration:
                position = duration
            self._seek.set_value(position, False)

    def _service_controls(self):
        """Hide the bar once its time is up, unless playback is paused."""
        if self._controls_until and not self._paused:
            if time.ticks_ms() >= self._controls_until:
                self._hide_controls()
            else:
                self._sync_scrubber()

    def _service_seek(self):
        ms = self._seek_request_ms
        if ms is None:
            return
        self._seek_request_ms = None
        self._apply_seek(ms)

    def _pump(self, timer=None):
        # Desktop fallback: the framework keeps passing, an LVGL timer pumps.
        if not self._playing:
            return
        if self._exit_requested:
            return
        self._service_seek()
        if self._paused:
            return
        self._service_controls()
        stats = self._stats
        stats["ticks"] += 1
        pass_start = time.ticks_us()
        self._audio_tick(time.ticks_ms())
        self._set_pump_period(self._frame_tick())
        stats["pass_us"] += time.ticks_diff(time.ticks_us(), pass_start)

    def _frame_tick(self):
        """Present one frame if it is due; return ms until the next check."""
        if not self._playing or self._paused:
            return 1
        stats = self._stats
        now = time.ticks_ms()
        wait = self._pacer.wait_ms(now)
        if wait > 1:
            return wait
        frame_start = time.ticks_us()
        t = frame_start
        frame = self._reader.next()
        stats["read_us"] += time.ticks_diff(time.ticks_us(), t)
        if frame is None:
            if self._advance_playlist():
                return 1
            if self._loop and self._restart():
                return 1
            self._request_exit()
            return 0
        stats["frames_read"] += 1
        buf = self._play_bufs[self._play_dsc_i]
        t = time.ticks_us()
        try:
            jpegdec.decode(frame, buf)
        except Exception as e:
            logger.error("media_player: decode failed: %s", e)
            return 1
        stats["decode_us"] += time.ticks_diff(time.ticks_us(), t)
        dsc = self._play_dscs[self._play_dsc_i]
        self._play_dsc_i = (self._play_dsc_i + 1) % len(self._play_dscs)
        t = time.ticks_us()
        self.image.set_src(dsc)
        stats["set_src_us"] += time.ticks_diff(time.ticks_us(), t)
        t = time.ticks_us()
        lv.refr_now(None)
        stats["refr_us"] += time.ticks_diff(time.ticks_us(), t)
        stats["present_us"] += time.ticks_diff(time.ticks_us(), frame_start)
        stats["presented"] += 1
        now = time.ticks_ms()
        # Drop frames to keep wall-clock time. Reading a dropped frame costs its
        # bytes at SD speed, which on a saturated stream is the whole budget, so
        # seek past it when that is cheaper. Skipping is only worth it once the
        # presenting work alone cannot keep up: otherwise the resync read after
        # the seek costs more than the frame it avoided.
        skip = self._pacer.mark_shown(now)
        if skip:
            t = time.ticks_us()
            if self._saturated() and self._reader.skip(skip):
                stats["seeked"] += skip
            else:
                for _ in range(skip):
                    dropped = self._reader.next()
                    if dropped is None:
                        break
                    stats["frames_read"] += 1
                    stats["dropped"] += 1
            stats["skip_us"] += time.ticks_diff(time.ticks_us(), t)
        return 1

    def _saturated(self):
        """True when presenting one frame costs more than the clip's period.

        Deliberately excludes the time spent dropping frames: counting that
        here makes the first skip a reason for the next one, and the player
        stays in the slow path even when reading the drops would catch up.
        """
        stats = self._stats
        presented = stats["presented"]
        if presented < 4:
            return False
        return stats["present_us"] * self._fps > 1000000 * presented

    def _stop_pump(self):
        timer = self._pump_timer
        self._pump_timer = None
        if timer is not None:
            try:
                if self._own_pump:
                    timer.deinit()
                else:
                    timer.delete()
            except Exception as e:
                logger.error("media_player: pump stop failed: %s", e)
        self._own_pump = False
        self._give_back_passes()

    def _stop_playback(self):
        was_playing = self._playing
        self._playing = False
        if self._audio_player is None:
            self._paused = False
        self._exit_requested = False
        self._hide_controls()
        self._stop_pump()
        self._close_audio()
        if self._reader is not None:
            self._reader.close()
            self._reader = None
        if was_playing:
            self._report_playback()
        self._play_bufs = None
        self._play_dscs = None
        self._pacer = None
        _hide_widget(self.video_bg)

    def _report_playback(self):
        if self._reported or not self._stats:
            return
        self._reported = True
        stats = self._stats
        elapsed_ms = time.ticks_diff(time.ticks_ms(), self._play_started_ms)
        presented = stats["presented"]
        fps = presented * 1000.0 / elapsed_ms if elapsed_ms else 0.0
        frames = presented or 1
        idle_us = elapsed_ms * 1000 - stats["pass_us"]
        if idle_us < 0:
            idle_us = 0
        other_us = idle_us - stats["audio_us"] - stats["sleep_us"]
        if other_us < 0:
            other_us = 0
        report = (
            "%s @ %dx%d: %d frames in %dms = %.2f fps, %d dropped (%d seek) "
            "of %d read, first frame %dms; read %.1fms skip %.1fms decode "
            "%.1fms set_src %.1fms refr %.1fms lvgl %.1fms pass %.1fms idle "
            "%.1fms (audio %.1f sleep %.1f other %.1f) per frame, %d passes"
        ) % (
            self._play_path + (" (RAM)" if self._preloaded else ""),
            self._play_w, self._play_h,
            presented, elapsed_ms, fps,
            stats["dropped"], stats["seeked"], stats["frames_read"],
            self._first_frame_ms,
            stats["read_us"] / 1000.0 / frames,
            stats["skip_us"] / 1000.0 / frames,
            stats["decode_us"] / 1000.0 / frames,
            stats["set_src_us"] / 1000.0 / frames,
            stats["refr_us"] / 1000.0 / frames,
            stats["lvgl_us"] / 1000.0 / frames,
            stats["pass_us"] / 1000.0 / frames,
            idle_us / 1000.0 / frames,
            stats["audio_us"] / 1000.0 / frames,
            stats["sleep_us"] / 1000.0 / frames,
            other_us / 1000.0 / frames,
            stats["ticks"],
        )
        print("media_player: " + report)
        print("media_player: audio " + self._audio_report())
        if self.status_label is not None and not self._playing:
            try:
                self.status_label.set_text(report)
            except lv.LvReferenceError:
                # The widgets can already be gone when a stop is queued and the
                # activity is torn down first; the on-screen report is only
                # cosmetic, so drop the stale label and keep the printed one.
                self.status_label = None

    def _set_pump_period(self, ms):
        # The own pump keeps a fixed tick and sleeps out the rest; only the
        # LVGL-timer fallback has a period to set.
        if self._own_pump or not self._playing or self._pump_timer is None:
            return
        if ms < 1:
            ms = 1
        elif ms > self.PUMP_MAX_WAIT_MS:
            ms = self.PUMP_MAX_WAIT_MS
        self._pump_timer.set_period(ms)

    def _hide_overlays(self):
        for obj in self._overlays:
            _hide_widget(obj)

    def _show_overlays(self):
        for obj in self._overlays:
            obj.remove_flag(lv.obj.FLAG.HIDDEN)

    # ------------------------------------------------------------------
    #  Benchmark mode (no clip given): draw in-RAM frames as fast as the
    #  panel accepts them.
    # ------------------------------------------------------------------

    def start_benchmark(self, w, h):
        self._stop_timer()
        self._reset_run_state()
        key = (w, h)
        bufs = self._bufs.get(key)
        if bufs is None:
            self.status_label.set_text("preparing %sx%s..." % (w, h))
            print("media_player: preparing %sx%s buffers..." % (w, h))
            bufs = [make_frame_rgb565(w, h, 0), make_frame_rgb565(w, h, 1)]
            self._bufs[key] = bufs
        self._dscs = [self._make_dsc(w, h, bufs[0]), self._make_dsc(w, h, bufs[1])]
        self._apply_scale_once(w, h)
        self.image.set_src(self._dscs[0])
        self._sysmon_samples = []
        self.status_label.set_text("running %sx%s %s frames..." % (w, h, self.N_FRAMES))
        print("media_player: benchmark start %sx%s frames=%s" % (w, h, self.N_FRAMES))
        self._timer = lv.timer_create(self._tick, 1, None)

    def _tick(self, timer):
        now = time.ticks_ms()
        if self._last_ms is not None:
            self._durations.append(time.ticks_diff(now, self._last_ms))
        self._last_ms = now
        t0 = time.ticks_ms()
        self.image.set_src(self._dscs[self._idx])
        self._set_src_ms += time.ticks_diff(time.ticks_ms(), t0)
        self._idx ^= 1
        self._count += 1
        if self._count >= self.N_FRAMES:
            self._finish()

    def _finish(self):
        self._stop_timer()
        stats = compute_stats(self._durations)
        set_src_avg = self._set_src_ms / self._count if self._count else 0
        if self._sysmon_samples:
            sysmon_total = 0
            for s in self._sysmon_samples:
                sysmon_total += s
            sysmon_avg = sysmon_total / len(self._sysmon_samples)
        else:
            sysmon_avg = 0
        report = "%s frames: %.1f FPS avg %.1fms p95 %sms set_src %.2fms sysmon %.1f FPS" % (
            stats["frames"], stats["fps"], stats["avg_ms"], stats["p95_ms"], set_src_avg, sysmon_avg)
        self.status_label.set_text(report)
        print("media_player: " + report)

    def _echo_sysmon(self):
        """Whether the sysmon line should also be echoed to the console.

        The label keeps the latest value either way; only the serial echo is
        time-bounded, because it is what floods a REPL or mpremote session.
        """
        return time.ticks_diff(self._sysmon_log_deadline, time.ticks_ms()) > 0

    def _sysmon_cb(self, level, log_str):
        if self._playing:
            # Updating a label during playback would invalidate and re-flush
            # part of the frame we are measuring.
            return
        if isinstance(log_str, bytes):
            log_str = log_str.decode()
        if "sysmon:" in log_str and "FPS" in log_str:
            try:
                fps = int(log_str.split("FPS")[0].split("sysmon:")[1].strip())
            except (IndexError, ValueError):
                return
            self._sysmon_samples.append(fps)
            if self._echo_sysmon():
                print("media_player sysmon FPS: %s" % fps)
            self.fps_label.set_text("sysmon: %s FPS" % fps)

    def _reset_run_state(self):
        self._count = 0
        self._idx = 0
        self._durations = []
        self._set_src_ms = 0
        self._last_ms = None

    def _stop_timer(self):
        if self._timer is not None:
            self._timer.delete()
            self._timer = None

    def _apply_scale_once(self, w, h):
        disp_w = DisplayMetrics.width() or self.FULL_W
        disp_h = DisplayMetrics.height() or self.FULL_H
        scale = min(disp_w * 256 // w, disp_h * 256 // h)
        self.image.set_size(w * scale // 256, h * scale // 256)
        self.image.set_scale(scale)
        self.image.center()

    @staticmethod
    def _make_dsc(w, h, buf):
        return lv.image_dsc_t({
            "header": {
                "magic": lv.IMAGE_HEADER_MAGIC,
                "w": w,
                "h": h,
                "stride": w * 2,
                "cf": lv.COLOR_FORMAT.RGB565,
            },
            "data_size": len(buf),
            "data": buf,
        })
