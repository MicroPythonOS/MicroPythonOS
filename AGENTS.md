# AGENTS.md

Guidance for AI assistants working in this repo. Keep it short.

## Project & build

MicroPythonOS: GUI + OS for microcontrollers. Source: `internal_filesystem/` (1:1 filesystem). C modules: `c_mpos/`. Built on `lvgl_micropython/` (LVGL + MicroPython).

**Desktop builds run MicroPython, NOT CPython.** `sys.implementation.name == 'micropython'`. Stdlib is minimal — no `uuid`, no `machine.unique_id()`.

- Build: `./scripts/build_mpos.sh <target>` (mutates tracked files — those edits persist).
- Prefer Makefile targets: `make build-mpos-unix`, `make lint`, `make lint-fix`, `make tests`, `make help`.
- `mpy-cross`: `./lvgl_micropython/lib/micropython/mpy-cross/build/mpy-cross`. Needs `-march=x64` for native/viper on desktop.
- Unix/macOS: `build_mpos.sh` creates symlinks in `lvgl_micropython/ext_mod/` for `c_mpos` and `secp256k1-embedded-ecdh`.

## Testing

**Run:** `./scripts/test_runner.py tests/<test_file> [--ondevice] [--port <port>] [--reset]`  
**All tests:** `make tests` (20–35 min). CI runs them on push. **Syntax:** `make syntax-tests`  
**CPython controller tests:** `python3 tests/cpython_mpos_controller.py` (not run by test_runner.py).  
**Details:** `tests/README.md`

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
- Use helpers in `internal_filesystem/lib/mpos/ui/testing.py`. Follow `tests/README.md` for graphical tests.

**After any code change:** grep for tests importing changed modules, run them. Do NOT skip.  
**If you modify a test:** run it to verify.

**Capturing logger output in tests:** add custom handler to logger, access `record.message` in `emit()`. Restore handlers in `finally:`.  
**Test decorators:** `@unittest.skipIf` must be directly above the function — no module-level code between.

**Most common test segfault cause:** passing a non-LVGL Python object (mock, plain instance) as parent to any LVGL widget constructor. Mock the calling method instead, or use real `lv.obj()` (graphical test).

## Development rules

- **TDD:** write failing test → fix → test passes.
- **Lint:** every change must pass `make lint`. Ruff, double quotes.
- **Comments/docstrings:** never add/remove/modify unless explicitly asked.
- **Batch edits:** constrain to exact patterns. Broad edits can silently delete unrelated code. If damage occurs, restore from git and re-apply a precise script.
- **Implement missing functionality** rather than working around it.

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
- `screenshot()`: use `all_layers=True` for popups. Serial takes ~40s.
- `wait_for_text("text", timeout=10)`, `expect_text("text")`.
- `startapp(name, intent={...})`, `run_app_with_file(app, file)`.
- Notification bar: `mpos.eval("mpos.ui.topmenu.bar_open")`, height 24px.
- Serial rotation (270°): `press()` auto-transforms coords.

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
- Make UI uniform: buttons in same flex row = same height.

### MicroPython @native / @viper
- `@micropython.viper` is compile-time: `hasattr(micropython, "viper")` returns `False`. Check `hasattr(micropython, "native")`.
- Guard programmatic decorators: `if hasattr(micropython, "native"): micropython.native(func)`.
- Viper: `ba[i]` returns `object` → `int()` cast. int16 sign extension: `v = int(ba[i]) | (int(ba[i+1]) << 8); if v & 0x8000: v -= 65536`.

### ESP32
- `sys.platform` always `'esp32'` (S3, C3, etc.).
- `Pin.init(Pin.OUT)` silently overrides peripheral GPIO routing → no output, no error. Fix: deinit + re-create peripheral.
- Shared RMT pin: re-create RMT driver (not just `pin.init`).

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

## Apps & docs

- Install: `./scripts/install.sh com.micropythonos.appname` then `AppManager.refresh_apps()`.
- Deploy files: `mpremote cp source :/dest/` then `machine.reset()`.
- `self.appFullName` auto-set by ActivityNavigator — use for `SharedPreferences(self.appFullName)`.
- Prefer `mpos.ui.SettingsActivity`/`SettingActivity` over custom dialogs.
- Follow symlinks in `internal_filesystem/apps/` when searching.
- `nostr_service.py` shared between nostr/displaywallet — update both copies.
- Docs: sibling `../docs/`. `mkdocs build` to check. Some `.md` files intentionally excluded from nav (included by other pages) — don't add them.
