# Testing

*Last updated: 2026-06-25*

## Test Runner

- `tests/unittest.sh [test_file.py] [--ondevice]` — main test runner.
- `tests/syntax.sh` — compiles every `internal_filesystem/**/*.py` with `mpy-cross`.
- Make targets: `make syntax-tests`, `make unittest-tests`, `make tests`.

## Test Flavors

| Type | Filename pattern | Runner behavior |
|------|-----------------|-----------------|
| Unit tests | `tests/test_*.py` | Runs without boot/main; `TaskManager` is disabled. |
| Graphical tests | `tests/test_graphical_*.py` | Injects `main.py` and boot files before running; LVGL is initialized. |
| Manual tests | `tests/manual_test_*.py` | Not run automatically. |
| Host controller tests | `tests/cpython_mpos_controller.py` | Run directly with CPython (`python3 tests/cpython_mpos_controller.py`); not part of `unittest.sh`. |

## Desktop Test Runtime

- `lvgl_micropython/build/lvgl_micropy_unix` (Linux) or `lvgl_micropy_macOS` (macOS).
- Default heap size: 32 MB (`heapsize=32M`).
- Tests receive `import mpos; mpos.TaskManager.disable()` so the asyncio loop does not block the runner.

## On-Device Test Runtime

- Tests are sent to a connected device via `mpremote`.
- The runner does **not** re-run boot/main because the OS is already running.
- `--ondevice` resets the device once to avoid stale unittest classes.

## Test Utilities

### Mocks

`internal_filesystem/lib/mpos/testing/mocks.py` provides:

- `MockMachine`, `MockPin`, `MockPWM`, `MockI2S`, `MockTimer`, `MockNeoPixel`
- `MockNetwork`, `MockRequests`, `MockResponse`, `MockSocket`
- `MockTaskManager`, `MockDownloadManager`
- `MockTime`, `MockJSON`
- `inject_mocks()`, `create_mock_module()`

### LVGL Testing Helpers

`internal_filesystem/lib/mpos/ui/testing.py` provides:

- `GraphicalTestCase` — automatic screen setup/teardown, text assertions.
- `KeyboardTestCase` — helper for on-screen keyboard tests.
- `wait_for_render(iterations=10)` — pump LVGL.
- `simulate_click(x, y)`, `simulate_drag(...)` — simulated touch.
- `click_button(text)`, `click_label(text)` — find and trigger widgets.
- `find_label_with_text(...)`, `verify_text_present(...)` — text assertions.
- `capture_screenshot(path, ...)` — raw pixel buffer capture.
- `get_screen_widget_tree()` — dump full widget tree with states and flags.

### MPOS Controller

`scripts/mpos_controller.py` is a host-side controller for interactive and automated testing:

- `MPOSController(backend="process")` for desktop.
- `MPOSController(backend="serial", port="/dev/ttyACM0")` for device.
- Methods: `start()`, `startapp()`, `run_app_with_file()`, `exec()`, `eval()`, `screenshot()`, `press()`, `click_button()`, `get_widget_tree()`, `get_visible_text()`, `read_file()`, `write_file()`, etc.
- See `AGENTS.md` for detailed usage and caveats.

## Writing New Tests

- Extend `GraphicalTestCase` for UI tests; extend `KeyboardTestCase` for keyboard tests.
- Add mocks via `inject_mocks()` before importing modules that depend on hardware.
- Do not include `if __name__ == "__main__": unittest.main()`; the runner handles execution.
- Use descriptive names: `test_keyboard_q_button_works` not `test_1`.

## Lint

- `make lint` runs `ruff check .`.
- Submodules and `tests/` are excluded from lint per `ruff.toml`.
