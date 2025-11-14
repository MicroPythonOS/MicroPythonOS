# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MicroPythonOS is an embedded operating system that runs on ESP32 hardware (particularly the Waveshare ESP32-S3-Touch-LCD-2) and desktop Linux/macOS. It provides an LVGL-based UI framework with an Android-inspired app architecture featuring Activities, Intents, and a PackageManager.

The OS supports:
- Touch and non-touch input devices (keyboard/joystick navigation)
- Camera with QR decoding (using quirc)
- WiFi connectivity
- Over-the-air (OTA) firmware updates
- App installation via MPK packages
- Bitcoin Lightning and Nostr protocols

## Repository Structure

### Core Directories

- `internal_filesystem/`: The runtime filesystem containing the OS and apps
  - `boot.py`: Hardware initialization for ESP32-S3-Touch-LCD-2
  - `boot_unix.py`: Desktop-specific boot initialization
  - `main.py`: UI initialization, theme setup, and launcher start
  - `lib/mpos/`: Core OS library (apps, config, UI, content management)
  - `apps/`: User-installed apps (symlinks to external app repos)
  - `builtin/`: System apps frozen into the firmware (launcher, appstore, settings, etc.)
  - `data/`: Static data files
  - `sdcard/`: SD card mount point

- `lvgl_micropython/`: Submodule containing LVGL bindings for MicroPython
- `micropython-camera-API/`: Submodule for camera support
- `micropython-nostr/`: Submodule for Nostr protocol
- `c_mpos/`: C extension modules (includes quirc for QR decoding)
- `secp256k1-embedded-ecdh/`: Submodule for cryptographic operations
- `manifests/`: Build manifests defining what gets frozen into firmware
- `freezeFS/`: Files to be frozen into the built-in filesystem
- `scripts/`: Build and deployment scripts
- `tests/`: Test suite (both unit tests and manual tests)

### Key Architecture Components

**App System**: Similar to Android
- Apps are identified by reverse-domain names (e.g., `com.micropythonos.camera`)
- Each app has a `META-INF/MANIFEST.JSON` with metadata and activity definitions
- Activities extend `mpos.app.activity.Activity` class (import: `from mpos.app.activity import Activity`)
- Apps implement `onCreate()` to set up their UI and `onDestroy()` for cleanup
- Activity lifecycle: `onCreate()` → `onStart()` → `onResume()` → `onPause()` → `onStop()` → `onDestroy()`
- Apps are packaged as `.mpk` files (zip archives)
- Built-in system apps (frozen into firmware): launcher, appstore, settings, wifi, osupdate, about

**UI Framework**: Built on LVGL 9.3.0
- `mpos.ui.topmenu`: Notification bar and drawer (top menu)
- `mpos.ui.display`: Root screen initialization
- Gesture support: left-edge swipe for back, top-edge swipe for menu
- Theme system with configurable colors and light/dark modes
- Focus groups for keyboard/joystick navigation

**Content Management**:
- `PackageManager`: Install/uninstall/query apps
- `Intent`: Launch activities with action/category filters
- `SharedPreferences`: Per-app key-value storage (similar to Android)

**Hardware Abstraction**:
- `boot.py` configures SPI, I2C, display (ST7789), touchscreen (CST816S), and battery ADC
- Platform detection via `sys.platform` ("esp32" vs others)
- Different boot files per hardware variant (boot_fri3d-2024.py, etc.)

## Build System

### Building Firmware

The main build script is `scripts/build_mpos.sh`:

```bash
# Development build (no frozen filesystem, requires ./scripts/install.sh after flashing)
./scripts/build_mpos.sh unix dev

# Production build (with frozen filesystem)
./scripts/build_mpos.sh unix prod

# ESP32 builds (specify hardware variant)
./scripts/build_mpos.sh esp32 dev waveshare-esp32-s3-touch-lcd-2
./scripts/build_mpos.sh esp32 prod fri3d-2024
```

**Build types**:
- `dev`: No preinstalled files or builtin filesystem. Boots to black screen until you run `./scripts/install.sh`
- `prod`: Files from `manifest*.py` are frozen into firmware. Run `./scripts/freezefs_mount_builtin.sh` before building

**Targets**:
- `esp32`: ESP32-S3 hardware (requires subtarget: `waveshare-esp32-s3-touch-lcd-2` or `fri3d-2024`)
- `unix`: Linux desktop
- `macOS`: macOS desktop

The build system uses `lvgl_micropython/make.py` which wraps MicroPython's build system. It:
1. Fetches SDL tags for desktop builds
2. Patches manifests to include camera and asyncio support
3. Creates symlinks for C modules (secp256k1, c_mpos)
4. Runs the lvgl_micropython build with appropriate flags

**ESP32 build configuration**:
- Board: `ESP32_GENERIC_S3` with `SPIRAM_OCT` variant
- Display driver: `st7789`
- Input device: `cst816s`
- OTA enabled with 4MB partition size (16MB total flash)
- Dual-core threading enabled (no GIL)
- User C modules: camera, secp256k1, c_mpos/quirc

**Desktop build configuration**:
- Display: `sdl_display`
- Input: `sdl_pointer`, `sdl_keyboard`
- Compiler flags: `-g -O0 -ggdb -ljpeg` (debug symbols enabled)
- STRIP is disabled to keep debug symbols

### Building and Bundling Apps

Apps can be bundled into `.mpk` files:
```bash
./scripts/bundle_apps.sh
```

### Running on Desktop

```bash
# Run normally (starts launcher)
./scripts/run_desktop.sh

# Run a specific Python script directly
./scripts/run_desktop.sh path/to/script.py

# Run a specific app by name
./scripts/run_desktop.sh com.micropythonos.camera
```

**Important environment variables**:
- `HEAPSIZE`: Set heap size (default 8M, matches ESP32-S3 PSRAM). Increase for memory-intensive apps
- `SDL_WINDOW_FULLSCREEN`: Set to `true` for fullscreen mode

The script automatically selects the correct binary (`lvgl_micropy_unix` or `lvgl_micropy_macOS`) and runs from the `internal_filesystem/` directory.

## Deploying to Hardware

### Flashing Firmware

```bash
# Flash firmware over USB
./scripts/flash_over_usb.sh
```

### Installing Files to Device

```bash
# Install all files to device (boot.py, main.py, lib/, apps/, builtin/)
./scripts/install.sh waveshare-esp32-s3-touch-lcd-2

# Install a single app to device
./scripts/install.sh waveshare-esp32-s3-touch-lcd-2 camera
```

Uses `mpremote` from MicroPython tools to copy files over serial connection.

## Testing

### Running Tests

Tests are in the `tests/` directory. There are two types: unit tests and manual tests.

**Unit tests** (automated, run on desktop or device):
```bash
# Run all unit tests on desktop
./tests/unittest.sh

# Run a specific test file on desktop
./tests/unittest.sh tests/test_shared_preferences.py
./tests/unittest.sh tests/test_intent.py
./tests/unittest.sh tests/test_package_manager.py
./tests/unittest.sh tests/test_start_app.py

# Run a specific test on connected device (via mpremote)
./tests/unittest.sh tests/test_shared_preferences.py ondevice
```

The `unittest.sh` script:
- Automatically detects the platform (Linux/macOS) and uses the correct binary
- Sets up the proper paths and heapsize
- Can run tests on device using `mpremote` with the `ondevice` argument
- Runs all `test_*.py` files when no argument is provided

**Available unit test modules**:
- `test_shared_preferences.py`: Tests for `mpos.config.SharedPreferences` (configuration storage)
- `test_intent.py`: Tests for `mpos.content.intent.Intent` (intent creation, extras, flags)
- `test_package_manager.py`: Tests for `PackageManager` (version comparison, app discovery)
- `test_start_app.py`: Tests for app launching (requires SDL display initialization)

**Manual tests** (interactive, for hardware-specific features):
- `manual_test_camera.py`: Camera and QR scanning
- `manual_test_nostr_asyncio.py`: Nostr protocol
- `manual_test_nwcwallet*.py`: Lightning wallet connectivity (Alby, Cashu)
- `manual_test_lnbitswallet.py`: LNbits wallet integration
- `test_websocket.py`: WebSocket functionality
- `test_multi_connect.py`: Multiple concurrent connections

Run manual tests with:
```bash
./scripts/run_desktop.sh tests/manual_test_camera.py
```

### Writing New Tests

**Unit test guidelines**:
- Use Python's `unittest` module (compatible with MicroPython)
- Place tests in `tests/` directory with `test_*.py` naming
- Use `setUp()` and `tearDown()` for test fixtures
- Clean up any created files/directories in `tearDown()`
- Tests should be runnable on desktop (unix build) without hardware dependencies
- Use descriptive test names: `test_<what_is_being_tested>`
- Group related tests in test classes

**Example test structure**:
```python
import unittest
from mpos.some_module import SomeClass

class TestSomeClass(unittest.TestCase):
    def setUp(self):
        # Initialize test fixtures
        pass

    def tearDown(self):
        # Clean up after test
        pass

    def test_some_functionality(self):
        # Arrange
        obj = SomeClass()
        # Act
        result = obj.some_method()
        # Assert
        self.assertEqual(result, expected_value)
```

## Development Workflow

### Creating a New App

1. Create app directory: `internal_filesystem/apps/com.example.myapp/`
2. Create `META-INF/MANIFEST.JSON` with app metadata and activities
3. Create `assets/` directory for Python code
4. Create main activity file extending `Activity` class
5. Implement `onCreate()` method to build UI
6. Optional: Create `res/` directory for resources (icons, images)

**Minimal app structure**:
```
com.example.myapp/
├── META-INF/
│   └── MANIFEST.JSON
├── assets/
│   └── main_activity.py
└── res/
    └── mipmap-mdpi/
        └── icon_64x64.png
```

**Minimal Activity code**:
```python
from mpos.app.activity import Activity
import lvgl as lv

class MainActivity(Activity):
    def onCreate(self):
        screen = lv.obj()
        label = lv.label(screen)
        label.set_text('Hello World!')
        label.center()
        self.setContentView(screen)
```

See `internal_filesystem/apps/com.micropythonos.helloworld/` for a minimal example and built-in apps in `internal_filesystem/builtin/apps/` for more complex examples.

### Testing App Changes

For rapid iteration on desktop:
```bash
# Build desktop version (only needed once)
./scripts/build_mpos.sh unix dev

# Install filesystem to device (run after code changes)
./scripts/install.sh waveshare-esp32-s3-touch-lcd-2

# Or run directly on desktop
./scripts/run_desktop.sh com.example.myapp
```

### Debugging

Desktop builds include debug symbols by default. Use GDB:
```bash
gdb --args ./lvgl_micropython/build/lvgl_micropy_unix -X heapsize=8M -v -i -c "$(cat boot_unix.py main.py)"
```

For ESP32 debugging, enable core dumps:
```bash
./scripts/core_dump_activate.sh
```

## Important Constraints

### Memory Management

ESP32-S3 has 8MB PSRAM. Memory-intensive operations:
- Camera images consume ~2.5MB per frame
- LVGL image cache must be managed with `lv.image.cache_drop(None)`
- Large UI components should be created/destroyed rather than hidden
- Use `gc.collect()` strategically after deallocating large objects

### Threading

- Main UI/LVGL operations must run on main thread
- Background tasks use `_thread.start_new_thread()`
- Stack size: 16KB for ESP32, 24KB for desktop (see `mpos.apps.good_stack_size()`)
- Use `mpos.ui.async_call()` to safely invoke UI operations from background threads

### Async Operations

- OS uses `uasyncio` for networking (WebSockets, HTTP, Nostr)
- WebSocket library is custom `websocket.py` using uasyncio
- HTTP uses `aiohttp` package (in `lib/aiohttp/`)
- Async tasks are throttled per frame to prevent memory overflow

### File Paths

- Use `M:/path/to/file` prefix for LVGL file operations (registered in main.py)
- Absolute paths for Python imports
- Apps run with their directory added to `sys.path`

## Build Dependencies

The build requires all git submodules checked out recursively:
```bash
git submodule update --init --recursive
```

**Desktop dependencies**: See `.github/workflows/build.yml` for full list including:
- SDL2 development libraries
- Mesa/EGL libraries
- libjpeg
- Python 3.8+
- cmake, ninja-build

## Manifest System

Manifests define what gets frozen into firmware:
- `manifests/manifest.py`: ESP32 production builds
- `manifests/manifest_fri3d-2024.py`: Fri3d Camp 2024 Badge variant
- `manifests/manifest_unix.py`: Desktop builds

Manifests use `freeze()` directives to include files in the frozen filesystem. Frozen files are baked into the firmware and cannot be modified at runtime.

## Version Management

Versions are tracked in:
- `CHANGELOG.md`: User-facing changelog with release history
- App versions in `META-INF/MANIFEST.JSON` files
- OS update system checks `hardware_id` from `mpos.info.get_hardware_id()`

Current stable version: 0.3.3 (as of latest CHANGELOG entry)

## Critical Code Locations

- App lifecycle: `internal_filesystem/lib/mpos/apps.py:execute_script()`
- Activity base class: `internal_filesystem/lib/mpos/app/activity.py`
- Package management: `internal_filesystem/lib/mpos/content/package_manager.py`
- Intent system: `internal_filesystem/lib/mpos/content/intent.py`
- UI initialization: `internal_filesystem/main.py`
- Hardware init: `internal_filesystem/boot.py`
- Config/preferences: `internal_filesystem/lib/mpos/config.py`
- Top menu/drawer: `internal_filesystem/lib/mpos/ui/topmenu.py`
- Activity navigation: `internal_filesystem/lib/mpos/activity_navigator.py`

## Common Utilities and Helpers

**SharedPreferences**: Persistent key-value storage per app
```python
from mpos.config import SharedPreferences

# Load preferences
prefs = SharedPreferences("com.example.myapp")
value = prefs.get_string("key", "default_value")
number = prefs.get_int("count", 0)
data = prefs.get_dict("data", {})

# Save preferences
editor = prefs.edit()
editor.put_string("key", "value")
editor.put_int("count", 42)
editor.put_dict("data", {"key": "value"})
editor.commit()
```

**Intent system**: Launch activities and pass data
```python
from mpos.content.intent import Intent

# Launch activity by name
intent = Intent()
intent.setClassName("com.micropythonos.camera", "Camera")
self.startActivity(intent)

# Launch with extras
intent.putExtra("key", "value")
self.startActivityForResult(intent, self.handle_result)

def handle_result(self, result):
    if result["result_code"] == Activity.RESULT_OK:
        data = result["data"]
```

**UI utilities**:
- `mpos.ui.async_call(func, *args, **kwargs)`: Safely call UI operations from background threads
- `mpos.ui.back_screen()`: Navigate back to previous screen
- `mpos.ui.focus_direction`: Keyboard/joystick navigation helpers
- `mpos.ui.anim`: Animation utilities

**Other utilities**:
- `mpos.apps.good_stack_size()`: Returns appropriate thread stack size for platform (16KB ESP32, 24KB desktop)
- `mpos.wifi`: WiFi management utilities
- `mpos.sdcard.SDCardManager`: SD card mounting and management
- `mpos.clipboard`: System clipboard access
- `mpos.battery_voltage`: Battery level reading (ESP32 only)
