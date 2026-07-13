# AGENTS.md

This file provides guidance to agents when working with code in this repository.

Introduction:

This repo contains MicroPythonOS, a graphical user interface and operating system for microcontrollers, complete with appstore, over-the-air updates, and lots of apps.
The main code is in the internal_filesystem/ folder, which is a one-to-one filesystem layout.
It's built on top of the lvgl_micropython/ submodule project, with itself builds on submodules like lvgl_micropython/lib/lvgl and lvgl_micropython/lib/micropython
MicroPythonOS also contains some C/C++ modules with MicroPython bindings in c_mpos/

- Build is driven by `./scripts/build_mpos.sh <target>`; it mutates tracked files (patches `lvgl_micropython/lib/micropython/ports/esp32/main/idf_component.yml`, appends include to `micropython-camera-API/src/manifest.py`). Re-run builds expecting these edits to persist unless reverted.
- A root `Makefile` now provides the preferred entry points for common tasks. Prefer these targets over direct script calls when an equivalent target exists: `make build-mpos-unix`, `make syntax-tests`, `make unittest-tests`, `make tests`, `make lint`, `make lint-fix` (use `make help` to list all targets).
- Unix/macOS builds rely on symlinks created by `build_mpos.sh` in `lvgl_micropython/ext_mod/` for `c_mpos` and `secp256k1-embedded-ecdh` because `USER_C_MODULE` is unreliable on those targets.
- Syntax tests run via `./tests/syntax.sh` and compile every `internal_filesystem/**/*.py` with `mpy-cross` but remove the .mpy files afterwards; failing files are reported by path.
- `mpy-cross` binary lives at `./lvgl_micropython/lib/micropython/mpy-cross/build/mpy-cross`.
- Unit tests run via `./tests/unittest.sh [test_file] [--ondevice]`; runner injects `main.py` and disables `mpos.TaskManager` for desktop, but on-device runs must NOT re-run boot/main (the script handles this).
- Running all unit tests takes a very long time (20 to 35 minutes) so better to run a broad selection of what might be impacted by the change. The build server will run all of them upon git push anyway.
- Graphical tests are detected by filename containing `graphical` and run with LVGL boot/main injected; non-graphical tests run without boot files.
- To run a single test, pass a file path to `./tests/unittest.sh` (absolute path is resolved inside the script).
- Testing workflow details and examples live in `tests/README.md`; check it before adding new tests.
- To install an app on a physical device: `./scripts/install.sh com.micropythonos.appname`
- After installing an app, call `AppManager.refresh_apps()` to reload the app registry before `start_app()` can find it.
- To deploy updated files to a physical device (e.g. updated `testing.py`): `python3 lvgl_micropython/lib/micropython/tools/mpremote/mpremote.py cp internal_filesystem/lib/mpos/ui/testing.py :/lib/mpos/ui/testing.py` then `import machine; machine.reset()` and wait 30 seconds for the device to boot.
- Code formatting for Python in this repo is ruff with double quotes configured in `ruff.toml` (quote-style = "double").

Guidelines:
- If something is incomplete or lacks functionality that is needed to finish the task, then implement the missing functionality, rather than working around it.
- Every code change must pass `make lint`.
- Never add, remove or modify inline comments or docstrings on your own initiative, unless the task explicitly asks for it. Comments and docstrings preserve intent and are treated as critical documentation. Refactoring or logging-conversion tasks must target only the specific code elements they're asked about and leave all other content untouched.
- Danger: batch-editing agents that operate on many files at once MUST be strictly constrained to only touch the specific patterns requested. Without tight boundary rules (e.g. "only edit lines matching `print(`"), agents may delete unrelated code: docstrings, constant definitions, function bodies, inline comments, imports, etc. If damage occurs, the safest fix might be restoring from git and running a precise targeted script, but request user confirmation before doing so.
- Debug logging: use `if __debug__: logger.debug("fmt %s", var)` (one line, `ruff.toml` ignores E701). `mpy-cross -O3` eliminates these blocks entirely at compile time — strings AND bytecode gone. Use `logger.warning/error/critical` without `__debug__` guard. Always `import logging; logger = logging.getLogger(__name__)` per file. Prefer `%s` formatting over f-strings for lazy eval.
- When converting `print()` calls to structured logging, watch for f-string edge cases: (a) `{var:format_spec}` → `%format_spec` in the format string with the var as positional arg, (b) `{var=}` debug syntax → strip the trailing `=`, (c) compound statements (`; print(...)`) need line-level matching, not just line-start matching. 
- Logging trap: `logger.error("msg: ", e)` — MicroPython's logging module formats messages with `msg % args`. A format string without `%s` (or similar) combined with a non-empty `args` raises `TypeError: format string didn't convert all arguments`. Always include a `%s` placeholder when passing variables: `logger.error("msg: %s", e)`. The same applies to `logger.warning()`, `logger.info()`, and `logger.debug()`. 
- Always add a timeout -s 9 30 to ./scripts/run_desktop.sh so run: timeout -s 9 30 ./scripts/run_desktop.sh
- Write temporary files to a `tmp/` folder in the CWD, not `/` or `/tmp`, due to permissions constraints.
- To kill processes, use `killall <name>` instead of `pkill -f <pattern>` — `pkill -f` matches the pkill command's own argv and can kill itself.
- `MPOSController` kills stale desktop binaries automatically in `start()` and cleans up on `SIGINT`/`SIGTERM`/normal exit. Only run `killall -9 lvgl_micropy_unix run_desktop.sh` manually if a hard `SIGKILL` left orphans behind.
- When using mpos-controller for debugging, write all scripts to `tmp/` in the project root (not `/tmp`). Run them with `python3 tmp/script.py`.

Guidelines for writing or updating tests:
- Use the testing facilities in ./internal_filesystem/lib/mpos/ui/testing.py and feel free to add new ones there, NOT ad hoc in the test itself.
- When adding graphical tests, follow the helpers and conventions described in tests/README.md.
- To capture logger output in tests: the logging module's `StreamHandler` stores `sys.stderr` at import time in `_stream`. Replacing `sys.stderr` at runtime does NOT redirect existing loggers. Instead, add a custom handler to the specific logger: `logging.getLogger("mpos.net.download_manager").addHandler(handler)`. In the handler's `emit()`, access the formatted message via `record.message` (not `self.format(record)`, which requires a formatter to be set). Restore the original handlers list in `finally:`.

ESP32 hardware tips:
- ESP32 GPIO matrix: `Pin.init(Pin.OUT)` reconfigures the GPIO matrix to route CPU/software GPIO to a pin, which **overrides** any peripheral (RMT, SPI, I2C, etc.) routing previously established. If a pin was claimed by a peripheral (e.g. `RMT(0, pin=pin, ...)`), calling `pin.init(Pin.OUT)` afterward disconnects the peripheral silently — no error, but no output. The peripheral appears to work (no exception, correct timing) but produces nothing. The fix is to deinit and re-create the peripheral driver after re-asserting the pin direction, so the peripheral re-acquires the GPIO matrix routing.
- ESP32 RMT + shared pins: if a pin is shared between an RMT TX driver and another peripheral (e.g. battery ADC on the Fri3d 2024 badge, GPIO 13), the correct recovery after the ADC reconfigures the pin is to deinit the RMT driver and re-create it — NOT to call `pin.init(Pin.OUT)` alone. Re-creating the driver calls `RMT(0, pin=pin, ...)` which re-establishes the GPIO matrix routing correctly.
- `sys.platform` on all ESP32 variants (including S3, C3, etc.) returns `'esp32'` in MicroPython, not `'esp32s3'` etc.

Debugging tips:
- When a user says "it worked at commit X but broke at commit Y", do `git diff X..Y --name-only` first, then `git diff X..Y -- <relevant files>` to read every changed line. Do NOT assume the bug is in the most recently touched file — trace the exact execution path through all changed files. A one-line addition in an unrelated-looking file can break something silently (e.g. `pin.init(Pin.OUT)` added for one board breaking RMT on all boards).
- Silent failures with no exception and correct-looking log output (e.g. "transmit done" in expected time) usually mean the operation ran but its output was routed/discarded somewhere. For hardware peripherals: check GPIO matrix routing, DMA channel conflicts, and whether a pin was reclaimed by another peripheral since the driver was initialized.

MicroPython BLE tips:
- BLE advertising data capped at **31 bytes**. Enforced at NimBLE HCI level (`BLE_HCI_MAX_ADV_DATA_LEN = 31` in `lib/mynewt-nimble/nimble/include/nimble/hci_common.h`). Extended advertising NOT compiled in (`MYNEWT_VAL_BLE_EXT_ADV = 0` in `extmod/nimble/syscfg/syscfg.h`). Pack service data + nickname carefully; use short name (0x08) over complete name (0x09) to save bytes. Scan response data has a separate 31-byte budget.
- BLE IRQ handlers run in the **main MicroPython thread** (NimBLE events dispatched via `mp_bluetooth_nimble_poll()` from VM main loop). LVGL widget manipulation from BLE event handlers is thread-safe — no need for `update_ui_threadsafe_if_foreground()` wrappers.
- Module-level BLE state machines: **every variable assigned in an IRQ handler needs `global`**. Forgetting it creates a silent local shadow variable (no error, state just disappears). Check every `=` across every handler function. Reading module-level vars without `global` is fine.
- UUID comparison mismatch mock vs real: mock IRQ events must pass **raw integers** for UUID fields (`uuid == 0xB2E4`), but on real hardware UUIDs are `bluetooth.UUID()` objects. A `_uuid(val)` helper that returns raw int in mock mode and `_bt.UUID(val)` on device handles both paths.
- `addr = bytes(addr)` after `_IRQ_SCAN_RESULT` / `_IRQ_PERIPHERAL_CONNECT` — the BLE stack **reuses the address buffer** after the IRQ handler returns. Copy with `bytes()` before storing for later use (e.g. in dicts or GATT connect calls).
- ESP32 BLE uses **synchronous event dispatch** (`MICROPY_PY_BLUETOOTH_USE_SYNC_EVENTS = 1` in `mpconfigport.h`). `gap_connect()`, `gattc_discover_services()`, `gattc_write()` etc. dispatch IRQ events synchronously inside the call, causing deep re-entrant nesting of `_ble_irq_handler`. Guard with a recursion-depth counter (`_irq_depth`); bail if depth exceeds ~8 to prevent `maximum recursion depth exceeded`.
- When a BLE peripheral dict (e.g. `_devices`) tracks both **scan data** (rssi, last_seen) and **ephemeral state** (friend-request relation), never `clear()` the dict — it wipes state that must survive between scan cycles. Instead, track `last_seen` timestamps per entry and remove only entries stale for N cycles at `_on_scan_done`.
- GATT busy-flag deadlock: if a `_process_gatt_queue()` function sets a `_gatt_busy = True` flag at entry and only clears it in a disconnect handler, then any exit path that finds nothing to send leaves the flag stuck True, **permanently blocking all future GATT operations**. Always clear the busy flag at the end of the idle-exit path.

LVGL tips:
- the LVGL docs are available in lvgl_micropython/lib/lvgl/docs/ for example lvgl_micropython/lib/lvgl/docs/src/details/widgets/msgbox.rst
- `lv.OPA` enum only has values at steps of 10: `TRANSP` (0), `_10`, `_20`, ..., `_100`, and `COVER` (255). Values like `_5` do NOT exist — use the nearest step or a raw integer (0–255).
- import lvgl as `lv` and use `lv.` to access it
- `lv.screen_active()` (not `lv.scr_act()`)
- use `button` instead of `btn`, `image` instead of `img`
- use `lv.EVENT.VALUE_CHANGED` instead of `lv.EVENT_VALUE_CHANGED`
- instead of `lv.OBJ_FLAG.CLICKABLE`, use `lv.obj.FLAG.CLICKABLE` (same pattern for other flags)
- instead of `.set_hidden(True)` use `.add_flag(lv.obj.FLAG.HIDDEN)`; instead of `.set_hidden(False)` use `.remove_flag(lv.obj.FLAG.HIDDEN)`
- use `.remove_flag()` instead of `.clear_flag()`
- use `obj.remove_state(...)` not `obj.clear_state(...)`
- to disable/enable a widget use `obj.add_state(lv.STATE.DISABLED)` / `obj.remove_state(lv.STATE.DISABLED)`; do NOT use `obj.add_flag(lv.obj.FLAG.DISABLED)`
- event handlers need 3 arguments: `button.add_event_cb(button_cb, lv.EVENT.CLICKED, None)`
- if you pass a method as an event callback, it must accept the event argument: `def callback(self, event)`. Using the same method as both a direct call and an event callback requires a default: `def method(self, event=None)`.
- don't hard-code display resolution; use `lv.pct(100)` or other techniques to scale the interface
- use `DisplayMetrics` (`from mpos import DisplayMetrics`) for widget sizes and spacing; avoid hard-coding pixel values greater than 5. Prefer `DisplayMetrics.pct_of_width(...)`, `DisplayMetrics.pct_of_height(...)`, `DisplayMetrics.width()`, etc.
- `DRAW_PART_BEGIN` does not exist anymore
- don't use `get_child_by_type()`; use a global variable with the child you want instead
- msgbox: `msgbox = lv.msgbox()` then `msgbox.add_title("title")`
- use `lv.buttonmatrix.CTRL.CHECKABLE` instead of `lv.BUTTONMATRIX_CTRL_CHECKABLE`
- use `lv.buttonmatrix.CTRL.CHECKED` instead of `lv.BUTTONMATRIX_CTRL_CHECKED`
- colors: `RED = lv.palette_main(lv.PALETTE.RED)` or `DARKPINK = lv.color_hex(0xEC048C)`
- use `lv.anim_t.path_ease_in_out` not `lv.anim_path_ease_in_out`
- instead of `label.set_long_mode(lv.label.LONG.WRAP)` use `label.set_long_mode(lv.label.LONG_MODE.WRAP)`
- use `style_obj = lv.style_t()` then `style_obj.init()` instead of `lv.style()`
- always call `style.init()` after `lv.style_t()` before calling setters like `set_bg_color()` — without it the device may hang
- don't leave label text uninitialized; it defaults to `"Text"` instead of being empty. Always set text explicitly with `label.set_text("")` if you want an empty label
- In LVGL 9.x style setters take only the value (no selector). The selector goes in `add_style()`. E.g. `style.set_bg_color(lv.color_hex(0x...))` then `obj.add_style(style, lv.PART.ITEMS | lv.STATE.CHECKED)`.
- `lv.buttonmatrix` has no `set_button_text()` or `set_button_ctrl()` in this binding. To update text, rebuild and call `set_map()`. To mark buttons visually (e.g. solved state), change the text symbol itself (e.g. append "!").
- `lv.buttonmatrix.set_map()` fires `LV_EVENT_VALUE_CHANGED` asynchronously (next LVGL tick), causing phantom second-selection events. Guard with a time-based debounce (`time.ticks_diff(now, last_ts) < 50`) rather than a simple flag.
- use `obj.scroll_to_view_recursive(True)` to scroll something into view or widget.scroll_to_y(0x7FFFFFFF, True) to scroll all the way down in a widget
- Don't use lv.ANIM.OFF nor lv.ANIM_OFF - just pass False if you dont want animation or True if you do want animation
- LVGL object wrappers (e.g. `lv.button()`, `lv.obj()`) do NOT support arbitrary Python attribute assignment (`btn.idx = 5` raises `AttributeError`). To associate data with a widget, use closures/lambdas (`lambda e, i=idx: callback(e, i)`) or maintain parallel lists keyed by list index.
- In event callbacks, use `event.get_target_obj()` instead of `event.get_current_target()`. The latter returns a generic `Blob` that can hang when passed to typed LVGL methods (e.g. `lv.list.get_button_text()`). `get_target_obj()` returns a properly typed `lv.obj`.
- `lv.obj.set_style_scrollbar_mode()` does NOT exist in this binding. Use `obj.remove_flag(lv.obj.FLAG.SCROLLABLE)` to hide scrollbars.
- Always call `label.set_text("")` on newly created labels — they default to displaying the literal text `"Text"` otherwise.
- Use `align_to(existing_widget, lv.ALIGN.OUT_RIGHT_MID, offset, 0)` to position a widget relative to another.
- On a parent with `lv.FLEX_FLOW.COLUMN` (or any flex layout), `lv.ALIGN.TOP_RIGHT` alone won't float a widget in the top-right corner — flex layout still pushes it into the flow. Add `lv.obj.FLAG.FLOATING` to remove the widget from the flex flow so alignments work as expected.
- The lvgl_micropython SDL keyboard driver processes each key event as an instantaneous press+release pair via `LV_INDEV_MODE_EVENT`. It calls `lv_indev_read()` twice per SDL_KEYDOWN (once returning PRESSED, once RELEASED). **SDL_KEYUP is completely ignored** — no `LV_EVENT_KEY` fires on key release. To detect key release in games, use a timeout-based approach: on first press set a long deadline (~600ms to cover SDL's initial repeat delay), on repeat events set a short extension (~100ms to cover the steady-state repeat interval), and reset movement direction when the deadline expires. Track the deadline with `_player_dir_until` and check `time.ticks_diff(now, _player_dir_until) > 0` in the game loop.
- On-screen keyboards: always use `MposKeyboard` from `mpos.ui.keyboard` (already exported from `mpos`). Never use the raw `lv.keyboard()` widget. If `MposKeyboard` is missing a feature you need, extend `MposKeyboard` instead of falling back to `lv.keyboard()`.
- `lv.timer_create()` creates timers with `repeat_count = -1` (infinite/periodic). Calling `set_repeat_count(0)` does **not** make a timer infinite; in LVGL 9.x it means "fire once and auto-delete". If Python code later calls `.delete()` on that wrapper, it will double-free the timer struct and corrupt `timer_ll`, typically producing a SIGSEGV inside `lv_timer_delete` -> `lv_ll_remove` with a dangling next-node pointer. Leave the default alone for an infinite periodic timer, or make the intent explicit with `set_repeat_count(-1)`. Use `set_repeat_count(1)` only for genuine one-shot timers.

MicroPythonOS tips:
- `self.appFullName` is automatically set by the ActivityNavigator when launching an Activity. Use it instead of hard-coding the app's package name (e.g. for `SharedPreferences(self.appFullName)`).
- Use `mpos.ui.SettingsActivity` to edit multiple related settings and `mpos.ui.SettingActivity` to edit a single setting. Prefer these shared activities over building custom dialogs or activities.
- When investigating a UI bug, trust visual reality over the code's intent. Especially with LVGL flex layouts, aligning a column to the bottom of its parent does **not** reverse child paint order: the first child created still renders at the visual top. Inspect the actual widget coordinates — for example with `mpos.get_widget_tree()` — instead of reasoning only from the internal data model. And when a user keeps insisting after an initial disagreement, they are likely seeing something you are missing.
- Debug-log trap with `__debug__` guards: `if __debug__: logger.debug("x=%s", x)` only compiles away under `-O3` (`__debug__ = False`). When `__debug__` is `True` (default), the statement executes normally — **variables referenced in the format string must be defined before the log line**, not after. Order matters: assign first, log second.

MicroPython compatibility:
- Soft reset is broken on lvgl_micropython and therefore also on MicroPythonOS. Use `machine.reset()` to do a hard reset.

MicroPython compatibility:
- Some builds ship a minimal `random` module without `random.Random` or `random.shuffle`. For shuffling, implement Fisher-Yates manually with `random.randint`.
- For deterministic jitter in apps, prefer a tiny local LCG (linear congruential generator) instead of `random.Random`.
- MicroPython's `logging.Logger.log()` (and by extension `error()`, `warning()`, etc.) formats messages via `msg % args`. Passing a variable to a format string without a `%s` placeholder raises `TypeError`. Always include a `%s` in the format string: `logger.error("msg: %s", e)`.
- MicroPython's `unittest` module lacks `assertGreater`, `assertGreaterEqual`, `assertLess`, `assertLessEqual`. Use `assertTrue(a > b, msg)` instead of `assertGreater(a, b, msg)`.
- MicroPython's `_thread` module is cooperative: a tight loop in a secondary thread can prevent the main thread (and therefore LVGL's `lv_timer_handler`) from running. Long-running secondary-thread loops should yield occasionally, e.g. `time.sleep_ms(1)`. Do not use `time.sleep_us()` for this — it busy-waits and does not yield.
- MicroPython does NOT support `bytearray * int` (e.g. `b = bytearray(4); b * 3` raises `TypeError: unsupported types for __mul__`). To repeat a `bytearray`, create a new one and extend it in a loop: `out = bytearray(); [out.extend(buf) for _ in range(n)]`. (`bytes * int` works in CPython but is also not guaranteed on MicroPython; prefer an explicit loop.)

MPOS Controller (`scripts/mpos_controller.py`):
- `MPOSController` drives MicroPythonOS from CPython via PTY/aioREPL or serial/UART.
- **`MPOSController()` does NOT auto-start a subprocess.** Call `mpos.start()` to launch `run_desktop.sh`, then wait at least `~8s` for boot before calling `startapp()` or any other method. Without `.start()` the internal `repl` is `None` and you get `AttributeError: 'NoneType' object has no attribute 'exec'`.
- Two backends: `MPOSController()` for local desktop process, `MPOSController(backend="serial", port="/dev/ttyACM0")` for physical device.
- Use `mpos.exec("code")`, `mpos.eval("expr")`, `mpos.screenshot()`, `mpos.save_screenshot(path)`, `mpos.screenshot_pixels()`, `mpos.screenshot_image()`, `mpos.press(x,y)`, `mpos.press_key("text")`, `mpos.click_button("text")`, `mpos.find_widget(type=..., text=...)`, `mpos.press_widget(type=..., text=...)`, `mpos.wait_for_text("text")`, `mpos.expect_text("text")`, `mpos.get_visible_text()`, `mpos.get_widget_tree()`, `mpos.read_file(path)`, `mpos.write_file(path, data)`.
- `exec()` and `exec_multiline()` both use **paste mode** (Ctrl-E / Ctrl-D) internally — multi-line code, quotes, and special chars need no escaping. They're equivalent; use whichever is convenient.
- `get_visible_text()` uses `exec_multiline()` iterating individual `repr()` prints — critical for serial where `print(repr(big_list))` corrupts for large lists with escape sequences. **Only extracts text from `lv.screen_active()`, not `lv.layer_top()`.** Popup/msgbox text is invisible to this method; use `get_widget_tree()` (which includes layer_top) or `screenshot(all_layers=True)` with ppq-vision instead.
- `exec()` auto-drains input buffer before sending then enters paste mode (Ctrl-E).
- `SerialBackend.wait_for_boot()` uses Ctrl-C to break into aioREPL (device may be running apps).
- The CLI supports `--serial-port <port>` and `--baudrate <rate>` for serial connections. To pipe code without quoting: `cat <<'EOF' | python3 scripts/mpos_controller.py --serial-port /dev/ttyACM0 exec`
- When no args are given and stdin is not a TTY, `exec` and `eval` read from stdin automatically — enabling heredoc/pipe usage.
- **Rotation handling**: SerialBackend caches `_rotation` from the display on connect. If rotation is 270° (value 3, common for landscape badges), `press(x, y)` auto-transforms coordinates: `simulate_click(height - 1 - y, x)` so caller always uses LVGL logical coordinates.
- `mpos.get_widget_tree()` dumps the full LVGL widget tree for both `lv.screen_active()` and `lv.layer_top()`. Returns JSON with type, text, coordinates, flags (clickable, hidden, scrollable, floating, event_bubble, etc.), states (checked, disabled, focused, pressed, etc.), scroll position, opacity, and widget-specific fields (slider value, dropdown options, textarea state, etc.). Uses `mpos.ui.testing.get_screen_widget_tree()` directly — no file I/O on desktop; on serial the JSON is written to a temp file then read via `mpremote cp` to avoid serial corruption of large outputs.
- IMPORTANT: `get_widget_tree()` and `get_visible_text()` include ALL children of scrollable parents, including off-screen items. y1/y2 coordinates are in content space, not screen space. To know what's actually visible, combine a screenshot (`mpos.screenshot()`) with the ppq-vision skill.
- `_read_remote_file` / `write_remote_file`: ProcessBackend uses base64 (works over PTY), SerialBackend uses `mpremote cp` (reliable over USB).
- `mpos.screenshot()` captures via `capture_screenshot()` on device, then reads raw file and converts to BMP via `_build_bmp()`. Over serial (`/dev/ttyACM0`) this takes ~40s total (~6s connect, ~34s transfer).
- The notification bar (top status bar) is NOT always present. It's controlled by the `bar_open` global in `internal_filesystem/lib/mpos/ui/topmenu.py`. Check it with `mpos.eval("mpos.ui.topmenu.bar_open")` (the module is already imported by `main.py`). When open, its height is `AppearanceManager.NOTIFICATION_BAR_HEIGHT` (24px).
- `mpos.startapp(appname)` launches an installed app; pass `intent={"data": filename, "action": ..., "extras": {...}}` to start an app with an `mpos.Intent` (e.g. opening a specific file in ImageView).
- `mpos.run_app_with_file(appname, filename)` boots and launches *appname* pre-populated with a file intent — convenient for testing "Open With" flows.
- `mpos.click_button("text")` finds a clickable widget whose own text or child-label text matches and clicks its center, avoiding manual coordinate math. For buttons, use this instead of `find_widget` because button text lives on a child label.
- `mpos.wait_for_text("text", timeout=10)` polls the screen until the text appears (or `disappear=True`); `mpos.expect_text("text")` raises if it doesn't appear.
- `mpos.screenshot_image()` returns a PIL `Image` (requires `pillow`), and `mpos.screenshot_pixels()` returns `(width, height, rgb888_bytes)` for direct pixel checks.
- The CLI also supports `startapp <appname>` (launches an app) and `checkfreespace` (reports free disk space and whether a screenshot fits).
- All tests pass covering exec, eval, screenshot, input simulation, screen introspection, file I/O, and physical device control.
- Host-side controller tests in `tests/cpython_mpos_controller.py` run via `python3 tests/cpython_mpos_controller.py` (desktop) or `python3 tests/cpython_mpos_controller.py --serial /dev/ttyACM0` (device); they are NOT run by `unittest.sh` (which targets MicroPython-side tests).

## Debugging with MPOS Controller

### Creating debug scripts
Write all scripts to `tmp/` in the project root:
```
python3 tmp/my_debug_script.py
```
Template:
```python
import sys
sys.path.insert(0, '.')
from scripts.mpos_controller import MPOSController

with MPOSController(backend='process') as mpos:
    mpos.run_app_with_file('com.micropythonos.imageview', 'data/images/test.bmp')
    mpos.save_screenshot('tmp/screenshot.bmp')
    pixels = mpos.screenshot_pixels()  # (width, height, rgb888_bytes)
```

### Analyzing screenshots (preferred techniques)
- **PIL + numpy** is the most reliable technique. Load the BMP, convert to numpy array, then check specific pixel coordinates for exact RGB values.
- **Widget tree** (`mpos.get_widget_tree()`): gives layout, types, text, coordinates, states, flags for every widget. Use this FIRST to understand screen structure.
- **Visible text** (`mpos.get_visible_text()`): extracts text from all labels on `lv.screen_active()`. Does NOT see `lv.layer_top()` popups/msgboxes. When a user reports text your tools don't capture (especially dialog prompts), trust visual reality over tool output.
- **PPQ vision skill** (`ppq-vision`): use for reading text content from screenshots or understanding visual layout when coordinates alone are insufficient.
- **ASCII art conversion**: NOT reliable for precise color analysis. Only use for quick visual structure checks when other methods aren't available.

### Effective debugging workflow
1. When a code path should produce output but doesn't, add a temporary `print()` diagnostic to see if the code even executes — generic `except Exception: pass` blocks often hide bugs.
2. When a function should return a specific type (e.g., `lv.image_dsc_t`), check what it actually returns with `print(type(result))`.
3. For color/image issues, inspect raw pixel buffer data (bytearray at known offsets) rather than relying on visual appearance.
4. Temporarily add detailed diagnostics (buffer dumps, type checks, hex printing) to `tmp/` files on-device, then retrieve via `mpos.read_file()`.

### LVGL debugging pitfalls
- `lv_color_t` in this MicroPython LVGL binding has ONLY `.red`, `.green`, `.blue` attributes — there is NO `.full` attribute.
- `lv.snapshot_take()` on a hidden `lv.obj()` still captures non-transparent pixel data because inherited theme styles (borders, shadows, background from parent theme) leak through the hidden object into the snapshot. For truly empty images, construct an `lv.image_dsc_t()` manually with a zeroed `bytearray()`.
- To snapshot a scaled `lv.image`, wrap it in a container (`lv.obj()`). `lv.snapshot_take_to_buf()` on the image alone won't see that the image size changed due to `set_scale()` and only captures a middle crop. Create a hidden container sized to the target dimensions, place the image inside it with `center()` and `set_size(target_w,target_h)`, then snapshot the container. Don't forget `set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)` and opaque style resets to avoid theme leakage. See `font_manager.py:_render_scaled_image_src()` for the canonical pattern.
- `except Exception: pass` is especially dangerous in image rendering paths — it silently falls back to unscaled/unprocessed source data, making it appear that transformations run when they don't.
- To create a manual empty image descriptor:
  ```python
  buf = bytearray(4)
  dsc = lv.image_dsc_t()
  dsc.data = buf
  dsc.header.w = 1
  dsc.header.h = target_height
  dsc.header.cf = lv.COLOR_FORMAT.ARGB8888
  ```

### Popup / msgbox tips
- Use `lv.msgbox()` with **no parent** for a true modal dialog. Passing a parent such as `lv.layer_top()` creates a non-modal msgbox and skips the dimming backdrop that blocks input to the rest of the screen.
- Add custom input widgets (e.g. `lv.textarea`) to the content container returned by `mbox.get_content()`.
- Default `mpos.screenshot()` and `capture_screenshot()` do **not** include `lv.layer_top()` overlays. Pass `all_layers=True` to capture popups/notifications in screenshots — it's slower but necessary for verifying dialog appearance.
- If screenshots or MPOSController behave oddly after hard-killing debug scripts (e.g. `timeout -s 9 ...`), check for stale `lvgl_micropy_unix`/`run_desktop.sh` processes with `ps aux | grep lvgl_micropy_unix`. Clean them up with `killall -9 lvgl_micropy_unix run_desktop.sh`.


### Specific app tips
- The app internal_filesystem/apps/com_micropythonos_nostr and the app internal_filessytem/apps/com.lightningpiggy.displaywallet (symlinked) use the same copy of nostr_service.py so when you update it, make sure to also update the other copy of that file and make sure it doesn't break the other app either.
- Some apps in internal_filesystem/apps/ are symlinks to outside repo's like all the com.quasikili.* apps and com.lightningpiggy.displaywallet so be sure to follow symlinks when grepping and finding etc

## Documentation

Public documentation source lives in the sibling `../docs/` directory (`/home/user/projects/MicroPythonOS/claude/docs`). It is a separate MkDocs site from the MicroPythonOS code repository.

When editing docs:
- Run `python3 -m mkdocs build` (or `./build.sh`) from the `../docs/` directory to check for errors.
- Some Markdown files are intentionally included into other pages instead of being listed directly in `mkdocs.yml` nav. Examples from `../docs/docs/os-development/`:
  - `compiling.md` is included by `linux.md` and `macos.md`.
  - `running-on-desktop.md` is included by `linux.md` and `macos.md`.
- This is why `mkdocs build` warns "The following pages exist ... but are not included in the nav" for those files. Do not add them to `nav` unless explicitly requested.
