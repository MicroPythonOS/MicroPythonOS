# Coding Conventions

*Last updated: 2026-06-25*

## Style

- **Formatter**: `ruff` with `quote-style = "double"` (`ruff.toml`).
- Line length: 120.
- Currently linting only `F401` (unused imports); broader `E` / `I` rules are commented out.
- `E701` (compound statements) is intentionally ignored because debug logging uses `if __debug__: logger.debug(...)` one-liners.
- Prefer double quotes for strings.

## Logging

- Per-file logger: `import logging; logger = logging.getLogger(__name__)`.
- Debug logs must be guarded with `if __debug__:` so `mpy-cross -O3` strips them entirely.
  - Correct: `if __debug__: logger.debug("fmt %s", var)`
  - Avoid debug `logger.debug` without the guard; avoid `logger.error`/`warning`/`critical` with the guard.
- Use `%s` formatting for lazy evaluation: `logger.error("msg: %s", e)`.
  - **Critical MicroPython pitfall**: `logger.error("msg: ", e)` raises `TypeError` because the format string lacks a `%s`.

## LVGL Conventions

MicroPythonOS uses LVGL 9.x naming:

- `import lvgl as lv`.
- `lv.screen_active()` instead of `lv.scr_act()`.
- Use `button`, `image`, `label` instead of `btn`, `img`, `lbl`.
- Use `lv.EVENT.VALUE_CHANGED`, `lv.obj.FLAG.CLICKABLE`, `lv.buttonmatrix.CTRL.CHECKABLE`, `lv.PALETTE.RED`, etc.
- Hide/show with `.add_flag(lv.obj.FLAG.HIDDEN)` / `.remove_flag(lv.obj.FLAG.HIDDEN)`.
- Scrollbar hiding: `obj.remove_flag(lv.obj.FLAG.SCROLLABLE)` because `set_style_scrollbar_mode()` is not available.
- Styles: `style = lv.style_t(); style.init(); style.set_bg_color(...)`.
- Event callbacks: 3 args (target, event); the wrapper is `callback(self, event)` for methods.
- Widgets do not allow arbitrary attribute assignment; use closures/lambdas or parallel lists.

## UI Sizing

- Avoid hardcoding pixel values greater than 5.
- Use `DisplayMetrics` (`from mpos import DisplayMetrics`) for responsive sizing:
  - `DisplayMetrics.pct_of_width(percent)`
  - `DisplayMetrics.pct_of_height(percent)`
  - `DisplayMetrics.width()`, `DisplayMetrics.height()`

## Threading & Async

- Apps should **not** import `asyncio` directly; route through `mpos.TaskManager`.
- UI updates from a background thread must use `lv.async_call()` or `Activity.update_ui_threadsafe_if_foreground()`.
- Secondary-thread tight loops should yield with `time.sleep_ms(1)`; `time.sleep_us()` busy-waits.

## Error Handling

- Lifecycle exceptions are wrapped by `ui/errordialog.py`.
- Broad `except Exception: pass` is heavily discouraged; it hides hardware/peripheral failures and makes debugging hard.
- Board detection catches hardware probe failures explicitly and returns `None` rather than crashing.

## MicroPython Compatibility

- No `bytearray * int`; loop-extend instead.
- `random` module may lack `Random` / `shuffle`; use a Fisher-Yates loop with `random.randint`.
- `sys.platform` on ESP32 variants is always `"esp32"` (not `"esp32s3"`).
- Prefer `machine.reset()` over soft reset.
- `unittest` lacks `assertGreater`/`assertLess`/etc.; use `assertTrue(a > b, msg)`.

## Imports

- Lazy imports are common to avoid circular dependencies, e.g. `mpos.ui` imported inside methods.
- `internal_filesystem/lib/mpos/__init__.py` exposes a curated public API.
- `from mpos import X` is the preferred way to access framework classes.
