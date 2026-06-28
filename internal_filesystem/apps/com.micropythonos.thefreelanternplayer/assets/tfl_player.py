# tfl_player.py  (ASCII-only)
# Main activity class: AlbumPlayer
#
# The Free Lantern Player for MicroPythonOS (ESP32-S3).
# - Streams 45s WAV fragments from index.html (Song Title<B>Track No<B>Album<B>frag1<B>frag2...)
# - Keeps a 2-fragment buffer using a background _thread prefetcher
# - Saves playback state every 10s so it can resume after restart
# - Next/Prev jumps to next/prev SONG (not fragment)
# - Shows "Buffering..." when waiting for the next fragment
# - If SD card present with >=70MiB free: prompts to download full album once and then plays from SD
#   * Writes timestamp/manifest on success
#   * If timestamp older than 10 days: verifies online sizes and updates changed files
#   * If timestamp missing but in-progress marker exists: removes last partial file and resumes
# - Volume buttons (Vol-/Vol+) + label; volume applied before every player.start()
# - About button with logo, credits, and basic status
#
# NOTE: On the macOS desktop runner, AudioManager playback may not be supported. In that case
# player.start() will raise ValueError; the UI will show an audio error and skip ahead.

import os
import time
import gc
import _thread

try:
    import lvgl as lv
except Exception:
    lv = None

try:
    import urequests as requests
except ImportError:
    import requests

try:
    import ujson as json
except ImportError:
    import json

from mpos import Activity, sdcard, AudioManager, WidgetAnimator
from mpos.ui.focus import add_focus_border
from mpos.ui.display_metrics import DisplayMetrics  # noqa: F401
from mpos import ConnectivityManager

# -------------------------
# LVGL compatibility shims
# -------------------------
try:
    ANIM_OFF = lv.ANIM.OFF
except Exception:
    try:
        ANIM_OFF = lv.ANIM_OFF
    except Exception:
        ANIM_OFF = 0

try:
    FLAG_HIDDEN = lv.obj.FLAG.HIDDEN
except Exception:
    try:
        FLAG_HIDDEN = lv.OBJ_FLAG.HIDDEN
    except Exception:
        FLAG_HIDDEN = 0

# -------------------------
# Configuration
# -------------------------
BASE_URL  = "http://www.thefreelantern.com/micropythonos/audio/"
INDEX_URL = BASE_URL + "index.html"

SEP = "<B>"
FRAGMENT_SECONDS = 45  # estimate for UI

# Downloader tuning for ESP32-S3
DL_CHUNK_BYTES = 8192
DL_THROTTLE_MS = 5  # raise to 10 if you get audio stutter; 0 for max speed

# Cache requirements for streaming mode
CACHE_TARGET_BYTES = 2 * 1024 * 1024  # need >=2MiB free internal storage for caching
CACHE_DIR = "/cache_audio"

# State file (stored in cache dir)
STATE_SAVE_INTERVAL = 10

# SD mode
SD_MIN_FREE_BYTES  = 70 * 1024 * 1024
SD_MUSIC_ROOT      = "/sdcard/music"
SD_TIMESTAMP_FILE  = SD_MUSIC_ROOT + "/.tfl_album_timestamp.json"
SD_INPROGRESS_FILE = SD_MUSIC_ROOT + "/.tfl_download_in_progress.json"
VERIFY_AFTER_DAYS  = 10

APP_VERSION = "1.0.0"

# Base path for bundled image assets on the LVGL "M:" virtual filesystem.
# The desktop sim cwd is internal_filesystem/ so M: resolves from there.
# icon_64x64.png lives one level above assets/ (app package root).
_ASSET_BASE = "M:apps/com.micropythonos.thefreelanternplayer/assets/"
_ICON_PATH  = "M:apps/com.micropythonos.thefreelanternplayer/icon_64x64.png"

# -------------------------
# Filesystem helpers
# -------------------------
def ensure_dir(path):
    try:
        os.mkdir(path)
    except OSError:
        pass

def exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False

def rm(path):
    try:
        os.remove(path)
    except OSError:
        pass

def free_bytes(path="/"):
    st = os.statvfs(path)
    return st[4] * st[1]

def has_internal_cache_space():
    try:
        return free_bytes("/") >= CACHE_TARGET_BYTES
    except Exception:
        return False

# Choose a writable cache dir (ESP32 prefers /cache_audio; desktop runner may not allow writing to /)
def init_cache_dir():
    global CACHE_DIR
    try:
        ensure_dir(CACHE_DIR)
        # test write
        p = CACHE_DIR + "/.__t"
        with open(p, "w") as f:
            f.write("x")
        rm(p)
    except Exception:
        CACHE_DIR = "cache_audio"
        ensure_dir(CACHE_DIR)

init_cache_dir()
STATE_FILE = CACHE_DIR + "/state.json"

# -------------------------
# Time helpers
# -------------------------
def fmt_mmss(seconds):
    if seconds < 0:
        seconds = 0
    m = seconds // 60
    s = seconds % 60
    return "{:02d}:{:02d}".format(m, s)

def est_song_total_seconds(track_dict):
    return len(track_dict.get("fragments", [])) * FRAGMENT_SECONDS

# -------------------------
# JSON helpers
# -------------------------
def load_json(path):
    try:
        with open(path, "r") as f:
            return json.loads(f.read())
    except Exception:
        return None

def save_json(path, obj):
    tmp = path + ".tmp"
    try:
        with open(tmp, "w") as f:
            f.write(json.dumps(obj))

        # Replace destination
        try:
            os.remove(path)
        except OSError:
            pass

        os.rename(tmp, path)

    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise

# -------------------------
# Playback state
# -------------------------
class PlaybackState:
    def __init__(self):
        self.track = 0
        self.fragment = 0
        self.mode = "stream"
        self.last_save = 0

    def load(self):
        d = load_json(STATE_FILE)
        if d:
            try:
                self.track = int(d.get("track", 0))
                self.fragment = int(d.get("fragment", 0))
            except Exception:
                self.track = 0
                self.fragment = 0
            self.mode = d.get("mode", "stream")
        return self

    def save(self):
        save_json(STATE_FILE, {
            "track": self.track,
            "fragment": self.fragment,
            "mode": self.mode
        })
        self.last_save = time.time()

    def maybe_save(self):
        if time.time() - self.last_save >= STATE_SAVE_INTERVAL:
            try:
                self.save()
            except Exception:
                pass

# -------------------------
# Album index
# -------------------------
class AlbumIndex:
    def __init__(self):
        self.tracks = []

    def load(self):
        # download index
        try:
            r = requests.get(INDEX_URL)
            code = getattr(r, "status_code", None)
            text = r.text
            try:
                r.close()
            except Exception:
                pass
            if (code is not None) and (code != 200):
                raise Exception("HTTP {}".format(code))
        except Exception as ex:
            raise Exception("Failed to download index.html: {}".format(ex))

        lines = text.splitlines()
        if not lines:
            raise Exception("index.html is empty")
        print("INDEX first line:", lines[0])

        tracks = []
        for ln in lines:
            ln = ln.strip()
            if not ln:
                continue
            parts = ln.split(SEP)
            if len(parts) < 4:
                print("Bad index line:", ln)
                continue
            tracks.append({
                "title": parts[0].strip(),
                "trackno": parts[1].strip(),
                "album": parts[2].strip(),
                "fragments": [p.strip() for p in parts[3:] if p.strip()],
            })

        if not tracks:
            raise Exception("No valid tracks parsed from index.html (separator must be '<B>')")

        self.tracks = tracks
        return self

    def all_fragments_flat(self):
        out = []
        for t in self.tracks:
            album = t.get("album", "")
            title = t.get("title", "")
            trackno = t.get("trackno", "")
            for fn in t.get("fragments", []):
                out.append((album, title, trackno, fn))
        return out

# -------------------------
# Download helpers (robust)
# -------------------------
def download_streaming(url, dest, progress=None, chunk=DL_CHUNK_BYTES, throttle_ms=DL_THROTTLE_MS,
                       stop_flag=None):
    r = None
    received = 0
    total = None
    try:
        r = requests.get(url, stream=True)

        try:
            total = int(r.headers.get("Content-Length", 0)) or None
        except Exception:
            total = None

        # Desktop runner often provides full body in .content
        try:
            if hasattr(r, "content") and r.content:
                data = r.content
                with open(dest, "wb") as f:
                    f.write(data)
                received = len(data)
                if progress:
                    progress(received, total)
                return received, total
        except Exception:
            pass

        # Streaming path
        with open(dest, "wb") as f:
            while True:
                buf = r.raw.read(chunk)
                if not buf:
                    break
                if stop_flag and stop_flag():
                    break  # abandon partial download; caller must rm() the .part file
                f.write(buf)
                received += len(buf)
                if progress:
                    progress(received, total)
                if throttle_ms:
                    time.sleep_ms(throttle_ms)

        return received, total

    finally:
        try:
            if r:
                r.close()
        except Exception:
            pass

def get_remote_content_length(url):
    r = None
    try:
        r = requests.get(url, stream=True)
        try:
            cl = r.headers.get("Content-Length", None)
            if cl is None:
                return None
            return int(cl)
        except Exception:
            return None
    finally:
        try:
            if r:
                r.close()
        except Exception:
            pass

# -------------------------
# SD album manager
# -------------------------
class SDAlbumManager:
    def __init__(self, status_cb=None, progress_cb=None):
        self.status = status_cb or (lambda _t: None)
        self.progress = progress_cb or (lambda _p: None)

    def sd_present(self):
        try:
            os.stat("/sdcard")
            return True
        except OSError:
            return False

    def sd_ready(self):
        if not self.sd_present():
            return False
        try:
            return free_bytes("/sdcard") >= SD_MIN_FREE_BYTES
        except Exception:
            return False

    def ensure_dirs(self):
        ensure_dir("/sdcard")
        ensure_dir(SD_MUSIC_ROOT)

    def sd_path_for_fragment(self, album, trackno, title, frag_fn):
        safe_album = str(album).replace("/", "_")
        safe_title = str(title).replace("/", "_")
        safe_fn = str(frag_fn).replace("/", "_")
        album_dir = SD_MUSIC_ROOT + "/" + safe_album
        track_dir = album_dir + "/{}_{}".format(trackno, safe_title)
        ensure_dir(SD_MUSIC_ROOT)
        ensure_dir(album_dir)
        ensure_dir(track_dir)
        return track_dir + "/" + safe_fn

    def handle_incomplete_previous_download(self):
        d = load_json(SD_INPROGRESS_FILE)
        if not d:
            return
        last_path = d.get("last_path")
        if last_path and exists(last_path):
            self.status("Incomplete SD download detected.\nRemoving last partial file:\n{}".format(last_path))
            rm(last_path)

    def should_verify_online(self):
        ts = load_json(SD_TIMESTAMP_FILE)
        if not ts or "timestamp" not in ts:
            return False
        age_s = time.time() - float(ts["timestamp"])
        return age_s >= (VERIFY_AFTER_DAYS * 24 * 3600)

    def build_local_manifest(self, index):
        manifest = {}
        for (album, title, trackno, fn) in index.all_fragments_flat():
            p = self.sd_path_for_fragment(album, trackno, title, fn)
            try:
                st = os.stat(p)
                manifest[fn] = st[6]
            except OSError:
                manifest[fn] = None
        return manifest

    def download_all_missing_or_changed(self, index, force_redownload_changed=False, stop_flag=None):
        self.ensure_dirs()
        self.handle_incomplete_previous_download()

        frags = index.all_fragments_flat()
        total_files = len(frags) if frags else 1
        done_files = 0

        for (album, title, trackno, fn) in frags:
            if stop_flag and stop_flag():
                return False

            url = BASE_URL + fn
            local_path = self.sd_path_for_fragment(album, trackno, title, fn)

            need = not exists(local_path)

            if (not need) and force_redownload_changed:
                remote_len = get_remote_content_length(url)
                if remote_len is not None:
                    try:
                        local_len = os.stat(local_path)[6]
                        if int(local_len) != int(remote_len):
                            need = True
                    except Exception:
                        need = True

            if not need:
                done_files += 1
                self.progress(int((done_files * 100) / total_files))
                continue

            save_json(SD_INPROGRESS_FILE, {
                "timestamp": time.time(),
                "last_path": local_path,
                "last_remote": fn
            })

            self.status("Downloading to SD:\n{}\n{}\n{}".format(album, title, fn))

            def pcb(rcv, tot):
                if tot:
                    pct_file = int((rcv * 100) / tot)
                else:
                    pct_file = 0
                overall = int((done_files * 100) / total_files)
                combined = min(100, overall + int(pct_file / 10))
                self.progress(combined)

            tmp = local_path + ".part"
            rm(tmp)
            download_streaming(url, tmp, progress=pcb, chunk=DL_CHUNK_BYTES, throttle_ms=0)

            rm(local_path)
            try:
                os.rename(tmp, local_path)
            except Exception:
                # fallback copy -- do NOT re-download; tmp is already complete
                with open(tmp, "rb") as fsrc:
                    with open(local_path, "wb") as fdst:
                        while True:
                            b = fsrc.read(4096)
                            if not b:
                                break
                            fdst.write(b)
                rm(tmp)

            done_files += 1
            self.progress(int((done_files * 100) / total_files))
            gc.collect()

        rm(SD_INPROGRESS_FILE)

        manifest = self.build_local_manifest(index)
        save_json(SD_TIMESTAMP_FILE, {
            "timestamp": time.time(),
            "manifest": manifest
        })
        self.progress(100)
        self.status("SD download complete.")
        return True

    def verify_online_and_update_if_needed(self, index, stop_flag=None):
        ts = load_json(SD_TIMESTAMP_FILE)
        if not ts:
            return True

        old_manifest = ts.get("manifest", {})
        remote_files = [fn for (_, _, _, fn) in index.all_fragments_flat()]
        old_files = list(old_manifest.keys()) if isinstance(old_manifest, dict) else []

        changed = (set(remote_files) != set(old_files))

        if (not changed) and isinstance(old_manifest, dict):
            self.status("Verifying SD album vs online...")
            for i, fn in enumerate(remote_files):
                if stop_flag and stop_flag():
                    return False
                url = BASE_URL + fn
                remote_len = get_remote_content_length(url)
                if remote_len is None:
                    continue
                old_len = old_manifest.get(fn, None)
                if old_len is None or int(old_len) != int(remote_len):
                    changed = True
                    break
                if i % 10 == 0:
                    self.progress(int((i * 100) / max(1, len(remote_files))))

        if changed:
            self.status("Online album changed. Updating SD...")
            return self.download_all_missing_or_changed(index, force_redownload_changed=True, stop_flag=stop_flag)

        self.status("SD verified OK. Refreshing timestamp.")
        local_manifest = self.build_local_manifest(index)
        save_json(SD_TIMESTAMP_FILE, {"timestamp": time.time(), "manifest": local_manifest})
        self.progress(100)
        return True

# -------------------------
# Prefetcher (_thread)
# -------------------------
class Prefetcher:
    def __init__(self):
        self.lock = _thread.allocate_lock()
        self.todo = None       # (url, path)
        self.err = None
        self.stop = False
        _thread.start_new_thread(self._run, ())

    def request(self, url, path):
        with self.lock:
            self.todo = (url, path)
            self.err = None

    def get_err(self):
        with self.lock:
            return self.err

    def clear_err(self):
        with self.lock:
            self.err = None

    def shutdown(self):
        self.stop = True

    def _run(self):
        while not self.stop:
            job = None
            with self.lock:
                job = self.todo
                self.todo = None

            if job:
                url, path = job
                try:
                    tmp = path + ".part"
                    rm(tmp)
                    download_streaming(url, tmp, stop_flag=lambda: self.stop)
                    rm(path)
                    try:
                        os.rename(tmp, path)
                    except Exception:
                        # if rename fails, fall back to copy approach
                        with open(tmp, "rb") as fsrc:
                            with open(path, "wb") as fdst:
                                while True:
                                    b = fsrc.read(4096)
                                    if not b:
                                        break
                                    fdst.write(b)
                        rm(tmp)
                    with self.lock:
                        self.err = None
                except Exception as ex:
                    with self.lock:
                        self.err = str(ex)
            else:
                time.sleep_ms(50)

# -------------------------
# Streaming player
# -------------------------
class StreamPlayer:
    def __init__(self, index, state, status_cb, buffering_cb, stop_flag, command_getter, volume_getter):
        self.index = index
        self.state = state
        self.status = status_cb
        self.buffering = buffering_cb
        self.stop_flag = stop_flag
        self.command_getter = command_getter
        self.volume_getter = volume_getter
        self.pref = Prefetcher()
        self._last_gc_ms = 0
        self._last_cleanup_ms = 0

    def shutdown(self):
        try:
            self.pref.shutdown()
        except Exception:
            pass

    # Preserve original fragment filenames in cache for easier debugging
    def _cache_path(self, track_idx, frag_idx):
        fn = self.index.tracks[track_idx]["fragments"][frag_idx]
        fn = str(fn).replace("/", "_")
        return "{}/{}".format(CACHE_DIR, fn)

    def _maybe_gc(self):
        # Avoid GC at fragment boundaries; do it occasionally while playing.
        try:
            now = time.ticks_ms()
            if time.ticks_diff(now, self._last_gc_ms) < 5000:
                return
            # Only GC when memory is getting low-ish.
            if gc.mem_free() < 80_000:
                gc.collect()
                self._last_gc_ms = now
        except Exception:
            pass

    def _maybe_cleanup_old_fragments(self, track_idx, current_frag_idx, keep_last=3):
        # Avoid deleting files exactly at fragment boundaries.
        # Keep a small rolling cache: current/next/(next+1) and delete older ones later.
        try:
            now = time.ticks_ms()
            if time.ticks_diff(now, self._last_cleanup_ms) < 2000:
                return
            self._last_cleanup_ms = now
            if keep_last < 1:
                keep_last = 1
            delete_before = current_frag_idx - (keep_last - 1)
            if delete_before <= 0:
                return
            t = self.index.tracks[track_idx]
            frags = t.get("fragments", [])
            # Delete fragments strictly older than the kept window.
            for i in range(0, min(delete_before, len(frags))):
                p = self._cache_path(track_idx, i)
                if exists(p):
                    rm(p)
        except Exception:
            # never let cleanup break playback
            pass


    def _wrap_track(self):
        n = len(self.index.tracks)
        if n <= 0:
            self.state.track = 0
            return
        if self.state.track >= n:
            self.state.track = 0
        if self.state.track < 0:
            self.state.track = n - 1

    def _apply_next_song(self):
        self.state.track += 1
        self._wrap_track()
        self.state.fragment = 0
        try:
            self.state.save()
        except Exception:
            pass

    def _apply_prev_song(self):
        self.state.track -= 1
        self._wrap_track()
        self.state.fragment = 0
        try:
            self.state.save()
        except Exception:
            pass

    def _audio_error(self, msg):
        print("TFLPlayer audio error:", msg)
        self.status("Audio error.\nSkipping to next song.")

    def play_forever(self):
        if not self.index.tracks:
            self.status("No tracks in index.")
            return

        self._wrap_track()

        while not self.stop_flag():
            self._wrap_track()
            t = self.index.tracks[self.state.track]
            frags = t.get("fragments", [])
            if not frags:
                self._apply_next_song()
                continue

            if self.state.fragment < 0:
                self.state.fragment = 0
            if self.state.fragment >= len(frags):
                self._apply_next_song()
                continue

            if not has_internal_cache_space():
                self.status("Not enough storage to continue.\nInsert an SD card or free ~2 MiB.")
                return

            song_total = est_song_total_seconds(t)

            # Current fragment
            cur_fn = frags[self.state.fragment]
            cur_url = BASE_URL + cur_fn
            cur_path = self._cache_path(self.state.track, self.state.fragment)

            # Ensure current exists
            if not exists(cur_path):
                self.buffering(True)
                self.status("Buffering...\n{}\n{}\n{} / {}".format(
                    t.get("album", ""), t.get("title", ""),
                    fmt_mmss(self.state.fragment * FRAGMENT_SECONDS), fmt_mmss(song_total)
                ))
                tmp = cur_path + ".part"
                rm(tmp)
                download_streaming(cur_url, tmp)
                rm(cur_path)
                try:
                    os.rename(tmp, cur_path)
                except Exception:
                    # fall back to direct download
                    download_streaming(cur_url, cur_path)
                    rm(tmp)
                self.buffering(False)

            # Prefetch next fragment (same song)
            next_frag = self.state.fragment + 1
            if next_frag < len(frags):
                n_fn = frags[next_frag]
                n_url = BASE_URL + n_fn
                n_path = self._cache_path(self.state.track, next_frag)
                if not exists(n_path):
                    self.pref.request(n_url, n_path)

            # Play current fragment
            frag_start_ms = time.ticks_ms()
            last_ui_ms = frag_start_ms

            self.status("Now playing:\n{}\n{}\n{} / {}".format(
                t.get("album", ""), t.get("title", ""),
                fmt_mmss(self.state.fragment * FRAGMENT_SECONDS), fmt_mmss(song_total)
            ))

            done = {"x": False}
            def finished(_res=None):
                done["x"] = True

            try:
                AudioManager.stop()
            except Exception:
                pass
            try:
                AudioManager.set_volume(int(self.volume_getter()))
            except Exception:
                pass

            ok = False
            try:
                player = AudioManager.player(file_path=cur_path, stream_type=AudioManager.STREAM_MUSIC, on_complete=finished)
                player.start()
                ok = True
            except Exception as ex:
                print("TFLPlayer: player.start() raised:", ex, "path:", cur_path)
                self._audio_error(str(ex))

            if not ok:
                # wait a bit so user can read the error message
                for _ in range(15):
                    if self.stop_flag():
                        break
                    time.sleep_ms(100)
                # jump to next song
                self.state.fragment = len(frags)
                self.state.maybe_save()

                # Maintenance during playback (not at boundaries)
                self._maybe_cleanup_old_fragments(self.state.track, self.state.fragment, keep_last=3)
                self._maybe_gc()
                continue

            # Wait while playing
            while (not done["x"]) and (not self.stop_flag()):
                self.state.maybe_save()

                cmd = self.command_getter()
                if cmd in ("next", "prev"):
                    try:
                        AudioManager.stop()
                    except Exception:
                        pass
                    done["x"] = True

                err = self.pref.get_err()
                if err:
                    # D-06: keep raw exception text out of the UI; it is transient (auto-retrying).
                    print("TFLPlayer prefetch error (retrying):", err)
                    self.pref.clear_err()

                now = time.ticks_ms()
                if time.ticks_diff(now, last_ui_ms) >= 1000:
                    last_ui_ms = now
                    frag_elapsed = time.ticks_diff(now, frag_start_ms) // 1000
                    song_elapsed = (self.state.fragment * FRAGMENT_SECONDS) + int(frag_elapsed)
                    if song_elapsed > song_total:
                        song_elapsed = song_total
                    self.status("Now playing:\n{}\n{}\n{} / {}".format(
                        t.get("album", ""), t.get("title", ""),
                        fmt_mmss(song_elapsed), fmt_mmss(song_total)
                    ))

                time.sleep_ms(100)

            if self.stop_flag():
                break

            cmd = self.command_getter(clear=True)
            if cmd == "next":
                # Don't delete at fragment boundaries; cleanup happens during playback.
                self._apply_next_song()
                continue
            if cmd == "prev":
                # Don't delete at fragment boundaries; cleanup happens during playback.
                self._apply_prev_song()
                continue

            # Normal completion
            self.state.fragment += 1
            try:
                self.state.save()
            except Exception:
                pass

            # Start next fragment immediately if it's already ready.
            if self.state.fragment < len(frags):
                need_path = self._cache_path(self.state.track, self.state.fragment)
                if exists(need_path):
                    # Next fragment ready: loop around and play it right away.
                    continue

            # Buffering banner if next fragment isn't ready yet
            if self.state.fragment < len(frags):
                # need_path already computed above
                if not exists(need_path):
                    self.buffering(True)
                    buf_start = time.ticks_ms()
                    while (not self.stop_flag()) and (not exists(need_path)):
                        waited = time.ticks_diff(time.ticks_ms(), buf_start) // 1000
                        self.status("Buffering...\n{}\n{}\n(waited {}s)".format(
                            t.get("album", ""), t.get("title", ""), waited
                        ))
                        time.sleep_ms(250)
                    self.buffering(False)

            # Opportunistic maintenance while playing; avoid doing it at boundaries.
            # (GC/cleanup runs from the playback loop.)

        self.shutdown()

# -------------------------
# SD player
# -------------------------
class SDPlayer:
    def __init__(self, index, state, status_cb, stop_flag, command_getter, volume_getter):
        self.index = index
        self.state = state
        self.status = status_cb
        self.stop_flag = stop_flag
        self.command_getter = command_getter
        self.volume_getter = volume_getter
        self.sdman = SDAlbumManager()

    def _wrap_track(self):
        n = len(self.index.tracks)
        if n <= 0:
            self.state.track = 0
            return
        if self.state.track >= n:
            self.state.track = 0
        if self.state.track < 0:
            self.state.track = n - 1

    def _apply_next_song(self):
        self.state.track += 1
        self._wrap_track()
        self.state.fragment = 0
        try:
            self.state.save()
        except Exception:
            pass

    def _apply_prev_song(self):
        self.state.track -= 1
        self._wrap_track()
        self.state.fragment = 0
        try:
            self.state.save()
        except Exception:
            pass

    def play_forever(self):
        if not self.index.tracks:
            self.status("No tracks in index.")
            return

        self._wrap_track()

        while not self.stop_flag():
            self._wrap_track()
            t = self.index.tracks[self.state.track]
            frags = t.get("fragments", [])
            if not frags:
                self._apply_next_song()
                continue

            if self.state.fragment < 0:
                self.state.fragment = 0
            if self.state.fragment >= len(frags):
                self._apply_next_song()
                continue

            song_total = est_song_total_seconds(t)

            fn = frags[self.state.fragment]
            p = self.sdman.sd_path_for_fragment(t.get("album", ""), t.get("trackno", ""), t.get("title", ""), fn)

            if not exists(p):
                self.status("Missing on SD:\n{}\n{}\nSkipping fragment.".format(t.get("album",""), t.get("title","")))
                self.state.fragment += 1
                self.state.maybe_save()
                continue

            frag_start_ms = time.ticks_ms()
            last_ui_ms = frag_start_ms

            self.status("Now playing from SD:\n{}\n{}\n{} / {}".format(
                t.get("album",""), t.get("title",""),
                fmt_mmss(self.state.fragment * FRAGMENT_SECONDS), fmt_mmss(song_total)
            ))

            done = {"x": False}
            def finished(_res=None):
                done["x"] = True

            try:
                AudioManager.stop()
            except Exception:
                pass
            try:
                AudioManager.set_volume(int(self.volume_getter()))
            except Exception:
                pass

            ok = False
            try:
                player = AudioManager.player(file_path=p, stream_type=AudioManager.STREAM_MUSIC, on_complete=finished)
                player.start()
                ok = True
            except Exception as ex:
                print("TFLPlayer: player.start() raised:", ex, "path:", p)
                ok = False

            if not ok:
                self.status("Audio error.\nSkipping to next song.")
                for _ in range(15):
                    if self.stop_flag():
                        break
                    time.sleep_ms(100)
                self._apply_next_song()
                continue

            while (not done["x"]) and (not self.stop_flag()):
                self.state.maybe_save()

                cmd = self.command_getter()
                if cmd in ("next", "prev"):
                    try:
                        AudioManager.stop()
                    except Exception:
                        pass
                    done["x"] = True

                now = time.ticks_ms()
                if time.ticks_diff(now, last_ui_ms) >= 1000:
                    last_ui_ms = now
                    frag_elapsed = time.ticks_diff(now, frag_start_ms) // 1000
                    song_elapsed = (self.state.fragment * FRAGMENT_SECONDS) + int(frag_elapsed)
                    if song_elapsed > song_total:
                        song_elapsed = song_total
                    self.status("Now playing from SD:\n{}\n{}\n{} / {}".format(
                        t.get("album",""), t.get("title",""),
                        fmt_mmss(song_elapsed), fmt_mmss(song_total)
                    ))

                time.sleep_ms(100)

            if self.stop_flag():
                break

            cmd = self.command_getter(clear=True)
            if cmd == "next":
                self._apply_next_song()
                gc.collect()
                continue
            if cmd == "prev":
                self._apply_prev_song()
                gc.collect()
                continue

            self.state.fragment += 1
            self.state.maybe_save()
            gc.collect()

# -------------------------
# Main Activity
# -------------------------
class AlbumPlayer(Activity):
    def __init__(self):
        super().__init__()
        self._volume = 80
        self.vol_label = None
        self._stop = False
        self._playing = False

        self._cmd_lock = _thread.allocate_lock()
        self._command = None  # "next" | "prev" | None

        self._worker_running = False
        self._worker_lock = _thread.allocate_lock()  # guards check-and-set of _worker_running
        self._choice_lock = _thread.allocate_lock()
        self._user_choice = None  # "sd" | "stream" | None

        # Index/state references kept so next/prev can preview tracks while paused.
        self._index = None
        self._state = None

        # Skin widget refs (set in onCreate, nulled in onDestroy)
        self._skin_bg = None
        self._crop_imgs = {}   # name -> lv.image
        self._hotspot_btns = {}  # name -> lv.button
        self.song_label = None
        self.album_label = None
        self.time_label = None
        self.pbar = None
        self.buffer_banner = None
        self._vol_box = None
        self._about_modal = None  # guard single instance; deleted on close

    # ----- display scale helpers -----
    def _sx(self, px):
        return DisplayMetrics.pct_of_width(px * 100.0 / 320.0)

    def _sy(self, px):
        return DisplayMetrics.pct_of_height(px * 100.0 / 240.0)

    # ----- command helpers -----
    def _stop_flag(self):
        return self._stop

    def _set_command(self, cmd):
        with self._cmd_lock:
            self._command = cmd

    def _get_command(self, clear=False):
        with self._cmd_lock:
            c = self._command
            if clear:
                self._command = None
            return c

    # ----- UI helpers -----
    def ui_set_status(self, txt):
        # Route all status/error/transient messages to song_label.
        # Clear album_label and time_label so stale data does not linger
        # behind error/wifi/loading messages.
        if not self.song_label:
            return
        def _do():
            try:
                self.song_label.set_text(txt)
            except Exception:
                pass
            try:
                if self.album_label:
                    self.album_label.set_text("")
            except Exception:
                pass
            try:
                if self.time_label:
                    self.time_label.set_text("")
            except Exception:
                pass
        self.update_ui_threadsafe_if_foreground(_do)

    def ui_set_progress(self, pct):
        if pct < 0:
            pct = 0
        if pct > 100:
            pct = 100
        if not self.pbar:
            return
        try:
            self.update_ui_threadsafe_if_foreground(self.pbar.set_value, int(pct), ANIM_OFF)
        except Exception:
            # Fallback for lv.slider builds that only accept one arg
            try:
                self.update_ui_threadsafe_if_foreground(self.pbar.set_value, int(pct))
            except Exception:
                pass

    def ui_set_time(self, timeval):
        """Update time_label threadsafely (called from worker thread with cur/total string)."""
        if not self.time_label:
            return
        self.update_ui_threadsafe_if_foreground(self.time_label.set_text, timeval)

    def ui_buffering_banner(self, show):
        def _do():
            try:
                if show:
                    self.buffer_banner.remove_flag(FLAG_HIDDEN)
                    WidgetAnimator.show_widget(self.buffer_banner, anim_type="fade", duration=200)
                else:
                    WidgetAnimator.hide_widget(self.buffer_banner, anim_type="fade", duration=200, hide=True)
            except Exception:
                pass
        self.update_ui_threadsafe_if_foreground(_do)

    def set_song_album(self, song, album):
        """Update song and album labels threadsafely (called from worker thread).
        song = title only (no time appended); album = album name.
        """
        def _do():
            try:
                if self.song_label:
                    self.song_label.set_text(song)
                if self.album_label:
                    self.album_label.set_text(album)
            except Exception:
                pass
        self.update_ui_threadsafe_if_foreground(_do)

    @staticmethod
    def _secs(mmss):
        """Parse 'mm:ss' string into total seconds. Returns None on failure."""
        try:
            parts = mmss.strip().split(":")
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
        except Exception:
            pass
        return None

    def _worker_status_cb(self, txt):
        """Status callback for workers: parse 'Now playing:' lines into set_song_album,
        route everything else to ui_set_status so error/wifi/audio messages still appear
        in the gray panel.
        """
        if txt.startswith("Now playing:\n") or txt.startswith("Now playing from SD:\n"):
            # Format: "Now playing:\n{album}\n{title}\n{cur} / {total}"
            # lines[0] = "Now playing:" or "Now playing from SD:"
            # lines[1] = album
            # lines[2] = title (song title ONLY -- do not append time here)
            # lines[3] = time string "cur / total"
            lines = txt.split("\n", 3)
            album = lines[1] if len(lines) > 1 else ""
            title = lines[2] if len(lines) > 2 else ""
            timeval = lines[3] if len(lines) > 3 else ""
            self.set_song_album(title, album)
            self.ui_set_time(timeval)
            # Derive playback percentage from time string and drive the progress slider
            if timeval and "/" in timeval:
                cur_s, tot_s = timeval.split("/", 1)
                c = self._secs(cur_s)
                t = self._secs(tot_s)
                if c is not None and t and t > 0:
                    self.ui_set_progress(c * 100.0 / t)
            # _playing and _show_play_crop are already set by toggle_play_pause
            # (main thread); do not write _playing from worker thread.
            self._show_play_crop(True)
        elif txt.startswith("Buffering...\n"):
            # Show abbreviated buffering in song_label, keep album in album_label
            self.ui_set_status("Buffering...")
        else:
            self.ui_set_status(txt)

    def _show_play_crop(self, playing):
        """Show or hide the play/pause crop image threadsafely."""
        def _do():
            try:
                img = self._crop_imgs.get("play")
                if not img:
                    return
                if playing:
                    img.remove_flag(FLAG_HIDDEN)
                else:
                    img.add_flag(FLAG_HIDDEN)
            except Exception:
                pass
        self.update_ui_threadsafe_if_foreground(_do)

    def change_volume(self, delta):
        v = self._volume + int(delta)
        if v < 0:
            v = 0
        if v > 100:
            v = 100
        self._volume = v
        try:
            AudioManager.set_volume(self._volume)
        except Exception:
            pass
        if self.vol_label:
            self.update_ui_threadsafe_if_foreground(self.vol_label.set_text, "{}%".format(self._volume))

    # ----- About dialog -----
    def show_about(self):
        # Delete any previous About modal so stale hidden objects do not accumulate
        # and cannot intercept input or corrupt z-order on repeated opens.
        if self._about_modal is not None:
            try:
                self._about_modal.delete()
            except Exception:
                pass
            self._about_modal = None

        # Themed modal matching the player skin: dark panel, amber border, vertical stack.
        m = lv.obj(self.screen)
        self._about_modal = m
        m.set_size(lv.pct(84), lv.pct(90))
        m.align(lv.ALIGN.CENTER, 0, 0)
        m.set_style_bg_color(lv.color_hex(0x1A1510), lv.PART.MAIN)
        m.set_style_bg_opa(255, lv.PART.MAIN)
        m.set_style_border_color(lv.color_hex(0xD0A020), lv.PART.MAIN)
        m.set_style_border_width(2, lv.PART.MAIN)
        m.set_style_radius(10, lv.PART.MAIN)
        m.set_style_pad_all(6, lv.PART.MAIN)
        m.set_style_pad_row(2, lv.PART.MAIN)
        # Vertical stack centered horizontally -- avoids unreliable lv.pct() align offsets.
        try:
            m.set_flex_flow(lv.FLEX_FLOW.COLUMN)
            m.set_flex_align(lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER, lv.FLEX_ALIGN.CENTER)
        except Exception:
            pass
        # Guarantee the modal is above all skin children (background + hotspot buttons).
        try:
            m.move_foreground()
        except Exception:
            pass

        def _color(w, hexv):
            try:
                w.set_style_text_color(lv.color_hex(hexv), lv.PART.MAIN)
            except Exception:
                pass

        def _setfont(w, fontname):
            try:
                w.set_style_text_font(getattr(lv, fontname), lv.PART.MAIN)
            except Exception:
                pass

        # Logo (transparent PNG over the dark panel)
        try:
            logo = lv.image(m)
            logo.set_src(_ICON_PATH)
        except Exception as ex:
            print("Logo load failed:", ex)

        title = lv.label(m)
        title.set_text("The Free Lantern Player")
        _color(title, 0xF0C040)
        _setfont(title, "font_montserrat_16")

        by = lv.label(m)
        by.set_text("By The Free Lantern")
        _color(by, 0xFFFFFF)

        url = lv.label(m)
        url.set_text("www.thefreelantern.com")
        _color(url, 0xBBBBBB)
        _setfont(url, "font_montserrat_12")

        ver = lv.label(m)
        ver.set_text("Version: {}".format(APP_VERSION))
        _color(ver, 0xBBBBBB)
        _setfont(ver, "font_montserrat_12")

        close = lv.button(m)
        close.set_size(lv.pct(52), lv.pct(18))
        try:
            close.set_style_bg_color(lv.color_hex(0xF0A010), lv.PART.MAIN)
            close.set_style_bg_opa(255, lv.PART.MAIN)
            close.set_style_radius(6, lv.PART.MAIN)
        except Exception:
            pass
        close_lbl = lv.label(close)
        close_lbl.set_text("Close")
        close_lbl.center()
        _color(close_lbl, 0x201500)
        add_focus_border(close)
        # Add Close to the default focus group so badge keypad users can reach it.
        try:
            fg = lv.group_get_default()
            if fg:
                fg.add_obj(close)
        except Exception:
            pass

        def _close_about(e):
            # Delete the modal entirely so no stale hidden object remains.
            try:
                m.delete()
            except Exception:
                pass
            self._about_modal = None

        close.add_event_cb(_close_about, lv.EVENT.CLICKED, None)

    # ----- hotspot builder -----
    def _make_hotspot(self, name, x, y, w, h, crop_file, action):
        """Create a transparent focusable button hotspot with a pressed-glow crop image.

        Z-order: crop image first (underneath), then transparent button (on top for input).
        The button registers PRESSED/FOCUSED to show the crop and RELEASED/DEFOCUSED to hide it.
        CLICKED runs the action.
        """
        sx, sy = self._sx, self._sy

        # 1. Crop image (underneath; hidden by default)
        crop = lv.image(self.screen)
        try:
            crop.set_src(_ASSET_BASE + crop_file)
        except Exception as ex:
            print("TFLPlayer skin: crop load failed {}: {}".format(crop_file, ex))
        crop.set_size(sx(w), sy(h))
        crop.align(lv.ALIGN.TOP_LEFT, sx(x), sy(y))
        crop.add_flag(FLAG_HIDDEN)
        self._crop_imgs[name] = crop

        # 2. Transparent button (on top)
        btn = lv.button(self.screen)
        btn.set_size(sx(w), sy(h))
        btn.align(lv.ALIGN.TOP_LEFT, sx(x), sy(y))
        btn.set_style_bg_opa(0, lv.PART.MAIN)
        btn.set_style_border_width(0, lv.PART.MAIN)
        try:
            btn.set_style_shadow_width(0, lv.PART.MAIN)
        except Exception:
            pass
        self._hotspot_btns[name] = btn

        # Add to default focus group (without add_focus_border -- crop IS the focus indicator)
        try:
            fg = lv.group_get_default()
            if fg:
                fg.add_obj(btn)
        except Exception:
            pass

        # Event callbacks: show crop on press/focus, hide on release/defocus
        _name = name  # capture for closures

        def _on_pressed(e, n=_name):
            try:
                self._crop_imgs[n].remove_flag(FLAG_HIDDEN)
            except Exception:
                pass

        def _on_released(e, n=_name):
            # Keep play crop visible while playing
            if n == "play" and self._playing:
                return
            try:
                self._crop_imgs[n].add_flag(FLAG_HIDDEN)
            except Exception:
                pass

        btn.add_event_cb(_on_pressed, lv.EVENT.PRESSED, None)
        btn.add_event_cb(_on_pressed, lv.EVENT.FOCUSED, None)
        btn.add_event_cb(_on_released, lv.EVENT.RELEASED, None)
        btn.add_event_cb(_on_released, lv.EVENT.DEFOCUSED, None)
        btn.add_event_cb(lambda e, a=action: a(), lv.EVENT.CLICKED, None)

    # ----- play/pause / stop -----
    def toggle_play_pause(self):
        if self._playing:
            # Pause = stop audio but stay in app
            self._request_stop()
            self._playing = False
            self._show_play_crop(False)
        else:
            # Play: reset stop flag, clear any stale command, (re)launch worker.
            # The worker reloads PlaybackState from file, so a track previewed
            # while paused (next/prev) resumes correctly.
            self._stop = False
            self._set_command(None)
            with self._worker_lock:
                if not self._worker_running:
                    self._worker_running = True
                    _thread.start_new_thread(self._worker_main, ())
            self._playing = True
            self._show_play_crop(True)

    def stop_playback(self):
        """Stop audio and stay in the app. Shows play arrow (hides pause glyph)."""
        self._request_stop()
        self._playing = False
        self._show_play_crop(False)

    # ----- lifecycle -----
    def onCreate(self):
        self.screen = lv.obj()
        # Black background so any non-320 margin is black
        self.screen.set_style_bg_color(lv.color_hex(0x000000), lv.PART.MAIN)
        try:
            self.screen.set_style_bg_opa(255, lv.PART.MAIN)
        except Exception:
            pass

        sx, sy = self._sx, self._sy

        # --- Background skin image ---
        self._skin_bg = lv.image(self.screen)
        try:
            self._skin_bg.set_src(_ASSET_BASE + "skin_bg.png")
        except Exception as ex:
            print("TFLPlayer skin: skin_bg load failed:", ex)
        self._skin_bg.align(lv.ALIGN.TOP_LEFT, 0, 0)

        # --- Gray panel: two single-line rows (design box x16 y140 w288 h46) ---
        # Row 1: song title (montserrat_14, SCROLL_CIRCULAR marquee, white)
        self.song_label = lv.label(self.screen)
        self.song_label.set_width(sx(272))
        self.song_label.align(lv.ALIGN.TOP_LEFT, sx(26), sy(144))
        try:
            self.song_label.set_long_mode(lv.label.LONG_MODE.SCROLL_CIRCULAR)
        except Exception:
            try:
                self.song_label.set_long_mode(lv.label.LONG_MODE.CIRCULAR)
            except Exception:
                self.song_label.set_long_mode(lv.label.LONG_MODE.CLIP)
        self.song_label.set_style_text_color(lv.color_white(), lv.PART.MAIN)
        try:
            self.song_label.set_style_text_font(lv.font_montserrat_14, lv.PART.MAIN)
        except Exception:
            pass
        self.song_label.set_text("Loading...")

        # Keep self.label as alias so ui_set_status callers are satisfied
        self.label = self.song_label

        # Row 2 left: album name (montserrat_12, DOT ellipsis, gray) -- lifted to y165 to avoid clipping
        self.album_label = lv.label(self.screen)
        self.album_label.set_width(sx(150))
        self.album_label.align(lv.ALIGN.TOP_LEFT, sx(26), sy(163))
        try:
            self.album_label.set_long_mode(lv.label.LONG_MODE.DOT)
        except Exception:
            try:
                self.album_label.set_long_mode(lv.label.LONG_MODE.DOTS)
            except Exception:
                self.album_label.set_long_mode(lv.label.LONG_MODE.CLIP)
        self.album_label.set_style_text_color(lv.color_hex(0xBBBBBB), lv.PART.MAIN)
        try:
            self.album_label.set_style_text_font(lv.font_montserrat_12, lv.PART.MAIN)
        except Exception:
            try:
                self.album_label.set_style_text_font(lv.font_montserrat_14, lv.PART.MAIN)
            except Exception:
                pass
        self.album_label.set_text("")

        # Row 2 right: time "cur / total" (montserrat_12, CLIP, light gray) -- lifted to y165
        self.time_label = lv.label(self.screen)
        self.time_label.set_width(sx(94))
        self.time_label.align(lv.ALIGN.TOP_LEFT, sx(206), sy(163))
        try:
            self.time_label.set_long_mode(lv.label.LONG_MODE.CLIP)
        except Exception:
            pass
        self.time_label.set_style_text_color(lv.color_hex(0xDDDDDD), lv.PART.MAIN)
        try:
            self.time_label.set_style_text_font(lv.font_montserrat_12, lv.PART.MAIN)
        except Exception:
            try:
                self.time_label.set_style_text_font(lv.font_montserrat_14, lv.PART.MAIN)
            except Exception:
                pass
        self.time_label.set_text("")

        # --- Progress slider (covers baked groove/knob; display-only, not clickable) ---
        # Baked skin: dark groove x~15-303, vertical center y~188; gold knob far-left.
        self.pbar = lv.slider(self.screen)
        self.pbar.set_size(sx(288), sy(11))
        self.pbar.align(lv.ALIGN.TOP_LEFT, sx(15), sy(183))
        self.pbar.set_range(0, 100)
        try:
            self.pbar.set_value(0, ANIM_OFF)
        except Exception:
            try:
                self.pbar.set_value(0)
            except Exception:
                pass
        # MAIN (track): dark groove covers baked art
        try:
            self.pbar.set_style_bg_color(lv.color_hex(0x302F2D), lv.PART.MAIN)
            self.pbar.set_style_bg_opa(255, lv.PART.MAIN)
        except Exception:
            pass
        try:
            self.pbar.set_style_radius(100, lv.PART.MAIN)
        except Exception:
            pass
        # INDICATOR: amber fill
        try:
            self.pbar.set_style_bg_color(lv.color_hex(0xF0A010), lv.PART.INDICATOR)
            self.pbar.set_style_bg_opa(255, lv.PART.INDICATOR)
        except Exception:
            pass
        try:
            self.pbar.set_style_radius(100, lv.PART.INDICATOR)
        except Exception:
            pass
        # KNOB: gold round dot
        try:
            self.pbar.set_style_bg_color(lv.color_hex(0xD7A82C), lv.PART.KNOB)
            self.pbar.set_style_bg_opa(255, lv.PART.KNOB)
        except Exception:
            pass
        try:
            self.pbar.set_style_radius(100, lv.PART.KNOB)
        except Exception:
            pass
        try:
            self.pbar.set_style_pad_all(2, lv.PART.KNOB)
        except Exception:
            pass
        # Display-only: remove clickable flag so touch/keypad cannot drag-seek
        try:
            self.pbar.remove_flag(lv.obj.FLAG.CLICKABLE)
        except Exception:
            try:
                self.pbar.clear_flag(lv.obj.FLAG.CLICKABLE)
            except Exception:
                pass

        # --- Volume % overlay (covers baked "80%"; themed to match skin) ---
        # Dark box with gold border and amber text, matching baked art at x~10 y~84
        self._vol_box = lv.obj(self.screen)
        self._vol_box.set_size(sx(38), sy(28))
        self._vol_box.align(lv.ALIGN.TOP_LEFT, sx(10), sy(84))
        self._vol_box.set_style_bg_color(lv.color_hex(0x2B2611), lv.PART.MAIN)
        try:
            self._vol_box.set_style_bg_opa(255, lv.PART.MAIN)
        except Exception:
            pass
        try:
            self._vol_box.set_style_border_color(lv.color_hex(0xD0A020), lv.PART.MAIN)
            self._vol_box.set_style_border_width(2, lv.PART.MAIN)
        except Exception:
            pass
        try:
            self._vol_box.set_style_radius(7, lv.PART.MAIN)
        except Exception:
            pass
        try:
            self._vol_box.set_style_pad_all(0, lv.PART.MAIN)
        except Exception:
            pass

        self.vol_label = lv.label(self._vol_box)
        self.vol_label.set_text("{}%".format(self._volume))
        self.vol_label.set_style_text_color(lv.color_hex(0xF0C040), lv.PART.MAIN)
        try:
            self.vol_label.set_style_text_font(lv.font_montserrat_14, lv.PART.MAIN)
        except Exception:
            pass
        self.vol_label.align(lv.ALIGN.CENTER, 0, 0)

        # --- Buffering banner (minimal; hidden initially) ---
        self.buffer_banner = lv.label(self.screen)
        self.buffer_banner.set_width(sx(288))
        self.buffer_banner.align(lv.ALIGN.TOP_LEFT, sx(16), sy(146))
        self.buffer_banner.set_long_mode(lv.label.LONG_MODE.WRAP)
        self.buffer_banner.set_style_text_color(lv.color_hex(0xFFCC00), lv.PART.MAIN)
        self.buffer_banner.set_text("Buffering...")
        self.buffer_banner.add_flag(FLAG_HIDDEN)

        # --- Interactive hotspots (design coords from spec table) ---
        # Focus order: help, vol+, vol-, prev, play, next, stop, close
        self._make_hotspot("help",     8,   16,  42, 36, "p_help.png",    self.show_about)
        self._make_hotspot("vol_plus", 6,   55,  44, 35, "p_volplus.png", lambda: self.change_volume(+10))
        self._make_hotspot("vol_minus",6,   106, 44, 34, "p_volminus.png",lambda: self.change_volume(-10))
        self._make_hotspot("prev",     14,  199, 72, 32, "p_prev.png",    self.prev_clicked)
        self._make_hotspot("play",     88,  199, 72, 32, "p_play.png",    self.toggle_play_pause)
        self._make_hotspot("next",     162, 199, 72, 32, "p_next.png",    self.next_clicked)
        self._make_hotspot("stop",     236, 199, 72, 32, "p_stop.png",    self.stop_playback)
        self._make_hotspot("close",    270, 16,  42, 36, "p_close.png",   self.finish)

        self.setContentView(self.screen)

    def onResume(self, screen):
        super().onResume(screen)
        self._stop = False
        try:
            AudioManager.set_volume(self._volume)
        except Exception:
            pass

        # best-effort SD mount
        try:
            sdcard.mount_with_optional_format("/sdcard")
        except Exception as ex:
            print("SD mount skipped:", ex)

        with self._worker_lock:
            if not self._worker_running:
                self._worker_running = True
                _thread.start_new_thread(self._worker_main, ())

    def onPause(self, screen):
        self._request_stop()
        super().onPause(screen)

    def onDestroy(self, screen):
        self._request_stop()
        super().onDestroy(screen)
        # C-heap-safe teardown: release decoded image buffers (set_src(None)) then gc.collect().
        # Do NOT call screen.delete() -- the framework calls screen.clean() after onDestroy.
        try:
            if self._skin_bg:
                self._skin_bg.set_src(None)
        except Exception:
            pass
        for img in self._crop_imgs.values():
            try:
                img.set_src(None)
            except Exception:
                pass
        try:
            gc.collect()
        except Exception:
            pass
        # Null all widget refs
        self.screen = None
        self.song_label = None
        self.label = None
        self.album_label = None
        self.time_label = None
        self.pbar = None
        self.buffer_banner = None
        self.vol_label = None
        self._vol_box = None
        self._skin_bg = None
        self._crop_imgs = {}
        self._hotspot_btns = {}
        if hasattr(self, 'modal') and self.modal:
            self.modal = None
        self._about_modal = None

    # ----- buttons -----
    def next_clicked(self):
        if self._playing:
            self._set_command("next")
            try:
                AudioManager.stop()
            except Exception:
                pass
        else:
            # Paused: advance the track pointer and show the next song name now.
            self._preview_track(+1)

    def prev_clicked(self):
        if self._playing:
            self._set_command("prev")
            try:
                AudioManager.stop()
            except Exception:
                pass
        else:
            self._preview_track(-1)

    def _preview_track(self, delta):
        """While paused, move to the next/prev track and display its song/album
        immediately without starting playback. The pointer is persisted so the
        next Play resumes on the previewed track. Safe no-op before the index loads."""
        idx = self._index
        st = self._state
        if not idx or not st or not idx.tracks:
            return
        n = len(idx.tracks)
        st.track = (st.track + delta) % n
        st.fragment = 0
        try:
            st.save()
        except Exception:
            pass
        t = idx.tracks[st.track]
        self.set_song_album(t.get("title", ""), t.get("album", ""))
        # New song not played yet: reset progress + time display.
        self.ui_set_progress(0)
        if self.time_label:
            self.update_ui_threadsafe_if_foreground(self.time_label.set_text, "")

    def _request_stop(self):
        self._stop = True
        try:
            AudioManager.stop()
        except Exception:
            pass

    # ----- SD choice modal -----
    def _show_sd_choice_modal(self):
        self.modal = lv.obj(self.screen)
        self.modal.set_size(lv.pct(90), lv.pct(40))
        self.modal.align(lv.ALIGN.CENTER, 0, 0)

        lbl = lv.label(self.modal)
        lbl.set_width(lv.pct(95))
        lbl.align(lv.ALIGN.TOP_MID, 0, lv.pct(3))
        lbl.set_long_mode(lv.label.LONG_MODE.WRAP)
        lbl.set_text(
            "SD card detected with enough free space.\n"
            "Download album to SD and play locally?\n\n"
            "Yes = SD mode  No = Streaming"
        )

        btn_yes = lv.button(self.modal)
        btn_yes.align(lv.ALIGN.BOTTOM_LEFT, lv.pct(3), lv.pct(-3))
        lv.label(btn_yes).set_text("Yes (SD)")
        add_focus_border(btn_yes)

        btn_no = lv.button(self.modal)
        btn_no.align(lv.ALIGN.BOTTOM_RIGHT, lv.pct(-2), lv.pct(-3))
        lv.label(btn_no).set_text("No (Stream)")
        add_focus_border(btn_no)

        def choose_sd(_e):
            with self._choice_lock:
                self._user_choice = "sd"
            WidgetAnimator.smooth_hide(self.modal, hide=True, duration=200)

        def choose_stream(_e):
            with self._choice_lock:
                self._user_choice = "stream"
            WidgetAnimator.smooth_hide(self.modal, hide=True, duration=200)

        btn_yes.add_event_cb(choose_sd, lv.EVENT.CLICKED, None)
        btn_no.add_event_cb(choose_stream, lv.EVENT.CLICKED, None)

        # Add buttons to default focus group so keypad-only badge users can navigate.
        try:
            fg = lv.group_get_default()
            if fg:
                fg.add_obj(btn_yes)
                fg.add_obj(btn_no)
        except Exception:
            pass

        try:
            self.modal.add_flag(FLAG_HIDDEN)
        except Exception:
            pass
        WidgetAnimator.smooth_show(self.modal, duration=200)

    def _wait_for_choice(self, timeout_s=60):
        start = time.time()
        while not self._stop_flag():
            with self._choice_lock:
                c = self._user_choice
            if c in ("sd", "stream"):
                return c
            if time.time() - start > timeout_s:
                return "stream"
            time.sleep_ms(100)
        return None

    # ----- worker thread -----
    def _worker_main(self):
        # D-07/D-08: connectivity pre-check before any network call
        # NEVER use wait_until_online() -- it has a truthy bug (tests bound method, always True)
        try:
            cm = ConnectivityManager.get()
            if not cm.is_online():
                self.ui_set_status("No WiFi\n\nConnect to WiFi and reopen the app.")
                self._worker_running = False
                return
        except Exception as ex:
            print("TFLPlayer: ConnectivityManager check failed:", ex)
            # Proceed; AlbumIndex.load() will fail with a clear error if truly offline

        try:
            self.ui_set_status("Loading index...")
            try:
                idx = AlbumIndex().load()
            except Exception as ex:
                print("TFLPlayer: index load error:", ex)
                self.ui_set_status("Could not load track list.\n\nCheck your connection and try again.")
                return  # finally block sets _worker_running = False
            st = PlaybackState().load()
            # Expose to the activity so next/prev can preview tracks while paused.
            self._index = idx
            self._state = st

            sdman = SDAlbumManager(status_cb=self.ui_set_status, progress_cb=self.ui_set_progress)

            sd_present = sdman.sd_present()
            cache_ok = has_internal_cache_space()

            if (not sd_present) and (not cache_ok):
                self.ui_set_progress(0)
                self.ui_set_status(
                    "No SD card and not enough internal storage.\n"
                    "Insert an SD card (>=70 MiB free) or free ~2 MiB."
                )
                self._request_stop()
                return

            # choose mode
            choice = "stream"
            if sdman.sd_ready():
                self.update_ui_threadsafe_if_foreground(self._show_sd_choice_modal)
                c = self._wait_for_choice(timeout_s=60)
                if c:
                    choice = c

            if self._stop_flag():
                return

            if choice == "sd":
                st.mode = "sd"
                st.maybe_save()

                self.ui_set_progress(0)
                self.ui_set_status("Preparing SD...")

                # If timestamp missing but inprogress exists: resume
                if (not exists(SD_TIMESTAMP_FILE)) and exists(SD_INPROGRESS_FILE):
                    sdman.handle_incomplete_previous_download()
                    ok = sdman.download_all_missing_or_changed(idx, force_redownload_changed=False, stop_flag=self._stop_flag)
                    if not ok or self._stop_flag():
                        return
                else:
                    if exists(SD_TIMESTAMP_FILE) and sdman.should_verify_online():
                        ok = sdman.verify_online_and_update_if_needed(idx, stop_flag=self._stop_flag)
                        if not ok or self._stop_flag():
                            return
                    else:
                        ok = sdman.download_all_missing_or_changed(idx, force_redownload_changed=False, stop_flag=self._stop_flag)
                        if not ok or self._stop_flag():
                            return

                self.ui_set_status("Playing from SD...")
                p = SDPlayer(idx, st, self._worker_status_cb, self._stop_flag, self._get_command, lambda: self._volume)
                p.play_forever()
                return

            # streaming mode
            if not cache_ok:
                self.ui_set_status(
                    "Not enough internal storage for streaming.\n"
                    "Insert an SD card or free ~2 MiB."
                )
                self._request_stop()
                return

            st.mode = "stream"
            st.maybe_save()

            self.ui_set_status("Streaming playback...")
            sp = StreamPlayer(
                idx, st,
                status_cb=self._worker_status_cb,
                buffering_cb=self.ui_buffering_banner,
                stop_flag=self._stop_flag,
                command_getter=self._get_command,
                volume_getter=lambda: self._volume
            )
            sp.play_forever()

        except Exception as ex:
            print("TFLPlayer: worker fatal error:", ex)
            self.ui_set_status("Something went wrong.\nReopen the app to try again.")

        finally:
            self._playing = False
            self._show_play_crop(False)
            self._worker_running = False
            try:
                AudioManager.stop()
            except Exception:
                pass
            gc.collect()
