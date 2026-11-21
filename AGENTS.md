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
**Frozen bytecode is -O3** (`manifests/manifest.py`): `mpy-cross` drops every `assert` at any
`-O` level, so the frozen `unittest` in a release firmware cannot fail and every test
would pass vacuously. The runner stages `internal_filesystem/lib/unittest` on an
on-device run first (device `sys.path` puts `lib` ahead of the frozen modules) and its
harness repairs the module it already imported. A device runs the whole suite in one
interpreter: a test that assigns `sys.modules[...]` at import (the connectivity mocks
did) poisons every later test - install mocks in `setUp`/`tearDown`, and remember
MicroPython's `unittest` has no `setUpModule`.

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
- **A megabyte into the internal filesystem over a 115200 UART: gzip, base64, `mpremote fs cp` the text, decode on the device.** `fs cp` cannot carry a binary file at all (raw paste dies on the first control byte: `could not complete raw paste`), and a hand-written raw-REPL writer has to pace like mpremote does (256 bytes every 10 ms) or the ESP32 UART input buffer overruns and the command silently truncates. The WAD (1,805,391 bytes) becomes an 820,778-byte gzip and 1,094,372 bytes of base64; the copy took 4m24s. On the device decode with `ubinascii.a2b_base64` in 4 KiB chunks (the file must be one line, `base64 -w 0`), then decompress with `deflate.DeflateIO(src, deflate.GZIP)` - `zlib` is not in the firmware, only `deflate` (`AUTO`/`GZIP`/`ZLIB`/`RAW`). Freeze the UI for the whole copy (`mpos.ui.task_handler.disable()`); the paste drops bytes while the frame loop runs. **A soft reset does not restart the LVGL task handler** - a disabled handler stays disabled across `mpremote` calls, so re-enable it or hard-reset before believing `frames=0`.

## Development rules

- **TDD:** write failing test → fix → test passes.
- **Order lists alphabetically** by default: boards, drivers, docs nav entries, "related" links, board tables. Use another order only when the order carries meaning (pipeline stages, priority, a deliberate capability grouping) and say why in the surrounding text.
- **Fewer directories:** each littlefs directory costs about 8 KiB of metadata. Prefer a flat layout in `.mpk` packages and small MPOS trees; add a subdirectory only when the file count or readability needs it (roughly ten related files, or a distinct subsystem). If a path can be a filename, use the filename.
- **Lint:** every change must pass `make lint`. Ruff, double quotes.
- **Names:** use descriptive names, never bare numbers or opaque suffixes. When a framework forces a numeric variant (e.g. display drivers select `_<driver>_init_type<N>.py` through `init(type=N)`), export named constants from the package and use those at every call site (`init(st7789.PROFILE_LEGACY)`), keeping the numeric mapping in one documented place.
- **Comments/docstrings:** never add/remove/modify unless explicitly asked.
- **GitHub comments:** always very polite and gentle (issues, PRs, reviews).
- **CI strips `@micropython.native` / `@micropython.viper`**: the workflow comments those decorator lines out before running the suite, so a module must still work as ordinary Python. Pointer builtins (`ptr8`, `ptr16`) only exist inside a viper-compiled function and raise `NameError` there — probe viper once at import (see `adpcm_ima._viper_available`) and fall back to a plain-Python implementation. Reproduce locally with the same `sed` over `internal_filesystem` before pushing.
- **Batch edits:** constrain to exact patterns. Broad edits can silently delete unrelated code. If damage occurs, restore from git and re-apply a precise script.
- **Implement missing functionality** rather than working around it.
- **USB host:** DisplayLink display + HID support lives in `c_mpos/usb/` — read its `README.md` before touching USB, display, touch, or topmenu code; build with `./scripts/build_mpos.sh esp32s3 --usb`.
- **Observe before fixing, not after.** When a bug involves UI state or runtime data, use `mpos-controller` (`exec`, `get_widget_tree`, `eval`) to inspect the actual running system before coding a fix. Do NOT spend more than 2 rounds of static code analysis without validating assumptions against the live process.
- **Never put an app on autostart just so it is playing when someone looks at the screen.** `auto_start_app_early` turns the badge into a demo and a hostile test target: the app's start-up (a Doom-class engine allocates its zone) holds the loop for seconds at a time, so a copy, a flash or `machine.reset()` attempted then reports "could not enter raw repl" and costs a relay cycle first. Start the app from the REPL (`AppManager.start_app(...)`) and leave it running if the screen should show something, or tell the user to start it themselves.
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
- Widget-class enums live on the class: `lv.image.ALIGN.CENTER` (also `.CONTAIN`, `.COVER`, `.TILE`), **not** `lv.IMAGE_ALIGN.CENTER` — the top-level name does not exist (the generated type `LV_IMAGE_ALIGN` is exported as `lv.image.ALIGN`). Check `dir(lv.image)` before assuming a top-level enum. Related: `image.set_inner_align(lv.image.ALIGN.CENTER)` is what positions a scaled/rotated image in its object.
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

### Multi-touch

- Only the controllers that report more than one point can do it: `gt911` (MaTouch, Waveshare P4 4.3, D-Shell; 5 points, config `Touch Number` at 0x804C is 5 on the MaTouch) and FocalTech FT6x36 (Waveshare 3.5; 2 points). `CST816S` (fri3d 2026, Waveshare 2" and 1.54") is single-touch — no software can add a second finger.
- Driver contract: `get_touches()` returns `[(id, x, y), ...]` for the points of the last report, already passed through `_calc_coords` (i.e. in LVGL's pre-display-rotation coordinate space); `get_touch_count()` is the same list's length. `PointerDriver._read` still gets the raw first point, so single-finger behavior is unchanged. **The id is the driver's slot number** (GT911 record index, FT6x36 record index); it is not a hardware id, so do not renumber the records after dropping empty slots — a point must keep the id of the slot it was read from. Keep the ids stable where the controller allows it, but do not rely on them: the FT6x36 returns its records in touch order and shuffles them ("the touch points simply move around between the points arbitrarily"), so `TouchFingers` pairs each point with the finger that was nearest in the previous report and uses the id only as a tie-break. Without that, a second thumb landing takes record 0 and the held finger's joystick jumps to the new finger.
- **GT911 record layout on the MaTouch is X-first, not id-first:** `[xlo, xhi, ylo, yhi, size_lo, size_hi, ...]`. The pre-multitouch single-point code read bytes 0-1 as X, and that is correct; parsing the datasheet's id-first layout gives ids 10/14 and coordinates in the tens of thousands. The status nibble can also say 5 while only two slots are live, with the rest zeroed — filter records whose x/y/size are all zero, don't trust the count.
- **Keep the two-finger suppression.** On the first report with 2+ points the driver calls `indev.wait_release()` and returns `RELEASED` until all fingers lift. Without it, the first finger clicks the widget under it when the pinch ends, and a pinch starting near the edge triggers the back-swipe overlay (`gesture_navigation` handles `PRESS_LOST` to hide its ghost button).
- `mpos.ui.multitouch.MultiTouchGesture(indev=None)` polls that driver and reports `scale` (cumulative since the pair became active), `rotation` (radians, normalized), `center` (logical), `delta_x/delta_y`, `fingers`, `active`, `just_started/just_ended`. It applies LVGL's display rotation itself (`display_to_logical`), keeps the pair in matching order by id when the driver reports one (GT911/FT6x36 slot numbers) or by nearest previous point when it does not, and starts only after the fingers are `_MIN_PAIR_DISTANCE` apart.
- **A game that needs two thumbs polls the driver, it does not wait for LVGL.** The
  pointer device is single-point by design and reports the panel as released while
  2+ fingers are down, so `NativeActivity.touch_fingers = True` polls a
  `mpos.TouchMonitor` in the frame loop and delivers every finger to
  `on_touch_finger(finger, event_code, x, y)`; `on_pointer()` is not called on such a
  panel (no double handling). `TouchMonitor` reads the driver once per tick and feeds
  both the per-finger events and `MultiTouchGesture`; `ThumbZones` keeps one state per
  finger and one owner per zone (a second finger in the same band is ignored, so the
  first to lift cannot release the other's key). On the MaTouch, LVGL's indev timer
  reads the GT911 29.6 times a second (34 ms gaps, 37 ms worst), `_get_coords()` costs
  at most 2.3 ms (0.5 ms status + 1.7 ms for five records), and a press reaches the
  frame loop in ~40-80 ms; `tests/test_native_input.py` covers the identity and
  ownership rules with a fake panel.
- Image zoom/rotate model: `set_inner_align(lv.image.ALIGN.CENTER)` + `set_size(viewport)` makes the decoded image centered inside a clipping viewport; `set_scale`/`set_rotation` transform around the decoded image's center pivot (default 50/50) and `set_offset_x/y` pan it. Anchor the content point under the gesture midpoint with `offset = M - base - pivot - R(θ)·(q - pivot)·scale` (see `imageview.py`); `lv.IMAGE_ALIGN` does not exist, the enum is `lv.image.ALIGN`.

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
- fri3d 2026 (`drivers/indev/fri3d_2026_expander.py`) **dual-delivers**: B→NEXT (tab) + `send_data(ord("B"))`, Y→PREV (tab) + `send_data(ord("Y"))`. So apps can rely on `ord("B")/ord("Y")` KEY events on both badges + desktop. Every B/Y press still tabs focus — apps that care must repair focus next frame (see `quasibird.py:_repair_focus`). **The letter arrives first, in the same input read as NEXT/PREV.** An app that maps NEXT/PREV must ignore them when the letter came with them, or one button does two things (in Doom, B fired *and* turned, and in a menu NEXT also means "down", so B moved the cursor and selected at once). Doom holds the letter for one frame (`_letter_key`, cleared in `on_frame`); a bare NEXT from a board that sends no letters still turns.
- Doom's engines map only one key in menus: fire → ENTER (the button a player calls "fire" also selects). Everything else passes through — Doom's arrows already steer its menus (up/down cursor, left/right sliders). The old core mapping dropped up/down and made left/right move the cursor, so up/down did nothing and confirming needed a different button than firing.
- For **held-state** (not edge) input, poll `mpos.io_expander.digital` directly (indices: `[6]=B [7]=A [8]=Y [9]=X`); see `com.casiegames.runner`. `_fire_nav_hook` in the expander driver is a `KeypadDriver` hook running in the LVGL read tick — side effects there (back_screen, send_data) follow existing precedent.
- **Key repeat is a typing feature; games need state.** LVGL sends no key-release event, so `KeyHolds` fell back to a 180 ms deadline that a repeat refreshed. The 2026 expander's first repeat comes at 400 ms (`LONG_PRESS_TIME`) and its repeats are press/release *pairs*, so a held joystick turned for 200 ms, stopped for 230 ms, and then resumed — that is the "repeat delay" in Doom. A native game sets `NativeActivity.key_state = True`: `InputManager.held_keys()` then reads the physical state each frame (`Fri3d2026Expander.held_keys()` from `_last_digital`; a keypad that reports continuous `PRESSED` needs no method; the communicator keyboard uses its HID report), the repeats of drivers that have `set_repeat_enabled()` are switched off while the game is foreground (otherwise holding Y taps the menu ten times a second), and `KeyHolds.hold(engine_code, source_key)` stays down while `source_key` is in that set. `MIN_HOLD_MS = 60` keeps a very quick tap alive for one engine tic. UI navigation keeps its 400/100 ms repeats.

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
- **glibc's ctype inline is a natmod trap.** `toupper(c)` in glibc's `ctype.h` compiles to `(*__ctype_toupper_loc())[c]` — a *double* dereference — so the port must supply `__ctype_toupper_loc` returning `const int **` (a pointer to the table pointer). Returning the table itself hands back two chars as a pointer and the module segfaults the first time it draws text through a function that got the inline: Doom's quit prompt died there (`M_StringWidth`), while the menus happened not to be inlined. `mpos_libc.c` has the implementation; keep the signature.

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
- **A surface flush is a whole LVGL pass on the caller's stack, and a native engine calls it from inside its own tick.** `NativeDisplay.flush()` therefore checks `render_guard.has_render_headroom()` and, when the stack is nearly full, leaves the invalidation to LVGL's refresh timer. This is the one pass the task-handler guard cannot skip: the present callback runs on top of the engine's C frames (measured `micropython.stack_use()` ≈ 8.3 KB at `invalidate_band` against a 16 KB mp_task stack, with a pass needing another 4.9-7.3 KB). An overflow there does not raise — it resets or hangs the board with no output, which is exactly what a quit-and-restart session kept doing.

**A legacy framebuffer engine, measured (`c_mpos/framecore_probe/`, app `com.micropythonos.framecoreprobe`)**
- 320x200 full redraw on the Waveshare 2": 6.5 ms drawing in C + 27.2 ms `present` = **29.5 fps**. Present is 4.7 MB/s over the 80 MHz SPI (5 bands of 45 rows: blit into LVGL's draw buffer, then flush).
- `NativeDisplay(screen, buffer=engine_buffer, width=320, height=200)` wraps pixels the module allocated (`m_malloc` + `mp_obj_new_bytearray_by_ref`) with no copy, and centres a smaller surface (letterbox). `present_area(x1, y1, x2, y2, render)` flushes only a rectangle. **Invalidation takes screen coordinates**, so the image's own position must be added — a centred 320x200 surface invalidated as rows 0..199 redraws the letterbox instead of the game.
- Convert per band, not per frame: a whole-frame palette→RGB565 + present is 33.1 ms (conversion finished before the SPI starts); doing it inside the render callback should overlap the two, so re-measure before quoting a banded number (an early measurement converted only 200 pixels because `rows` was treated as a pixel count — the banded functions now take `rows * width` explicitly). A prepared 256-entry RGB565 LUT is 6.2 ms/frame, per-pixel RGB888 8.6 ms, `expand32` 9.5 ms, and a full-frame present alone is 27.2 ms, so the floor for a converted 320x200 frame is ~27 ms either way.
- Native module import cost is real: a 267 KB `.mpy` (256 KB rodata + 256 KB BSS) imports in **443 ms** and takes **537 KB** of heap. Fine on a fresh boot (~7 MB free) but a visible pause.
- The filesystem, not the panel, is the asset bottleneck: LittleFS reads **~1.3 MB/s** (16 KB = 12.5 ms, 256 KB = 257 ms); a raw flash partition reads 16 KB in 1.6 ms (~8 MB/s). Never read a game lump per frame — load/cache in RAM.
- `tests/test_graphical_native_display.py` covers `mpos.ui.native_display.NativeDisplay`; on a badge whose firmware predates the module it fails (the frozen module is old) until the firmware is reflashed. Apps **import** it from `mpos.ui.native_display`; since 0.23.0 they no longer ship a copy in the app folder (Doom, Breakout and framecoreprobe all did, and the copies drifted), and the test fails if an app folder contains a `native_display.py` again.
- **A natmod's code must fit in executable RAM.** The loader commits native code with `MP_PLAT_COMMIT_EXEC` → `heap_caps_malloc(..., MALLOC_CAP_EXEC)` (`ports/esp32/main.c`), and on a booted S3 the largest contiguous exec block is **~7 KB** (`esp32.idf_heap_info(esp32.HEAP_EXEC)`: 7.2 KB / 0 / 7.4 KB). rodata and BSS are ordinary heap and can live in PSRAM, which is why the 3.8 KB framecore probe and the 267 KB "big" probe import while a Doom-class module does not: `MemoryError allocating 142528` (that is the code size). `gc.mem_free()` and `gc_try_add_heap()` are irrelevant here — the allocation is not a GC allocation. There is **no PSRAM escape on S3**: `CONFIG_SPIRAM_XIP_FROM_PSRAM` only copies flash code/rodata into PSRAM at boot, and IDF's S3 memory layout keeps `MALLOC_CAP_EXEC` on internal DIRAM/RTC RAM only (`components/heap/port/esp32s3/memory_layout.c`), so a `MALLOC_CAP_EXEC` allocation can never be served from PSRAM. A Doom-class engine therefore has to live in the firmware (flash) or in a flash-resident core (`mpos_core` / `retro-core`, below). The natmod build still exists: it is what the desktop runs.

**Engines bigger than executable RAM: `mpos_core` (flash-resident cores)**
- `c_mpos/core_abi.h` + `c_mpos/src/core_loader.c` load an engine from a flash partition and run it *inside* MPOS: the blob is linked at fixed addresses, flashed into a partition (`retro-core`, 0x710000) and mapped executable, so its code runs XIP through the cache — no IRAM, no exec-RAM limit, and **no reboot/otadata**. Python API: `mpos_core.start(label, offset, size, present_band, palette, poll_key, read_file, file_size, log, wad_path, width, height, frame, band_rows)` (14 arguments), then `tick(now_ms)` / `stop()` / `mapped()` / `mapped_size()` / `audio_mix(buffer)` / `quit_requested()`.
- A core needs **three** fixed addresses, all declared in `mpos_core_entry_t` at offset 0 (read it through a temporary DATA mapping before mapping anything):
  1. `load_addr` — text in the instruction window (0x42000000..0x44000000 on S3);
  2. `data_addr` + `data_offset` + `data_size` — read-only data, mapped from the *same* flash pages a second time (DATA), because **IROM is not data-readable** (a string dereference faults with `LoadStoreError`). `data_offset` is a 64 KB boundary in the blob; `size == 0` in the entry means "everything after the offset".
  3. `arena_addr` + `arena_size` — `.bss`. The host allocates page-aligned RAM (PSRAM first), zeroes it and maps it at that address page by page (`esp_mmu_vaddr_to_paddr` + `mmu_hal_map_region`), so engine globals are ordinary variables, not a bytearray behind getters.
- Address choice: text at 0x43000000 (12 MB into IROM, far above the 3.6 MB app image) and the data/arena windows in the **top** of the DROM window (0x3DF00000 / 0x3DC00000). Both allocators grow up from the end of the app image, so the top of the window is unreachable in practice; anything near `_rodata_reserved_end` collides with the app's rodata and the 8 MB PSRAM mapping.
- **Never invalidate a hand-programmed MMU entry at runtime.** `mmu_hal_unmap_region()` on the arena or the text/data windows panics the chip ("Cache error", both cores) as soon as the freed pages are reused — stop() therefore leaves those entries in place and only frees the RAM; the next start re-maps the same addresses. Release only the block `esp_mmu_map()` booked, through `esp_mmu_unmap()`.
- **`esp_partition_mmap()`/`spi_flash_mmap()` pick the vaddr themselves** — a fixed-address blob faults with "MMU entry fault" if you let them choose. `map_fixed()` calls `esp_mmu_map()` (which validates the paddr, books the pages and does IDF's own cache/MMU dance) and then `mmu_hal_map_region()` for the one entry at the linked address.
- **Do not hand-roll the cache dance**: `spi_flash_disable_interrupts_caches_and_other_cpu()` + `mmu_hal_map_region()` + enable deadlocks the interrupt watchdog from a MicroPython task even with `IRAM_ATTR`. Also, code that runs with the cache disabled must be in IRAM anyway.
- **Host allocations for the core are C allocations owned by the loader** (`heap_caps_malloc`, released on `stop()`), and the Python callbacks passed to `start()` are held in one tuple registered with `MP_REGISTER_ROOT_POINTER`. A Python list of bytearrays and bare C statics both look fine and both break: **the GC does not trace C statics**, so the list and the bound methods were collected mid-run (the Doom port crashed in `mp_obj_list_append` after the engine had allocated its zone).
- `present_band(band, rows, pixels)` can carry palette indices or RGB565 (flag `MPOS_CORE_FLAG_BAND_RGB565`), or nothing at all: `abi->frame` is the host's own display buffer (`start()` arg, an ordinary Python buffer), and a core that draws into it calls `present_band(host, y, rows, NULL)`. Then Python neither copies nor converts — it only invalidates and flushes that band, so the panel transfer runs while the core draws the next one. **Present in `abi->band_rows` chunks** (the app passes `NativeDisplay.rows_per_band`), otherwise the last rows fall outside the band that gets invalidated.
- `now_ms(host)` is a live clock (`mp_hal_ticks_ms()`), not the tick's timestamp, so a core can measure its own phases. The Doom core logs `engine / convert / present` ms every two seconds; that split is how you tell a slow engine from a slow panel.
- Proven on the MaTouch (fri3d-class S3, 240x320 portrait) **and the fri3d 2026** (240x320 rotated to 320x240 landscape): `com.micropythonos.doom` boots the Doom engine from `retro-core`, reads `/doom1.wad` through the host's file callbacks, plays the E1M1 demo and takes touch/button input, at **18-19 fps on the MaTouch** and **12-19 on the fri3d** (engine 15 ms + convert 4-5 ms + present 30-36 ms at 80 MHz SPI; a full frame is ~50 ms, so the spread is the level, not the code). The MaTouch panel does take 80 MHz — the 40 in its board file was conservative.
- **A full-screen frame is panel/PSRAM bound; the transfer cannot be hidden behind the renderer.** Measured on the fri3d: 128 KB takes 21-25 ms whichever way it is pushed (LVGL flush 25 ms, `tx_color` straight from the PSRAM surface 21.7 ms, copy into the display's internal draw buffer then `tx_color` 23.3 ms), i.e. ~5-6 MB/s against the 10 MB/s the 80 MHz bus allows, and the engine runs from PSRAM too so the two do not overlap. Two traps that cost an evening: `esp_lcd_panel_io_tx_color` rejects a single transfer of 128 KB (`ESP_ERR_INVALID_ARG`) but takes 64 KB, and `_set_memory_location` costs ~6 ms when a colour transfer is queued (0.2 ms when idle) because its parameter transfer waits for it. The largest free internal block is ~45 KB, so a 128 KB DMA-ready surface is impossible; that is the wall. **Handing the bands straight to the bus was tried and reverted**: it is fast on paper (21.7 ms against 30), but the panel's address window is shared state — anything that flushes in between (the hint disappearing, the OS bar) leaves the write pointer elsewhere, so the next frame lands at a varying offset, which reads as flicker with the status bar wrapping to the top. Re-arming the window per band costs 6 ms a band and loses to the LVGL path it was meant to beat; per frame it did not hold up in practice. Keep LVGL as the only writer of the panel. Doom's tic rate is 35 Hz, so ~21 fps is what this hardware gives at 320x200. Getting there: draw into the host surface and present display-sized bands (transfer overlaps the next band's conversion), keep the engine's 64 KB framebuffer in internal RAM (small `abi_alloc` blocks prefer it), build the engine `-O2`. hello_core (`c_mpos/doom/core/hello_core.c`) covers the same contract with text, rodata and arena assertions.
- **A board module newer than its driver package boots to a black screen.** A frozen board file calling `init(st7789.PROFILE_LEGACY)` against a frozen `st7789` that predates it makes `mpos.main` raise, and `main.py` exits to the REPL: nothing draws, nothing prints unless you are watching from power-on, and it looks exactly like a bad panel clock or a boot loop. A `git pull`/merge on a second checkout can produce this mix. To see the real error, `exec(open("/main.py").read())` at the REPL. Check that the driver package is in sync before believing any display fault.
- **Never build unix and web in the same checkout at the same time.** Both use `ports/unix/build-standard`, and the web build rewrites `ports/unix/Makefile`, so a concurrent pair produces impossible link errors (`undefined symbol: machine_timer_type`, missing `MP_QSTR_mem_*`) that look like source bugs. Build them one after the other, and `git -C lvgl_micropython/lib/micropython checkout -- ports/unix` plus `rm -rf ports/unix/build-standard` before switching targets.
- **The OS boots from the *frozen* `main.py`.** `pyexec_file_if_exists()` checks frozen modules first, so `/main.py` on the vfs is ignored and a missing one is not a boot failure. Flashing firmware without preloading the filesystem is fine.
- Build/test loop: `c_mpos/doom/core/build_doom_core.sh` (dataless rewrite + fixed-address link, patches `data_offset`/`data_size` into the entry table from the ELF), `esptool.py write_flash 0x710000 build_core/doom_core.bin`, reboot. **On the MaTouch the active OTA slot is not always ota_0**: otadata lives at 0x9000 and a seq of 2 boots ota_1 (0x390000), so a firmware flashed only at 0x10000 silently keeps running the old image — flash both slots (`write_flash 0x10000 <bin> 0x390000 <bin>`) or check otadata first. `mpremote run` and multi-line `mpremote exec` fail on the OS's aiorepl; single-line `exec` and `fs cp` work when the REPL is not starved, and `Ctrl-C` in the first seconds after reset (`RTS` pulse) reaches the real REPL if a running app keeps the aiorepl busy.
- **The engine owns its sound, and both builds share the mixer.** `chocolate-doom`'s `i_sound.c` delegates to a `sound_module_t`; `c_mpos/doom/core/core_sound.c` provides one (8-voice 8-bit DMX, Doom's own 11025 Hz) and the core's entry table carries `audio_mix(dst, frames)` (ABI 6) so the *host* pulls samples when its DAC needs them. The **native module links the same file** (`-DFEATURE_SOUND`, `-Icore`, `core/core_sound.c` in SRC) and exports `audio_mix(buf)`, so a desktop can pull it too; it no longer passes `-nosound`. Two rules that file exists to teach: no `static` writable variables (a natmod cannot have static BSS), and no `.data` initialisers (a core's arena is zeroed, so `int s_volume = 15;` never survives — set it in the init function). Doom's music needs an OPL2 emulator and is a no-op module. `-DFEATURE_SOUND` makes `i_sound.c` `#include <SDL_mixer.h>` for nothing, hence `core/stub/SDL_mixer.h`.
- **One PCM sink for every host: `hosted_audio`, over SDL.** `c_mpos/hosted_audio/` is SDL audio; Emscripten's SDL2 port implements it over WebAudio (the first page interaction starts the AudioContext, as browsers require), and the Linux desktop gets it from the bundled SDL built with `SDL_ALSA=ON`, so ALSA feeds the card through PulseAudio/PipeWire/ALSA itself. `NativeActivity` owns the sink: an app sets `audio_rate` (and optionally `audio_output_kind`, which is how Doom refuses a piezo) and its engine implements `audio_mix(buffer)`; the base opens on resume, closes on pause and pulls `elapsed × rate` samples every frame. **The desktop binary is therefore linked dynamically** (`patches/unix_desktop_dynamic.patch`): a static binary cannot link `libasound.so`, `dlopen` of it from a static binary aborts with `free(): invalid pointer`, and a *static* alsa-lib was measured dead (config parser spins at 100% CPU; a minimal config opens the card exclusively, `EBUSY` next to any other audio). Cost: `libc` and `libasound` come from the host - and `modffi`'s dlopen works now too. macOS still needs the module wired to its SDL (sdl2 framework/brew), untested.
- **The buzzer is a second sink for the same mixer.** `stream_buzzer.open_sink(output, rate)` hands back the same native sink `BuzzerStream` uses for files — a `buzzer` C module that rewrites an LEDC duty from a timer interrupt at the sample rate — so an app that synthesises audio writes into it with `write(buf)` exactly as it would into `machine.I2S`. The Doom activity asks for an **i2s** output and refuses a piezo: Doom's 11 kHz broadband PCM through a resonator with no output below 2 kHz is a screech, and on a frame that is already ~50 ms its 11 kHz timer interrupt costs real time (measured: playable but unpleasant, ~-26 dBFS on a mic at the piezo). A piezo-only board therefore gets a silent Doom, which is the better of the two — the framework path stays (`open_pcm` accepts any output) so a future app with tone-like audio, or a tuned piezo sink, can use it. A 4-5 kHz tone is the control signal for such a test, not 440 Hz.
- **The zbox1 checkout can be missing whole files, not merely stale.** Gaps found so far: `partitions/`, `st7789/__init__.py`'s `PROFILE_LEGACY`, `c_mpos/src/{buzzer,hosted_module,jpegdec,mp3dec}.c` and their cmake lines, `lib/mpos/audio/{mp3,stream_buzzer,stream_mp3}.py`, `lib/mpos/ui/{native_display,render_guard}.py`, three board files and `drivers/display/st7701_dsi/`. The symptom is always an `ImportError` or a board init that raises at boot (a black screen). Copy the missing files across — a `git reset --hard` there also resets the locally patched `lvgl_micropython` submodule, so prefer copying unless you want a from-scratch rebuild.
- **Doom's quit must not tear the engine down, and an engine cannot close the app by itself.** Doom's own `I_Quit()` runs its atexit list — which `Z_Free`s the framebuffer and shuts the sound down — and then ends the process. There is no process here: the app owns the panel and the audio device, so an engine that keeps being ticked reads freed memory (that was the desktop segfault when choosing QUIT GAME). `I_Quit()` now only sets `mpos_quit_requested`; the host decides what that means. `M_QuitDOOM` skips Doom's "are you sure? press y" prompt (a badge has no 'y' key), and `create()`/`init()` clear the flag because the module and the core outlive the activity (without that, every later start quit instantly). Both engines expose it the same way: the natmod as `doom.quit_requested()`, the core through ABI 7's `quit_requested()` entry (`mpos_core.quit_requested()`), and the activity has one `finish()` path. A core on an older host (`abi->version < 7`) falls back to clearing its menus and returning to the title screen instead of freezing.
- **Both engines present the same way, and the app owns none of it.** The core draws RGB565 into the host's buffer and calls `present_band`; the native module now does the same (`doom.surface(buffer, width, height, band_rows, present)`, then `tick()` converts and announces each band), so the Python side only invalidates and flushes a band. The callback is held in C, which the GC does not trace: keep the bound method alive in the adapter (`self._present`) and clear it in `stop()`, or the next tick calls into a collected object. The module still cannot transpose its frame, so a portrait panel gets the engine's own (letterboxed, sideways) surface; the core rotates.
- **A native game should not own the frame loop.** `mpos.ui.native_activity.NativeActivity` owns the screen and its event handlers, the surface lifecycle, pacing and fps stats, the hint/message labels (rotated with the picture), `to_game()` for touch coordinates and the one quit-to-`finish()` path; `mpos.ui.native_input` provides `KeyHolds` (keypad presses are timed holds, pointer keys last until release) and `ThumbZones` (left-thumb joystick + three right action bands, laid out in the game's frame). Doom and Breakout both subclass it; Doom overrides input only, Breakout overrides `on_frame` because its engine is dirty-band driven (`surface.present(dirty_bands(), render_band)`). `_on_touch` drops events while `_surface` is None, because `setContentView` shows the screen before `onResume` starts the engine.
- **The engine presents in the panel's orientation.** The core reads the surface shape from `abi->frame_width/height`: 200x320 means rotate (portrait panel), 320x200 means send the engine's frame as it is (landscape). The app picks the surface from the display and rotates touch coordinates to match.
- A core's engine tree is built **dataless** (`tools/dataless.py`: no `.data`, no static BSS) by that same script; `.data` is discarded at link time and the build fails if anything lands there. Writable globals must be zero-initialised and set from `doom_init_all_data()`.
- PSRAM is the arena, so engine globals cost PSRAM bandwidth: the Doom frame's rotation+palette conversion was ~40 ms per frame until it was transposed in 32x32 tiles (cache-friendly reads and writes), and it is done per band now (5 ms). What is left is the renderer itself (~15 ms) — running it on the second core, or rendering fewer pixels, is the next lever; the panel transfer is at its limit.
- Doom is **one app, two engines** (`c_mpos/doom/`, `internal_filesystem/apps/com.micropythonos.doom/`): `_CoreEngine` starts the flash-resident core on `sys.platform == "esp32"`, `_NatmodEngine` imports `doom_x64.mpy` everywhere else (the xtensawin natmod is still built by `c_mpos/doom/Makefile` but no longer shipped: it cannot import on an S3). Everything above the engine is shared — surface sizing, pacing, touch zones, key mapping — because MPOS already unifies input (LVGL events) and output (`NativeDisplay`). A new engine goes behind the same seven methods (`surface_size`, `start`, `tick`, `key`, `resume`, `pause`, `stop`); don't duplicate the activity. `tick` means "advance and get this frame onto the surface, presenting bands", which is why the core can present from inside C while the natmod presents from Python. Only the core exports `audio_mix`, so the desktop build is silent (linking `core_sound.c` into the natmod is the step to take if that matters). The `.mpk` still carries `doom_x64.mpy` (360 KiB) for the desktop; a badge never imports it. See `../plans/native-doom-port-status.md`.
- Engine ports are mostly a **writable-data** problem: a natmod has text/rodata/BSS but no data section and no `static` BSS, so every writable file-scope variable must become a non-static global with no initializer and its value set in an init call (`const` tables stay as they are). A core has a real BSS (the arena) but the same dataless rewrite is what keeps `.data` empty.

**Sound**
- A piezo beep is a PWM channel whose frequency/duty are set per event and cleared by a deadline check every frame — never `AudioManager.player()`, which costs milliseconds and allocates.
- Get the pin from `AudioManager.find_output_by_kind("buzzer")` and no-op when there is none: `get_outputs()` can be empty (the Waveshare boards have no audio at all). Poll the off-deadline **every** frame, not only on events.

**Testing**
- Graphical tests run both on desktop and on the device (`MPOSController.run_test_file`).
- Never delete the screen that is still loaded in `tearDown` (`lv.screen_load(lv.obj())` instead) — the device hangs.
- A running app is a slow neighbour for the REPL, not a dead one: on the fri3d 2026 with Doom at 17 fps, single-line `mpremote exec` and `mpremote run` of a small file both got through (the app yields in the task-handler callback), while the engine's start-up — the zone allocation — holds the loop long enough for an attach in that window to fail. Keep device `exec` snippets short, and pause the activity between measurement steps instead of issuing long execs against a running game.
- Assert drawn **rows**, not just "some pixels": the band-offset bug passes a naive check.

**Packaging**
- `BuildInfo.version.api_level` is 0, so the framework API is not frozen: an app may require the latest OS and break on older firmware. Shared framework code (gestures, native display, ...) lives in `lib/mpos/` and apps import it — never ship a copy of a framework module in an app folder (copies drift; `tests/test_graphical_native_display.py` fails when a `native_display.py` reappears). An app that needs a new framework module is published only after the OS release that carries it is out (0.23.0 for anything added now), so AppStore users do not get an `ImportError`. This changes once API level 1 exists.

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
