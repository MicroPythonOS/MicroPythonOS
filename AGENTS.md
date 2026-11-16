# AGENTS.md

Guidance for AI assistants working in this repo. Keep it short.

## Project & build

MicroPythonOS: GUI + OS for microcontrollers. Source: `internal_filesystem/` (1:1 filesystem). C modules: `c_mpos/`. Built on `lvgl_micropython/` (LVGL + MicroPython).

**Desktop builds run MicroPython, NOT CPython.** `sys.implementation.name == 'micropython'`. Stdlib is minimal — no `uuid`, no `machine.unique_id()`.

- Build: `./scripts/build_mpos.sh <target>` (mutates tracked files — those edits persist).
- Prefer Makefile targets: `make build-mpos-unix`, `make lint`, `make lint-fix`, `make tests`, `make help`.
- `mpy-cross`: `./lvgl_micropython/lib/micropython/mpy-cross/build/mpy-cross`. Needs `-march=x64` for native/viper on desktop.
- Unix/macOS: `build_mpos.sh` creates symlinks in `lvgl_micropython/ext_mod/` for `c_mpos` and `secp256k1-embedded-ecdh`.

### lvgl_micropython submodule branching

To keep it easy to manage/sync with upsteam lvgl_micropython, we keep the changes in either:

- **Patch files** (`.patch` applied by `build_mpos.sh`): commit directly on `integration`. No topic branch needed — the patch file is the topic.
- **Direct edits**: must go on a `topic/<name>` branch, then merge into `integration`. Branch naming: `topic/<kebab-case>` (e.g. `topic/wifi-country-japan`).

## Testing

**Run:** `./scripts/test_runner.py tests/<test_file> tests/<other_test_file> [--ondevice] [--port <port>] [--reset]` 
**All tests:** `make tests` (20–35 min). CI runs them on push. **Syntax:** `make syntax-tests`  
**CPython controller tests:** `python3 tests/cpython_mpos_controller.py`, `python3 tests/cpython_kill_orphaned.py`, `python3 tests/cpython_kill_orphaned_linux.py` (not run by test_runner.py).  
**Prefs wipe:** `test_runner.py` deletes `internal_filesystem/prefs/` (all app settings) in the checkout it runs from (`_cleanup_config`). Run tests from a worktree if that checkout holds settings you need.  
**Details:** `tests/README.md`

**Options:**  
`--ondevice` — run on connected device (serial). `--no-install-test-apps` skips test-app install.  
`--port <port>` — serial port (overrides `MPOS_TEST_PORT` env).  
`--relayport <port>` — USB power relay port; with `--reset`, power-cycles device instead of `machine.reset()`.  
`--reset` — hard-reset device before each test.  
`--resume` — resume suite from first provided test file (alphabetical order).  
`--cpulimit <pct>` — throttle desktop MicroPython to simulate slow CI (requires `cpulimit` installed).  
`--logserial <file>` — log all serial traffic to file; watch with `tail -f`.  
`--coverage` — line coverage (desktop only, requires mpcov build). `--coverage-save`/`--coverage-load` for merged runs.  
`--usb-unbind` — cleanly unbind/rebind USB between resets to reduce xhci wedging.  
`--usb-reset-hub` — reset xhci host controller after relay power-on.  
`--usb-settle <s>` — USB settle time after unbind/bind (default: 5).  
`--no-usb-recovery` — disable automatic USB recovery on I/O error.  
`--timeout <s>` — per-test timeout. `--tests-dir <dir>` — add dir to `sys.path` for test helpers.

### First-use and render-time paths

- Test **cold caches**, not just warm ones. Clear the FontManager caches (`_composed_font_cache`, `_emoji_*`, `_imgfont_*`) and render emoji in a textarea placeholder, a keyboard field and a label. A warm-cache test never exercises the imgfont callback path.
- Never call `lv.snapshot_take*` (or anything that dispatches draws) from inside a draw callback: an imgfont/style callback runs while LVGL is drawing, and the snapshot waits for the draw that invoked it — the whole system hangs with no traceback. Defer it with `lv.async_call` (see `FontManager._defer_scale`).
- A hang is a bug. When an on-device test stops responding with no traceback, rerun with `--timeout`, capture the last serial output, and add a regression test instead of just retrying.
- Before releasing a FontManager/LVGL-drawing change, run `tests/test_graphical_emoji_font_while_drawing.py`, `tests/test_graphical_keyboard_emoji_font.py` and `tests/test_graphical_sorter_emoji_persistence.py` on at least one board.

### Deploying lib/ changes to device

Frozen modules in the firmware shadow filesystem `.py` files even though `sys.path = ['lib', '', '.frozen']`. To test a modified framework file at `internal_filesystem/lib/mpos/ui/*.py` on device:

- **`./scripts/install.sh`** — copies the entire `lib/` directory to device flash (`lib/mpos/` → `:/lib/mpos/`), overriding frozen modules. Slow but comprehensive; run once to populate the tree.
- **`python3 lvgl_micropython/lib/micropython/tools/mpremote/mpremote.py connect /dev/ttyACM0 cp internal_filesystem/<path> :<path>`** — copies a single file. Fast but only works after `install.sh` has already created the target directory structure on flash.

After deploying, relay-reset so the device boots with the new files (the module cache is cleared on reset).

**WARNING — flash shadows replace whole directories, not single files:** once `:/lib/mpos/` exists on flash, its modules come from flash ONLY. Deleting one flash file (e.g. after instrumenting it) does NOT fall back to frozen — you get `ImportError`. Never `fs rm` a shadow file; re-copy the original from `internal_filesystem/` instead. Also keep vintages consistent: mixing current-repo copies with an older install causes subtle crashes — if in doubt, re-run full `install.sh`.

**USB/IP + relay reset:** the `/dev/ttyACM0` node can appear before USB enumeration finishes; opening serial too early wedges the usbip session (URB `-104` unlinks, reads return nothing). `_relay_reset` settles 8s after first seeing the node. Manual recovery: relay-cycle, wait ≥20s, poke with raw pyserial `\r\n` until `>>>`.

### Code coverage (desktop only)

**Build with coverage:** `./scripts/build_mpos.sh unix coverage` or `make build-mpos-unix-coverage`  
Enables `sys.settrace` in the mpcov variant. Standard build overwritten — re-run `./scripts/build_mpos.sh unix` to restore.

**Run tests with coverage:**
```
python3 scripts/test_runner.py --coverage tests/test_a.py tests/test_b.py   # terminal report
python3 scripts/test_runner.py --coverage --coverage-save cov.json tests/test_*.py  # save JSON
python3 scripts/test_runner.py --coverage --coverage-load cov.json --coverage-save cov.json tests/test_extra.py  # merge
```

**Generate HTML report:** `python3 scripts/coverage_report.py cov.json -o coverage/index.html`  
Self-contained HTML — overview stats, per-file coverage %, expand inline source with line coloring (red=untested, green=tested, shade intensity by hit count).

**When running multiple tests for coverage:** prefer `test_runner.py` with multiple positional args (e.g. `tests/test_a.py tests/test_b.py`) over one-by-one invocations — the merged coverage report will aggregate all runs.

- Graphical tests (filename contains `graphical`): LVGL boot injected. Non-graphical: no boot, no LVGL init — import `lvgl` lazily.
- Test CWD = `internal_filesystem/`. `sys.path.insert(0, ".")` assumes that root.
- `--reset` (device only): hard-resets via `machine.reset()`, waits for `"Starting asyncio REPL..."` (NOT just `>>>`). Boot: 2–40s.
- USB/IP passthrough: close serial fd before reset; retry open up to 20× (3s apart).
- Serial (paste-mode) test runs strip the file's `if __name__ == "__main__": unittest.main()` block — in paste mode `__name__ == "__main__"`, so without stripping, `unittest.main()` AND the appended TextTestRunner would run the suite twice on already-mutated UI state. Desktop import-runner (`_build_import_runner_code`) is immune (`__name__` = module name), which is why such bugs only appear on device.
- Use helpers in `internal_filesystem/lib/mpos/ui/testing.py`. Follow `tests/README.md` for graphical tests.

**After any code change:** grep for tests importing changed modules, run them. Do NOT skip.  
**If you modify a test:** run it to verify.

**Capturing logger output in tests:** add custom handler to logger, access `record.message` in `emit()`. Restore handlers in `finally:`.  
**Test decorators:** `@unittest.skipIf` must be directly above the function — no module-level code between.

**Most common test segfault cause:** passing a non-LVGL Python object (mock, plain instance) as parent to any LVGL widget constructor. Mock the calling method instead, or use real `lv.obj()` (graphical test). Known live one: AppStore detail-navigation tests segfault ESP32 asynchronously right after `_launch_activity` returns (breadcrumbs: N3 present/N4 missing); quarantined via `_skip_detail_navigation_on_esp32` in `tests/test_graphical_appstore_focus.py`.

**Never cache `asyncio.get_event_loop()` in `setUp`.** The test runner may create a fresh event loop between `setUp` and the test method, making a cached reference stale. Get the loop fresh at call time — inside the test method or inside the task-capture callback:

```python
# WRONG — loop may be stale
def setUp(self):
    self._loop = asyncio.get_event_loop()

def _capture_task(coro):
    self._loop.run_until_complete(coro)  # boom

# RIGHT — fresh lookup
def _capture_task(coro):
    import asyncio as _asyncio
    _asyncio.get_event_loop().run_until_complete(coro)
```

**Task capture triggers cascading side effects.** When `TaskManager.create_task` is mocked to `run_until_complete` synchronously, any task that internally spawns more tasks also runs synchronously in the same call. E.g. mocking `_update_all_click` reaches `_run_update_all` → `refresh_list` → `download_app_index` → `create_apps_list` → `_stop_all_timers`. Every link in the chain needs a mock (`_raw_timer`, `refresh_list`, etc.) even if your test goal is narrow. The crash surfaces far from the mocked entry point — watch the stack trace for the full cascade.

**`asyncio.core` stores the event loop in module-level globals.** `_task_queue`, `_io_queue`, `cur_task`, and the `SingletonGenerator` (created once as a default-argument in `sleep_ms`) are all shared. `asyncio.new_event_loop()` replaces `_task_queue` and `_io_queue` globally — if called from a test setUp running inside the TaskManager's event loop (paste mode via aiorepl), the outer loop's orphaned queue is GC'd and its tasks become dangling pointers. `asyncio.run()` also shares these globals; when the inner `run_until_complete` sets `cur_task = None` on exit, the outer loop resumes with a stale task pointer → SIGSEGV. **For tests that need `asyncio.run()` inside a running event loop:** save/restore `cur_task` around the call. For tests that call `new_event_loop()`, restore all three globals after `unittest.main()`. See `_build_import_runner_code()` in `mpos_controller.py` for the standard monkeypatches applied to all tests.

## Lab tooling

Check here before writing a new measurement script; these exist and are maintained.

| Tool | What it does |
|------|--------------|
| `scripts/mpos_dac_acoustic.py` | Plays a tone sequence (or `--file <wav>`) through an i2s output and scores a recording from a host capture input. Also the way to prove the badge actually makes sound. Needs no cable: the tools default to a USB microphone and pick the channel count from the device, so the webcam mic records both the DAC speaker and the buzzer. |
| `scripts/mpos_buzzer_acoustic.py` | Records the PWM buzzer with a host mic and folds each peak to the expected harmonic, so low notes work despite the piezo resonance. |
| `scripts/mpos_screen_camera.py` | Aligns a webcam view to the device framebuffer (SIFT+RANSAC) and reports NCC, sharpness and per-icon-cell metrics. |
| `scripts/validate_ota_release.py` | The release gate: takes a badge already on the previous factory image, drives the OSUpdate notification/install UI over serial and checks the `ota_0 -> ota_1 -> ota_0` sequence, with webcam checkpoints. |
| `scripts/ota_validation_server.py` | Serves throwaway osupdate metadata so an older upgrade path can be re-validated. |
| `video_samples/tools/capture_measure.py` | Webcam recorder plus ruler-strip analyzer: `presented_fps` (pictures actually seen) separate from `clip_rate_fps` (how fast the clip timeline advanced). |
| `video_samples/tools/generate_assets.py` | Regenerates the clips, sidecars and the AVI/MOV/MKV muxes. |
| `video_samples/tools/probe_matrix.py` | On-device SD/display matrix; run it from a fresh boot. |
| `tests/cpython_*.py`, `tests/manual_test_*.py` | Host-side and manual entry points for the acoustic and camera tools. |

Hardware facts that cost time to rediscover:

- **On the lab rig the badge is attached to `zbox1`, a separate host, so the ALSA cards described here are `zbox1`'s** — run `arecord`/`amixer` there, not on the machine you are editing from. That rig also has the badge's headset jack wired into `zbox1`'s motherboard line input, so card 0 (`hw:0,0`) is a clean, full-scale copy of the DAC output — but that is one rig's cabling, not a property of the badge: if the lead is unplugged or moved, card 0 hears only room noise. Card 2 (`hw:2,0`) is the C925e webcam mic: it refuses mono (the tools ask for stereo automatically) and it hears the speaker and the buzzer across the desk. Card 3 (`hw:3,0`) is the Generalplus USB sound card whose microphone sits right next to the buzzer: at +25 dB with `Auto Gain Control` off it is ~28 dB stronger on the buzzer than card 2 (0.12 vs 0.005 RMS on a 1 kHz tone) and is the right device for anything about the buzzer, while card 0 hears only the DAC. Recording the wrong card makes healthy audio look silent, so prove which card hears the target with a loud tone before measuring. `amixer -c 3 contents` is where to check (and turn off) AGC before trusting a level.
- **The badge's sample clock and the capture card's clock differ by ~0.24 %**: the same 12 s file comes back slightly longer, which is inaudible but smears any long comparison (coherence collapses, STOI drifts). Put a noise burst at both ends of the test file, measure the spacing to get the ratio, and resample by it before scoring. The badge is the one playback device here that cannot be assumed to have the host's clock.
- **The piezo disc is a resonator at ~5 kHz, not a wideband speaker.** Measured on the fri3d 2026 with the sweep the quality tool plays: no measurable output below 2 kHz and ~50 dB more at 5 kHz, and coherence against the source of ~0.02 — almost everything audible is harmonic content generated by the clipping, not a linear copy. Energy in the "reproducible band" therefore rewards distortion (the old energy table ranked the worst tunings first); score intelligibility (STOI) and envelope tracking instead, and watch for the resonance saturating into a constant tone when the drive is raised.
- **`mpremote run` executes the file with `__name__ == "builtins"`**, so an `if __name__ == "__main__":` guard silently skips the whole file (no output, exit code 0). Device scripts must run unconditionally.
- **v4l2 timestamps are `CLOCK_MONOTONIC`, ALSA's are the wall clock.** A one-shot webcam+line-in capture therefore cannot be aligned: ffmpeg rebases each stream to zero (losing the difference), `-copyts` pushes the absolute values past what Matroska can hold, and the UVC stream arrives with seconds of buffered frames. Measuring an A/V offset needs one marker in both streams (clap board, or an LED driven from the beep event).
- **Screen checks with the C925e:** use `scripts/mpos_screen_camera.py` (`config`, `capture`, `measure`/`verify`), not raw ffmpeg stills. Auto exposure/high gain clips the white MicroPythonOS UI: `config --no-auto-exposure --exposure 100 --gain 0 --apply` gives a readable frame, and lowering the panel backlight (`mpos.ui.main_display.set_backlight(35)`, restore 100 afterwards) helps on white screens. The screen is only ~300x230 px in 1920x1080; SIFT still aligns it (86 matches/81 inliers measured on the Waveshare), but `cell_ncc_min` can fall below the default threshold from focus/resolution — inspect `compare.jpg`/`aligned.png` alongside the numbers. On the zbox1 rig `focus_absolute=40` was 4.5x sharper than the default `20` (Laplacian variance 229 vs 51 over the screen area). For the OTA gate a rig config with `min_inliers: 20`, `min_ncc_gray`/`min_ncc_gradient: 0.55`, `min_eff_px_per_screen_px: 0.70` and no `min_cell_ncc_min` passes: inliers ranged 21-56 per screen (text-only screens have the fewest features) and per-cell scores are meaningless on text at this resolution.
- The I2S DMA ring starts full of silence that plays out in real time, so the first write after opening only lands as the ring drains (~22 ms per KB). Wait `ibuf` before priming.
- Firmware `machine.I2S.write()` does not release the GIL, so an audio thread buys nothing; feed the sink from the same loop that presents frames.
- **Copying files to the badge's SD card over USB-CDC runs at about 2 KB/s** (`mpremote cp` is the fastest serial path; chunked base64 through the REPL is no better): 500 KB takes ~5 minutes, so do not move media that way. The card itself writes at ~345 KB/s, so the link is the limit.
- **To put megabytes on the card, pull them over WiFi instead.** Serve the directory on the host (`cd dir && python3 -m http.server 8765`) and fetch it on the device with a raw socket GET (~200 KB/s: a 2.6 MB clip in 12.5 s). `DownloadManager` needs the async stack and failed with `ENOENT` when called from the REPL; a plain `socket` + `GET ... HTTP/1.0` writing to `/sdcard/...` works. Mount the card first (`SDCardManager.mount()`), or the path does not resolve.

## Development rules

- **TDD:** write failing test → fix → test passes.
- **Lint:** every change must pass `make lint`. Ruff, double quotes.
- **Names:** use descriptive names, never bare numbers or opaque suffixes. When a framework forces a numeric variant (e.g. display drivers select `_<driver>_init_type<N>.py` through `init(type=N)`), export named constants from the package and use those at every call site (`init(st7789.PROFILE_LEGACY)`), keeping the numeric mapping in one documented place.
- **Comments/docstrings:** never add/remove/modify unless explicitly asked.
- **GitHub comments:** always very polite and gentle (issues, PRs, reviews).
- **CI strips `@micropython.native` / `@micropython.viper`**: the workflow comments those decorator lines out before running the suite, so a module must still work as ordinary Python. Pointer builtins (`ptr8`, `ptr16`) only exist inside a viper-compiled function and raise `NameError` there — probe viper once at import (see `adpcm_ima._viper_available`) and fall back to a plain-Python implementation. Reproduce locally with the same `sed` over `internal_filesystem` before pushing.
- **Batch edits:** constrain to exact patterns. Broad edits can silently delete unrelated code. If damage occurs, restore from git and re-apply a precise script.
- **Implement missing functionality** rather than working around it.
- **USB host:** DisplayLink display + HID support lives in `c_mpos/usb/` — read its `README.md` before touching USB, display, touch, or topmenu code; build with `./scripts/build_mpos.sh esp32s3 --usb`.
- **Observe before fixing, not after.** When a bug involves UI state or runtime data, use `mpos-controller` (`exec`, `get_widget_tree`, `eval`) to inspect the actual running system before coding a fix. Do NOT spend more than 2 rounds of static code analysis without validating assumptions against the live process.
- **If the hardware looks broken or misconfigured, stop and ask.** When a measurement or a fix points at a fault in the physical setup — a microphone that records nothing, a capture device that is silent or saturated, a board that does not enumerate, a sensor that returns constant or impossible values — say so and ask the user to fix it instead of building on it or working around it. A workaround built on a broken rig produces confident, wrong numbers, which is worse than no measurement. Continue past a suspected hardware fault only when the user explicitly overrides it, and say in the report that the override is what the result rests on.

### Debugging shared-object / identity bugs

The AppStore and AppManager share App objects by reference — `self.apps`, `_by_fullname`, and `_app_list` may all point to the same instance. Mutating any attribute on one path silently changes it everywhere. When tracing a bug where a value is "wrong" despite looking correct in isolation:

1. **Check object identity first:** `a is b` on the suspected candidates. Use `mpos-controller exec` to test.
2. **Mock objects hide identity bugs.** A test mock that creates a fresh object won't catch mutations propagated through shared references. Write at least one test that uses the real objects from the cache (`AppManager._by_fullname`) — not mock copies.
3. **Prefer filesystem reads over cache reads for installed state.** The cache can go stale or be corrupted by shared-object writes. For installed-app data (version, installed status), reading MANIFEST.JSON directly from `apps/` or `builtin/apps/` is more reliable than `_by_fullname`.
4. **Don't overwrite fields on shared objects.** If an App object lives in both the AppManager cache and the store list, use a separate attribute (e.g., `_remote_version`) for store-specific data instead of mutating shared fields like `version`.

### Logging

```python
import logging; logger = logging.getLogger(__name__)
if __debug__: logger.debug("fmt %s", var)  # eliminated by mpy-cross -O3
logger.warning("msg: %s", e)  # always include %s placeholder
```

- Prefer `%s` over f-strings. `mpy-cross -O3` strips `__debug__` blocks entirely (strings + bytecode).
- Trap: `logger.error("msg: ", e)` → `TypeError` (no `%s` in format string). Always: `"msg: %s"`.
- `f"{var:spec}"` → `"%spec"` format + var as positional arg. `f"{var=}"` → strip `=`. Compound `; print(...)` needs line-level matching.
- `__debug__` guard trap: `if __debug__: logger.debug("x=%s", x)` — `x` must be defined **before** this line. Assign first, log second.

### Process & temp files

- Desktop: `timeout -s 9 30 ./scripts/run_desktop.sh`
- Kill processes: `killall <name>` (not `pkill -f`).
- Temp files: `tmp/` in project root (not `/tmp`).
- MPOSController cleans up on exit. Manual `killall -9 lvgl_micropy_unix run_desktop.sh` only for SIGKILL orphans.
- Debug scripts: write to `tmp/`, run with `python3 tmp/script.py`.

## MPOS Controller (`scripts/mpos_controller.py`)

Drives MicroPythonOS from CPython. `backend='process'` (local PTY) or `backend='serial', port='/dev/ttyACM0'` (device).

**Must call `mpos.start()` then wait ~8s before any other method.**

Key methods: `exec()`, `eval()`, `startapp()`, `run_app_with_file()`, `run_test_file()`, `screenshot()`, `screenshot_image()`, `screenshot_pixels()`, `save_screenshot()`, `press(x,y)`, `press_key()`, `click_button()`, `find_widget()`, `press_widget()`, `wait_for_text()`, `expect_text()`, `get_visible_text()`, `get_widget_tree()`, `read_file()`, `write_file()`.

- `exec()`/`exec_multiline()` use paste mode — equivalent, multi-line safe. Timeout supported.
- `get_visible_text()`: `lv.screen_active()` only (NOT `lv.layer_top()` — misses popups/msgboxes).
- `get_widget_tree()`: includes `layer_top`, returns JSON (type, text, coords in content-space, flags, states). Off-screen children included.
- `click_button("text")`: matches own or child-label text, clicks center.
- `screenshot()`/`save_screenshot()` capture `screen_active()` ONLY (no `layer_top()` — drawer/bar/popups invisible). For overlays, `exec` `save_screenshot_bmp('/tmp/x.bmp', all_layers=True)` in-target (desktop shares `/tmp` with host; on device write under `/` then `read_file()`). Serial takes ~40s.
- `drag()` on the process backend is discrete taps (`simulate_click` at interpolated points), NOT a continuous swipe — gesture/swipe tests must `exec` `simulate_drag()` in-target. (Serial `drag()` is a real drag.)
- `wait_for_text("text", timeout=10)`, `expect_text("text")`.
- `startapp(name, intent={...})`, `run_app_with_file(app, file)`.
- Notification bar: `mpos.eval("mpos.ui.topmenu.bar_open")`, height 24px.
- Coordinates are LOGICAL (rotated content-space) everywhere: on-device `simulate_click`/`simulate_drag` and host `press()`/`drag()` all take the same logical coords; the rotation transform (e.g. 270°) is applied once, inside `_touch_read_cb` (`testing.py`). Do NOT pre-transform in callers — THIS SEEMS WRONG in older notes that said press() transforms; it no longer does.

**Debugging workflow:**
1. Widget tree first (`get_widget_tree()`) — layout, types, coords, states.
2. PIL + numpy from BMP for exact pixel checks.
3. ppq-vision skill for text/visuals from screenshots.
4. `get_visible_text()` for active-screen labels only.

**Pitfalls:**
- `lv_color_t` has `.red/.green/.blue` only (no `.full`).
- `lv.snapshot_take()` on hidden obj leaks theme artifacts. For truly empty images, construct `lv.image_dsc_t()` manually with zeroed `bytearray()`.
- Snapshot scaled image: wrap in container, snapshot the container. See `font_manager.py:_render_scaled_image_src()`.
- `except Exception: pass` in image paths hides failures silently.
- `lv.msgbox()` with no parent = modal. Parent = non-modal (no backdrop).
- Stale processes after SIGKILL? `killall -9 lvgl_micropy_unix run_desktop.sh`.
- When output should appear but doesn't: add temporary `print()` — generic `except Exception: pass` often hides bugs.

**Template:**
```python
import sys; sys.path.insert(0, '.')
from scripts.mpos_controller import MPOSController
with MPOSController(backend='process') as mpos:
    mpos.run_app_with_file('com.micropythonos.imageview', 'data/images/test.bmp')
    mpos.save_screenshot('tmp/screenshot.bmp')
```

## Platform constraints

### MicroPython compatibility
- Soft reset broken → `machine.reset()`.
- `hashlib.sha1(...).hexdigest()` missing → `ubinascii.hexlify(hashlib.sha1(data).digest()).decode()`.
- `os.uname()` absent on Unix port → `os.getenv('HOSTNAME', '')` or `socket.gethostname()`.
- `unittest` lacks `assertGreater/Less` → `assertTrue(a > b)`.
- `_thread` cooperative: secondary loops must yield (`time.sleep_ms(1)`, not `sleep_us()`).
- No `bytearray * int` → `bytearray(); [out.extend(buf) for _ in range(n)]`.
- Some builds lack `random.Random`/`shuffle` → Fisher-Yates with `randint`. Prefer tiny LCG for deterministic jitter.
- `logging.Logger.log()` formats via `msg % args` — always include `%s` when passing variables.
- `asyncio.TimeoutError` is NOT an `OSError` subclass on MicroPython. Catching `except OSError` for socket operations will silently miss timeouts — use `except (OSError, asyncio.TimeoutError)`.

### LVGL (import as `lv`, docs at `lvgl_micropython/lib/lvgl/docs/`)

Use: `lv.screen_active()` (not `scr_act`), `lv.button`/`lv.image`, `lv.obj.FLAG.*`, `lv.EVENT.VALUE_CHANGED`, `lv.label.LONG_MODE.WRAP`, `lv.buttonmatrix.CTRL.*`, `lv.palette_main(lv.PALETTE.RED)`, `lv.color_hex(0x...)`.

Critical gotchas:
- `lv.style_t()` must call `.init()` before setters, or device hangs.
- New labels default to `"Text"` — always `label.set_text("")`.
- LVGL wrappers can't hold Python attributes → closures/lambdas: `lambda e, i=idx: cb(e, i)`.
- `event.get_target_obj()` not `get_current_target()` (returns blob → hang).
- `lv.timer_create()` defaults to infinite. `set_repeat_count(0)` = one-shot + auto-delete → double-free on `.delete()`. Use `-1` for infinite, `1` for one-shot.
- `buttonmatrix`: no `set_button_text/set_button_ctrl` → use `set_map()`. `set_map()` fires async `VALUE_CHANGED` → 50ms debounce.
- Keyboard: always `MposKeyboard` from `mpos`, never raw `lv.keyboard()`.
- Flex layout + alignment: add `lv.obj.FLAG.FLOATING` to escape flow.
- SDL keyboard: no key-release event. Use timeout-based approach for games.
- Don't hardcode sizes >5px — use `DisplayMetrics` from `mpos`.
- Styles: setter takes value only. `style.set_bg_color(c); obj.add_style(style, lv.PART.ITEMS | lv.STATE.CHECKED)`.
- Animation: pass `True`/`False`, not `lv.ANIM.OFF`.
- Disable/enable: `obj.add_state(lv.STATE.DISABLED)` / `remove_state(...)`, NOT `obj.FLAG.DISABLED`.
- Hide/show: `obj.add_flag(lv.obj.FLAG.HIDDEN)` / `remove_flag(...)`.
- Event callbacks: 3 args, `def method(self, event=None)` for dual use.
- Use `remove_flag()`/`remove_state()` not `clear_flag()`/`clear_state()`.
- `lv.OPA` values at steps of 10 only. No `_5` — use nearest step or raw int.
- Never take a snapshot from inside a draw callback: an imgfont/style callback runs while LVGL draws, and `lv.snapshot_take_to_buf` waits for that draw forever (silent whole-system hang). Defer it with `lv.async_call` (see `FontManager._defer_scale`).
- Make UI uniform: buttons in same flex row = same height.

### MicroPython @native / @viper
- `@micropython.viper` is compile-time: `hasattr(micropython, "viper")` returns `False`. Check `hasattr(micropython, "native")`.
- Guard programmatic decorators: `if hasattr(micropython, "native"): micropython.native(func)`.
- Viper: `ba[i]` returns `object` → `int()` cast. int16 sign extension: `v = int(ba[i]) | (int(ba[i+1]) << 8); if v & 0x8000: v -= 65536`.

### ESP32
- Remember that MicroPythonOS often runs on resource constrained hardware
- `sys.platform` always `'esp32'` (S3, C3, etc.).
- `Pin.init(Pin.OUT)` silently overrides peripheral GPIO routing → no output, no error. Fix: deinit + re-create peripheral.
- Shared RMT pin: re-create RMT driver (not just `pin.init`).
- `asyncio.create_task()` from outside the event loop (timer callbacks, thread, boot services) does NOT wake the event loop — tasks queue up and execute with unpredictable delay (~6s typical on ESP32-S3). Architectures that rely on a `create_task()`-spawned loop polling a flag will fail. Instead, call `create_task()` directly from each callback (see `appstore_core._network_changed` for the proven pattern).
- `TaskManager.create_task()` crashes at C level when `TaskManager.disable()` is True (the test runner disables TaskManager). If any activity `onResume` callback calls `create_task()`, the device reboots silently — no Python traceback, no issue on desktop. Fix: guard `create_task` with `if cls.disabled: return None` in source AND mirror in `mpos_controller.py:_build_test_code` runtime patch (frozen modules shadow flash files).
- Services that call `start()` → `register_callback()` → `create_task(_run_loop())` at boot: the callback path works (fired via timer ISR on main thread), but the run-loop task may face scheduling delays. Don't rely on the run-loop for time-sensitive work — treat it as best-effort periodic background check.

### Badge buttons (fri3d 2024 vs 2026)
- Button→key mapping differs per board. Most keypad boards (2026, odroid_go, m5stack_fire, lilygo_t4, unphone, unihiker) map secondary buttons to `lv.KEY.NEXT`/`PREV`, which LVGL **consumes for focus tabbing** — the focused object never receives them as `EVENT.KEY`. Only fri3d 2024 + desktop SDL send action buttons as `ord("B")`/`ord("Y")` letters that reach apps.
- fri3d 2026 (`drivers/indev/fri3d_2026_expander.py`) **dual-delivers**: B→NEXT (tab) + `send_data(ord("B"))`, Y→PREV (tab) + `send_data(ord("Y"))`. So apps can rely on `ord("B")/ord("Y")` KEY events on both badges + desktop. Every B/Y press still tabs focus — apps that care must repair focus next frame (see `quasibird.py:_repair_focus`).
- For **held-state** (not edge) input, poll `mpos.io_expander.digital` directly (indices: `[6]=B [7]=A [8]=Y [9]=X`); see `com.casiegames.runner`. `_fire_nav_hook` in the expander driver is a `KeypadDriver` hook running in the LVGL read tick — side effects there (back_screen, send_data) follow existing precedent.

### BLE
- 31-byte advertising cap (NimBLE). No extended advertising. Scan response = separate 31 bytes.
- IRQ handlers run in main thread — LVGL calls are thread-safe.
- **Every** var assigned in IRQ handler needs `global`.
- `bytes(addr)` after scan/connect — stack reuses buffer.
- Sync event dispatch: guard `_ble_irq_handler` with recursion depth counter (~8).
- Peripheral dicts: never `clear()`. Remove stale entries by timestamp.
- GATT busy flag: clear at end of idle-exit path, not just disconnect.

### Debugging
- Bug at commit Y, worked at X: `git diff X..Y --name-only`, then trace every changed line. Don't assume the bug is in the most recent file.
- PTY I/O error (`OSError 5`) = binary crash. 139=SIGSEGV, 134=SIGABRT. Run binary directly with `-c` to reproduce.
- Trust visual reality over code intent with UI bugs. Use `mpos.get_widget_tree()` to inspect actual coordinates.
- A crash is ALWAYS a bug: fix the crash site first, work around it second — never avoidance alone. "Upstream code" is not immunity: this repo already patches IDF (`patches/*.patch` via `build_mpos.sh`), and a decodeable PC (`xtensa-*-elf-addr2line -e <elf>`) turns a mystery abort into a patchable line. Avoidance is only acceptable together with a fix attempt, or when the crash is in upstream code AND the workaround is genuinely easy (no permanent UX tax).

### Performance

Full guide: `../docs/docs/apps/app-performance.md`. Load-bearing rules:

- Measure via serial `sysmon:` (`render Xms | flush Yms`) with overlay off. FPS counts refresh cycles (~300ms window), capped ~30 by `LV_DEF_REFR_PERIOD=33ms`. `change_task_handler(period)` is the outer pump, not the refresh rate.
- ESP32-S3 SPI: 80MHz max (integer divider, 60 rounds down to 40). Freq is per-device; flush is DMA-async.
- No floats in hot loops (heap objects → GC jitter). Fixed-point milli-pixels with accumulators (naive `SPEED*dt//1000` truncation freezes slow movers); modulo-bound counters so they never outgrow small ints.
- `set_text()`/`set_offset_x()` always invalidate → guard on change. `set_x/set_y` are free when unchanged.
- Permanent `set_rotation()` = per-pixel transform forever → ship pre-rotated assets. `TILE` = 1 draw call per tile → pre-compose strips. Translucent+rounded panels = blend+mask+overdraw.
- `ruff`/`mpy-cross` on the real path: symlinked external-app files are NOT covered by `make lint`/`syntax-tests`.
- **A native game does not go through LVGL's widgets at all** — see the next section. A 320x240 frame costs ~25 ms of SPI (153600 B at ~6.2 MB/s); one band of 45 rows is 4.6 ms, and two bands per frame is ~10 ms end to end (Breakout: 56 fps). That is the ceiling to design against.

## Native modules and fast 2D games

Guide with the measurements: `../docs/docs/apps/native-apps.md`. Reference
implementation: `c_mpos/breakout/` + `internal_filesystem/apps/com.micropythonos.breakout/`.
Read this before writing another one.

**Build**
- Source in `c_mpos/<app>/`, Makefile includes `lvgl_micropython/lib/micropython/py/dynruntime.mk`, `ARCHES = x64 xtensawin`.
- Each architecture needs its **own object dir** (`BUILD=build_$@`). With the default `BUILD=build` the second architecture links the first one's objects and you get an "incompatible arch" link error or a silently wrong `.mpy`.
- xtensawin needs `xtensa-esp32-elf-gcc` on `PATH` (`~/.espressif/tools/xtensa-esp-elf/*/xtensa-esp-elf/bin`) and `ar` + `pyelftools` importable by the python that runs `mpy_ld.py` — system pip is blocked, so build with `PATH="$PWD/tmp/venv/bin:$PATH" make` (or `build.sh`).
- libc is not linked: provide `memset`/`memcpy` (word-wise; the band clear runs once per band).

**Never import in C on the hot path**
- `mp_import_name("time")` costs **32 ms** on the badge even when `time` is loaded. One `ticks_ms()` helper that imported on every call cost 32 ms of every frame. Take `now_ms` as an argument from Python.
- Prefer a "`tick(now_ms)` + `next_dirty()` + `render_band(band)` + `poll_events()`" module shape: no globals the Python side must poll, no clock in C, and the clock can be faked in tests.

**Rendering (the part that used to be wrong)**
- Use `mpos.ui.native_display.NativeDisplay`. It owns an RGB565 surface shown by a full-screen `lv_image`; `present(bands, render)` blits + flushes only the dirty bands and then calls `lv.refr_now()`.
- Do **not** draw into `main_display._frame_buffer1/2` and flush with `_data_bus.tx_color()`. Those are LVGL's draw buffers: two writers on one panel = flicker + one pass of latency per chunk (Breakout was 7.6 fps). The surface copy is free — the next band's blit overlaps the current band's DMA.
- Do **not** try to stop LVGL refreshing: `get_refr_timer().pause()` is undone by LVGL itself (it pauses at the start of each refresh and resumes when something is invalidated), and replacing the bus callback hangs LVGL in `wait_for_flushing`.
- Draw bands at their **own rows**: the surface is the whole screen, so clear at `band * rows_per_band` and index rows absolutely. Getting this wrong still shows bricks and puts the paddle at the top.
- Mark both the old and the new rectangle of anything that moves before redrawing. One band = one draw-buffer = one blit + one SPI transfer.
- Pace on the pass grid and present up to ~5 ms **early**; a deadline checked only after it expires slips a whole pass per frame (asked for 30 fps, got 25).

**A legacy framebuffer engine, measured (`c_mpos/framecore_probe/`, app `com.micropythonos.framecoreprobe`)**
- 320x200 full redraw on the Waveshare 2": 6.5 ms drawing in C + 27.2 ms `present` = **29.5 fps**. Present is 4.7 MB/s over the 80 MHz SPI (5 bands of 45 rows: blit into LVGL's draw buffer, then flush).
- `NativeDisplay(screen, buffer=engine_buffer, width=320, height=200)` wraps pixels the module allocated (`m_malloc` + `mp_obj_new_bytearray_by_ref`) with no copy, and centres a smaller surface (letterbox). `present_area(x1, y1, x2, y2, render)` flushes only a rectangle. **Invalidation takes screen coordinates**, so the image's own position must be added — a centred 320x200 surface invalidated as rows 0..199 redraws the letterbox instead of the game.
- Convert per band, not per frame: a whole-frame palette→RGB565 + present is 33.1 ms (conversion finished before the SPI starts); doing it inside the render callback should overlap the two, so re-measure before quoting a banded number (an early measurement converted only 200 pixels because `rows` was treated as a pixel count — the banded functions now take `rows * width` explicitly). A prepared 256-entry RGB565 LUT is 6.2 ms/frame, per-pixel RGB888 8.6 ms, `expand32` 9.5 ms, and a full-frame present alone is 27.2 ms, so the floor for a converted 320x200 frame is ~27 ms either way.
- Native module import cost is real: a 267 KB `.mpy` (256 KB rodata + 256 KB BSS) imports in **443 ms** and takes **537 KB** of heap. Fine on a fresh boot (~7 MB free) but a visible pause.
- The filesystem, not the panel, is the asset bottleneck: LittleFS reads **~1.3 MB/s** (16 KB = 12.5 ms, 256 KB = 257 ms); a raw flash partition reads 16 KB in 1.6 ms (~8 MB/s). Never read a game lump per frame — load/cache in RAM.
- `tests/test_graphical_native_display.py` covers the framework copy of `NativeDisplay`; on a badge whose firmware predates the change it fails (the frozen module is old) until the firmware is reflashed. The app ships its own copy, which is what actually runs from an `.mpk`.
- **A natmod's code must fit in executable RAM.** The loader commits native code with `MP_PLAT_COMMIT_EXEC` → `heap_caps_malloc(..., MALLOC_CAP_EXEC)` (`ports/esp32/main.c`), and on a booted S3 the largest contiguous exec block is **~7 KB** (`esp32.idf_heap_info(esp32.HEAP_EXEC)`: 7.2 KB / 0 / 7.4 KB). rodata and BSS are ordinary heap and can live in PSRAM, which is why the 3.8 KB framecore probe and the 267 KB "big" probe import while a Doom-class module does not: `MemoryError allocating 142528` (that is the code size). `gc.mem_free()` and `gc_try_add_heap()` are irrelevant here — the allocation is not a GC allocation. Enable `CONFIG_SPIRAM_XIP_FROM_PSRAM` (commented out in `lvgl_micropython/builder/esp32.py`) to lift the limit at an execution-speed cost, or put big engines in the firmware.
- Doom port status (`c_mpos/doom/`, app `com.micropythonos.doom`): the engine builds for x64 and xtensawin and **runs the demo on desktop**; the badge cannot import it because of the exec-RAM limit above. See `../plans/native-doom-port-status.md` for the fix options.
- Engine ports are mostly a **writable-data** problem: a natmod has text/rodata/BSS but no data section and no `static` BSS, so every writable file-scope variable must become a non-static global with no initializer and its value set in an init call (`const` tables stay as they are). 256 KB of global BSS imports fine. Do not move engine globals into Python-heap bytearrays behind getters — an earlier Doom attempt did and stalled there.

**Sound**
- A piezo beep is a PWM channel whose frequency/duty are set per event and cleared by a deadline check every frame — never `AudioManager.player()`, which costs milliseconds and allocates.
- Get the pin from `AudioManager.find_output_by_kind("buzzer")` and no-op when there is none: `get_outputs()` can be empty (the Waveshare boards have no audio at all). Poll the off-deadline **every** frame, not only on events.

**Testing**
- Graphical tests run both on desktop and on the device (`MPOSController.run_test_file`).
- Never delete the screen that is still loaded in `tearDown` (`lv.screen_load(lv.obj())` instead) — the device hangs.
- An app pumping 50 fps starves the REPL: keep device `exec` snippets short, and pause the activity between measurement steps instead of issuing long execs against a running game.
- Assert drawn **rows**, not just "some pixels": the band-offset bug passes a naive check.

**Packaging**
- A released `.mpk` must run on firmware older than your tree. Do not import a frozen module you just added to `lib/mpos/`; ship a copy in the app folder (Breakout ships `native_display.py`) and add a test that the two copies are identical.

## Apps & docs

- Install: `./scripts/install.sh com.micropythonos.appname` then `AppManager.refresh_apps()`.
- Deploy files: `mpremote cp source :/dest/` then `machine.reset()`.
- **Releasing an app:** bump `MANIFEST.JSON` → `make check-app-versions ARGS='--changed'` → `./scripts/bundle_apps.sh --app <fullname>` → commit/push `../apps` + `upload_apps.sh` → `cd ../badgehub && ./synchronize_apps.py --app <fullname>` (token per app in `../badgehub/apps.csv`). Full checklist: `../docs/docs/apps/publishing-apps.md`. Install the *extracted* `.mpk` on the badge and re-measure before publishing — that is the artifact users get.
- `self.appFullName` auto-set by ActivityNavigator — use for `SharedPreferences(self.appFullName)`.
- Prefer `mpos.ui.SettingsActivity`/`SettingActivity` over custom dialogs.
- Follow symlinks in `internal_filesystem/apps/` when searching.
- `nostr_service.py` shared between nostr/displaywallet — update both copies.
- **CHANGELOG.md:** only OS-level changes — frameworks (`internal_filesystem/lib/`), OS/runtime, board support, drivers, build and testing, and builtin apps (`internal_filesystem/builtin/apps/`). Regular apps in `internal_filesystem/apps/` are versioned and shipped through the AppStore, so never list them. Keep entries short and factual: what changed for the user, no background story. Leave an empty `Future release (next version)` section on top for the next cycle.
- **Releases:** follow `../docs/docs/other/release-checklist.md`. `scripts/release_metadata.py <version>` prepares the `install/`, `updates/` and `web/` repos from the published GitHub release; all three are archives that are deployed by rsyncing them from the parent folder, not by pushing (`web/` has no remote at all).
- Docs: sibling `../docs/`. `mkdocs build` to check. Some `.md` files intentionally excluded from nav (included by other pages) — don't add them.
