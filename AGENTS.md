# AGENTS.md

This file provides guidance to agents when working with code in this repository.

- Build is driven by `./scripts/build_mpos.sh <target>`; it mutates tracked files (patches `lvgl_micropython/lib/micropython/ports/esp32/main/idf_component.yml`, appends include to `micropython-camera-API/src/manifest.py`, and toggles `@micropython.viper` in `internal_filesystem/lib/mpos/audio/stream_wav.py`). Re-run builds expecting these edits to persist unless reverted.
- Unix/macOS builds rely on symlinks created by `build_mpos.sh` in `lvgl_micropython/ext_mod/` for `c_mpos` and `secp256k1-embedded-ecdh` because `USER_C_MODULE` is unreliable on those targets.
- Syntax tests run via `./tests/syntax.sh` and compile every `internal_filesystem/**/*.py` with `mpy-cross`; failing files are reported by path.
- Unit tests run via `./tests/unittest.sh [test_file] [--ondevice]`; runner injects `main.py` and disables `mpos.TaskManager` for desktop, but on-device runs must NOT re-run boot/main (the script handles this).
- Graphical tests are detected by filename containing `graphical` and run with LVGL boot/main injected; non-graphical tests run without boot files.
- To run a single test, pass a file path to `./tests/unittest.sh` (absolute path is resolved inside the script).
- Testing workflow details and examples live in `tests/README.md`; check it before adding new tests.
- To install an app on a physical device: `./scripts/install.sh com.micropythonos.appname`
- After installing an app, call `AppManager.refresh_apps()` to reload the app registry before `start_app()` can find it.
- To deploy updated files to a physical device (e.g. updated `testing.py`): `python3 lvgl_micropython/lib/micropython/tools/mpremote/mpremote.py cp internal_filesystem/lib/mpos/ui/testing.py :/lib/mpos/ui/testing.py` then `import machine; machine.reset()` and wait 30 seconds for the device to boot.
- Code formatting for Python in this repo is ruff with double quotes configured in `ruff.toml` (quote-style = "double").

Guidelines:
- If something is incomplete or lacks functionality that is needed to finish the task, then implement the missing functionality, rather than working around it.
- Always add a timeout -s 9 30 to ./scripts/run_desktop.sh so run: timeout -s 9 30 ./scripts/run_desktop.sh
- Write temporary files to a `tmp/` folder in the CWD, not `/` or `/tmp`, due to permissions constraints.

Guidelines for writing or updating tests:
- Use the testing facilities in ./internal_filesystem/lib/mpos/ui/testing.py and feel free to add new ones there, NOT ad hoc in the test itself.
- When adding graphical tests, follow the helpers and conventions described in tests/README.md.

LVGL tips:
- import lvgl as `lv` and use `lv.` to access it
- `lv.screen_active()` (not `lv.scr_act()`)
- use `button` instead of `btn`, `image` instead of `img`
- use `lv.EVENT.VALUE_CHANGED` instead of `lv.EVENT_VALUE_CHANGED`
- instead of `lv.OBJ_FLAG.CLICKABLE`, use `lv.obj.FLAG.CLICKABLE` (same pattern for other flags)
- instead of `.set_hidden(True)` use `.add_flag(lv.obj.FLAG.HIDDEN)`; instead of `.set_hidden(False)` use `.remove_flag(lv.obj.FLAG.HIDDEN)`
- use `.remove_flag()` instead of `.clear_flag()`
- use `obj.remove_state(...)` not `obj.clear_state(...)`
- event handlers need 3 arguments: `button.add_event_cb(button_cb, lv.EVENT.CLICKED, None)`
- if you pass a method as an event callback, it must accept the event argument: `def callback(self, event)`. Using the same method as both a direct call and an event callback requires a default: `def method(self, event=None)`.
- don't hard-code display resolution; use `lv.pct(100)` or other techniques to scale the interface
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
- In LVGL 9.x style setters take only the value (no selector). The selector goes in `add_style()`. E.g. `style.set_bg_color(lv.color_hex(0x...))` then `obj.add_style(style, lv.PART.ITEMS | lv.STATE.CHECKED)`.
- `lv.buttonmatrix` has no `set_button_text()` or `set_button_ctrl()` in this binding. To update text, rebuild and call `set_map()`. To mark buttons visually (e.g. solved state), change the text symbol itself (e.g. append "!").
- `lv.buttonmatrix.set_map()` fires `LV_EVENT_VALUE_CHANGED` asynchronously (next LVGL tick), causing phantom second-selection events. Guard with a time-based debounce (`time.ticks_diff(now, last_ts) < 50`) rather than a simple flag.
- LVGL object wrappers (e.g. `lv.button()`, `lv.obj()`) do NOT support arbitrary Python attribute assignment (`btn.idx = 5` raises `AttributeError`). To associate data with a widget, use closures/lambdas (`lambda e, i=idx: callback(e, i)`) or maintain parallel lists keyed by list index.
- In event callbacks, use `event.get_target_obj()` instead of `event.get_current_target()`. The latter returns a generic `Blob` that can hang when passed to typed LVGL methods (e.g. `lv.list.get_button_text()`). `get_target_obj()` returns a properly typed `lv.obj`.

MicroPythonOS tips:
- `self.appFullName` is automatically set by the ActivityNavigator when launching an Activity. Use it instead of hard-coding the app's package name (e.g. for `SharedPreferences(self.appFullName)`).

MicroPython compatibility:
- Soft reset is broken on lvgl_micropython and therefore also on MicroPythonOS. Use `machine.reset()` to do a hard reset.

MicroPython compatibility:
- Some builds ship a minimal `random` module without `random.Random` or `random.shuffle`. For shuffling, implement Fisher-Yates manually with `random.randint`.
- For deterministic jitter in apps, prefer a tiny local LCG (linear congruential generator) instead of `random.Random`.

MPOS Controller (`scripts/mpos_controller.py`):
- `MPOSController` drives MicroPythonOS from CPython via PTY/aioREPL or serial/UART.
- Two backends: `MPOSController()` for local desktop process, `MPOSController(backend="serial", port="/dev/ttyACM0")` for physical device.
- Use `mpos.exec("code")`, `mpos.eval("expr")`, `mpos.screenshot()`, `mpos.press(x,y)`, `mpos.press_key("text")`, `mpos.get_visible_text()`, `mpos.get_widget_tree()`, `mpos.read_file(path)`, `mpos.write_file(path, data)`.
- `exec()` and `exec_multiline()` both use **paste mode** (Ctrl-E / Ctrl-D) internally — multi-line code, quotes, and special chars need no escaping. They're equivalent; use whichever is convenient.
- `get_visible_text()` uses `exec_multiline()` iterating individual `repr()` prints — critical for serial where `print(repr(big_list))` corrupts for large lists with escape sequences.
- `exec()` auto-drains input buffer before sending then enters paste mode (Ctrl-E).
- `SerialBackend.wait_for_boot()` uses Ctrl-C to break into aioREPL (device may be running apps).
- The CLI supports `--serial-port <port>` and `--baudrate <rate>` for serial connections. To pipe code without quoting: `cat <<'EOF' | python3 scripts/mpos_controller.py --serial-port /dev/ttyACM0 exec`
- When no args are given and stdin is not a TTY, `exec` and `eval` read from stdin automatically — enabling heredoc/pipe usage.
- **Rotation handling**: SerialBackend caches `_rotation` from the display on connect. If rotation is 270° (value 3, common for landscape badges), `press(x, y)` auto-transforms coordinates: `simulate_click(height - 1 - y, x)` so caller always uses LVGL logical coordinates.
- `mpos.get_widget_tree()` dumps the full LVGL widget tree for both `lv.screen_active()` and `lv.layer_top()`. Returns JSON with type, text, coordinates, flags (clickable, hidden, scrollable, floating, event_bubble, etc.), states (checked, disabled, focused, pressed, etc.), scroll position, opacity, and widget-specific fields (slider value, dropdown options, textarea state, etc.). Uses `mpos.ui.testing.get_screen_widget_tree()` directly — no file I/O on desktop; on serial the JSON is written to a temp file then read via `mpremote cp` to avoid serial corruption of large outputs.
- IMPORTANT: `get_widget_tree()` and `get_visible_text()` include ALL children of scrollable parents, including off-screen items. y1/y2 coordinates are in content space, not screen space. To know what's actually visible, combine a screenshot (`mpos.screenshot()`) with the ppq-vision skill.
- `_read_remote_file` / `write_remote_file`: ProcessBackend uses base64 (works over PTY), SerialBackend uses `mpremote cp` (reliable over USB).
- `mpos.screenshot()` captures via `capture_screenshot()` on device, then reads raw file and converts to BMP via `_build_bmp()`.
- The notification bar (top status bar) is NOT always present. It's controlled by the `bar_open` global in `internal_filesystem/lib/mpos/ui/topmenu.py`. Check it with `mpos.eval("mpos.ui.topmenu.bar_open")` (the module is already imported by `main.py`). When open, its height is `AppearanceManager.NOTIFICATION_BAR_HEIGHT` (24px).
- All tests pass covering exec, eval, screenshot, input simulation, screen introspection, file I/O, and physical device control.
- Host-side controller tests in `tests/cpython_mpos_controller.py` run via `python3 tests/cpython_mpos_controller.py` (desktop) or `python3 tests/cpython_mpos_controller.py --serial /dev/ttyACM0` (device); they are NOT run by `unittest.sh` (which targets MicroPython-side tests).
