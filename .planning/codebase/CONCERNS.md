# Concerns & Technical Debt

*Last updated: 2026-06-25*

## Build Fragility

- `scripts/build_mpos.sh` mutates tracked files in submodules:
  - Appends `esp32-camera` and `adc_mic` lines to `lvgl_micropython/lib/micropython/ports/esp32/main/idf_component.yml`.
  - Appends an `include(...)` line to `micropython-camera-API/src/manifest.py`.
  - Applies patches to `lvgl_micropython/lib/micropython` and `lvgl_micropython/lib/lvgl`.
  - On `unix`/`macOS` it disables `@micropython.native`/`@micropython.viper` decorators by rewriting Python files.
  - Expects these edits to persist unless the user reverts them manually.
- Unix/macOS builds depend on symlinks created under `lvgl_micropython/ext_mod/` (`c_mpos`, `secp256k1-embedded-ecdh`) because `USER_C_MODULE` is unreliable on desktop.

## Silent Hardware Failures

- Several board-detection and driver paths catch exceptions and return silently. Broad `except Exception: pass` patterns can mask GPIO-matrix routing failures.
- ESP32 GPIO matrix caveat: calling `Pin.init(Pin.OUT)` after peripheral setup (RMT, SPI, I2C) disconnects the peripheral with no error. Recovery requires deinit/re-create of the peripheral driver.
- Shared RMT + ADC pins on Fri3d 2024 badge require RMT driver recreation after ADC use.

## Known Code Issues

From TODO/FIXME markers in the source:

- `internal_filesystem/lib/mpos/audio/stream_record_adc.py:62` — ADC unit/channel passing needs cleanup.
- `internal_filesystem/lib/mpos/board/m5stack_core2.py:157` — startup sound requires WAV instead of RTTTL.
- `internal_filesystem/lib/mpos/board/freenove_esp32s3_display.py:200` — should switch to `adc.read_uv()`.
- `internal_filesystem/lib/mpos/board/unphone.py` — two backlights, persistent store, storage API, and calibration issues.
- `internal_filesystem/apps/cz.ucw.pavel.weather/main.py:80` — precipitation display missing.
- `internal_filesystem/apps/cz.ucw.pavel.calendar/main.py` — multiple FIXMEs around editing and saving events.
- `internal_filesystem/builtin/apps/com.micropythonos.appstore/assets/app_detail.py:360` — install reporting endpoint disabled.
- `internal_filesystem/builtin/apps/com.micropythonos.settings/assets/settings.py:98` — uses direct dict instead of `should_show` helper.

## Async / Concurrency Debt

- `TaskManager` keeps a `task_list` that is never pruned of completed tasks; long-running devices may leak memory.
- The asyncio loop comment says `lv.timer_handler` is not called explicitly because "everything seems to work fine without it" — this is a hidden dependency on lvgl_micropython's task handling.
- `TaskManager.start()` does not return; code after it in `mpos.main` is effectively unreachable unless it raises.

## UI / LVGL Debt

- LVGL timers: `set_repeat_count(0)` on `lv.timer_create()` creates a one-shot auto-delete timer, but calling `.delete()` afterward double-frees.
- `lv.buttonmatrix.set_map()` fires `VALUE_CHANGED` asynchronously; apps must debounce with time checks.
- `topmenu.bar_open` is a global flag; the notification bar may be absent depending on runtime state.
- Many existing apps still contain legacy LVGL 8.x patterns that have been migrated but may have stragglers.

## Test Coverage

- `ruff.toml` currently excludes `tests/` from lint because of too many errors.
- 88 test files exist; the project is rich in graphical tests but lacks an aggregated coverage metric.
- On-device tests require manual serial connection and a 30-second reset per retry, making CI difficult.

## Security

- The codebase embeds user-facing crypto via `secp256k1-embedded-ecdh` and `micropython-nostr`. Private-key handling is in app code; review any new Nostr/crypto apps carefully.
- WebREPL exposes a remote REPL over HTTP/WebSocket; device deployments should consider transport security.
- Generated codebase documents were scanned for common secret patterns before this commit.

## Performance

- Full `lvgl_micropython` rebuild is required for most framework changes because `internal_filesystem/lib/mpos` is frozen.
- Desktop emulator startup time and serial screenshot capture (~40 s over USB) slow the debug/test loop.
- Native decorators disabled on desktop mean unit tests do not exercise viper/native code paths.

## Soft Reset

- Soft reset is broken in lvgl_micropython / MicroPythonOS. Use `machine.reset()`; remember that `sys.exit` in tests is used instead of relying on clean shutdown.
