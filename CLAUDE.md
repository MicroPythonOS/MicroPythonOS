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
- `SharedPreferences`: Per-app key-value storage (similar to Android) - see [docs/frameworks/preferences.md](../docs/docs/frameworks/preferences.md)

**Hardware Abstraction**:
- `boot.py` configures SPI, I2C, display (ST7789), touchscreen (CST816S), and battery ADC
- Platform detection via `sys.platform` ("esp32" vs others)
- Different boot files per hardware variant (boot_fri3d-2024.py, etc.)

### Webcam Module (Desktop Only)

The `c_mpos/src/webcam.c` module provides webcam support for desktop builds using the V4L2 API.

**Resolution Adaptation**:
- Automatically queries supported YUYV resolutions from the webcam using V4L2 API
- Supports all 23 ESP32 camera resolutions via intelligent cropping/padding
- **Center cropping**: When requesting smaller than available (e.g., 240x240 from 320x240)
- **Black border padding**: When requesting larger than maximum supported
- Always returns exactly the requested dimensions for API consistency

**Behavior**:
- On first init, queries device for supported resolutions using `VIDIOC_ENUM_FRAMESIZES`
- Selects smallest capture resolution ≥ requested dimensions (minimizes memory/bandwidth)
- Converts YUYV to RGB565 (color) or grayscale during capture
- Caches supported resolutions to avoid re-querying device

**Examples**:

*Cropping (common case)*:
- Request: 240x240 (not natively supported)
- Capture: 320x240 (nearest supported YUYV resolution)
- Process: Extract center 240x240 region
- Result: 240x240 frame with centered content

*Padding (rare case)*:
- Request: 1920x1080
- Capture: 1280x720 (webcam maximum)
- Process: Center 1280x720 content in 1920x1080 buffer with black borders
- Result: 1920x1080 frame (API contract maintained)

**Performance**:
- Exact matches use fast path (no cropping overhead)
- Cropped resolutions add ~5-10% CPU overhead
- Padded resolutions add ~3-5% CPU overhead (memset + center placement)
- V4L2 buffers sized for capture resolution, conversion buffers sized for output

**Implementation Details**:
- YUYV format: 2 pixels per macropixel (4 bytes: Y0 U Y1 V)
- Crop offsets must be even for proper YUYV alignment
- Center crop formula: `offset = (capture_dim - output_dim) / 2`, then align to even
- Supported resolutions cached in `supported_resolutions_t` structure
- Separate tracking of `capture_width/height` (from V4L2) vs `output_width/height` (user requested)

**File Location**: `c_mpos/src/webcam.c` (C extension module)

## Build System

### Development Workflow (IMPORTANT)

**For most development, you do NOT need to rebuild the firmware!**

When you run `scripts/install.sh`, it copies files from `internal_filesystem/` to the device storage. These files override the frozen filesystem because the storage paths are first in `sys.path`. This means:

```bash
# Fast development cycle (recommended):
# 1. Edit Python files in internal_filesystem/
# 2. Install to device:
./scripts/install.sh waveshare-esp32-s3-touch-lcd-2

# That's it! Your changes are live on the device.
```

**You only need to rebuild firmware (`./scripts/build_mpos.sh esp32`) when:**
- Testing the frozen `lib/` for production releases
- Modifying C extension modules (`c_mpos/`, `secp256k1-embedded-ecdh/`)
- Changing MicroPython core or LVGL bindings
- Creating a fresh firmware image for distribution

**Desktop development** always uses the unfrozen files, so you never need to rebuild for Python changes:
```bash
# Edit internal_filesystem/ files
./scripts/run_desktop.sh  # Changes are immediately active
```

### Building Firmware

The main build script is `scripts/build_mpos.sh`:

```bash
# Build for desktop (Linux)
./scripts/build_mpos.sh unix

# Build for desktop (macOS)
./scripts/build_mpos.sh macOS

# Build for ESP32-S3 hardware (works on both waveshare and fri3d variants)
./scripts/build_mpos.sh esp32
```

**Targets**:
- `esp32`: ESP32-S3 hardware (supports waveshare-esp32-s3-touch-lcd-2 and fri3d-2024)
- `unix`: Linux desktop
- `macOS`: macOS desktop

**Note**: The build system automatically includes the frozen filesystem with all built-in apps and libraries. No separate dev/prod distinction exists anymore.

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
./tests/unittest.sh tests/test_graphical_start_app.py

# Run a specific test on connected device (via mpremote)
./tests/unittest.sh tests/test_shared_preferences.py --ondevice

# Run all tests on connected device
./tests/unittest.sh --ondevice
```

The `unittest.sh` script:
- Automatically detects the platform (Linux/macOS) and uses the correct binary
- Sets up the proper paths and heapsize
- Can run tests on device using `mpremote` with the `--ondevice` flag
- Runs all `test_*.py` files when no argument is provided
- On device, assumes the OS is already running (boot.py and main.py already executed), so tests run against the live system
- Test infrastructure (graphical_test_helper.py) is automatically installed by `scripts/install.sh`

**Available unit test modules**:
- `test_shared_preferences.py`: Tests for `mpos.config.SharedPreferences` (configuration storage)
- `test_intent.py`: Tests for `mpos.content.intent.Intent` (intent creation, extras, flags)
- `test_package_manager.py`: Tests for `PackageManager` (version comparison, app discovery)
- `test_graphical_start_app.py`: Tests for app launching (graphical test with proper boot/main initialization)
- `test_graphical_about_app.py`: Graphical test that verifies About app UI and captures screenshots

**Graphical tests** (UI verification with screenshots):
```bash
# Run graphical tests on desktop
./tests/unittest.sh tests/test_graphical_about_app.py

# Run graphical tests on device
./tests/unittest.sh tests/test_graphical_about_app.py --ondevice

# Convert screenshots from raw RGB565 to PNG
cd tests/screenshots
./convert_to_png.sh  # Converts all .raw files in the directory
```

Graphical tests use `tests/graphical_test_helper.py` which provides utilities like:
- `wait_for_render()`: Wait for LVGL to process UI events
- `capture_screenshot()`: Take screenshot as RGB565 raw data
- `find_label_with_text()`: Find labels containing specific text
- `verify_text_present()`: Verify expected text is on screen

Screenshots are saved as `.raw` files (RGB565 format) and can be converted to PNG using `tests/screenshots/convert_to_png.sh`

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
- **IMPORTANT**: Do NOT end test files with `if __name__ == '__main__': unittest.main()` - the `./tests/unittest.sh` script handles running tests and capturing exit codes. Including this will interfere with test execution.

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
./scripts/build_mpos.sh unix

# Install filesystem to device (run after code changes)
./scripts/install.sh

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
- Config/preferences: `internal_filesystem/lib/mpos/config.py` - see [docs/frameworks/preferences.md](../docs/docs/frameworks/preferences.md)
- Audio system: `internal_filesystem/lib/mpos/audio/audioflinger.py` - see [docs/frameworks/audioflinger.md](../docs/docs/frameworks/audioflinger.md)
- LED control: `internal_filesystem/lib/mpos/lights.py` - see [docs/frameworks/lights-manager.md](../docs/docs/frameworks/lights-manager.md)
- Sensor management: `internal_filesystem/lib/mpos/sensor_manager.py` - see [docs/frameworks/sensor-manager.md](../docs/docs/frameworks/sensor-manager.md)
- Top menu/drawer: `internal_filesystem/lib/mpos/ui/topmenu.py`
- Activity navigation: `internal_filesystem/lib/mpos/activity_navigator.py`
- IMU drivers: `internal_filesystem/lib/mpos/hardware/drivers/qmi8658.py` and `wsen_isds.py`

## Common Utilities and Helpers

**SharedPreferences**: Persistent key-value storage per app

📖 User Documentation: See [docs/frameworks/preferences.md](../docs/docs/frameworks/preferences.md) for complete guide with constructor defaults, multi-mode patterns, and auto-cleanup behavior.

**Implementation**: `lib/mpos/config.py` - SharedPreferences class with get/put methods for strings, ints, bools, lists, and dicts. Values matching constructor defaults are automatically removed from storage (space optimization).

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

### Keyboard and Focus Navigation

MicroPythonOS supports keyboard/joystick navigation through LVGL's focus group system. This allows users to navigate apps using arrow keys and select items with Enter.

**Basic focus handling pattern**:
```python
def onCreate(self):
    # Get the default focus group
    focusgroup = lv.group_get_default()
    if not focusgroup:
        print("WARNING: could not get default focusgroup")

    # Create a clickable object
    button = lv.button(screen)

    # Add focus/defocus event handlers
    button.add_event_cb(lambda e, b=button: self.focus_handler(b), lv.EVENT.FOCUSED, None)
    button.add_event_cb(lambda e, b=button: self.defocus_handler(b), lv.EVENT.DEFOCUSED, None)

    # Add to focus group (enables keyboard navigation)
    if focusgroup:
        focusgroup.add_obj(button)

def focus_handler(self, obj):
    """Called when object receives focus"""
    obj.set_style_border_color(lv.theme_get_color_primary(None), lv.PART.MAIN)
    obj.set_style_border_width(2, lv.PART.MAIN)
    obj.scroll_to_view(True)  # Scroll into view if needed

def defocus_handler(self, obj):
    """Called when object loses focus"""
    obj.set_style_border_width(0, lv.PART.MAIN)
```

**Key principles**:
- Get the default focus group with `lv.group_get_default()`
- Add objects to the focus group to make them keyboard-navigable
- Use `lv.EVENT.FOCUSED` to highlight focused elements (usually with a border)
- Use `lv.EVENT.DEFOCUSED` to remove highlighting
- Use theme color for consistency: `lv.theme_get_color_primary(None)`
- Call `scroll_to_view(True)` to auto-scroll focused items into view
- The focus group automatically handles arrow key navigation between objects

**Example apps with focus handling**:
- **Launcher** (`builtin/apps/com.micropythonos.launcher/assets/launcher.py`): App icons are focusable
- **Settings** (`builtin/apps/com.micropythonos.settings/assets/settings_app.py`): Settings items are focusable
- **Connect 4** (`apps/com.micropythonos.connect4/assets/connect4.py`): Game columns are focusable

**Other utilities**:
- `mpos.apps.good_stack_size()`: Returns appropriate thread stack size for platform (16KB ESP32, 24KB desktop)
- `mpos.wifi`: WiFi management utilities
- `mpos.sdcard.SDCardManager`: SD card mounting and management
- `mpos.clipboard`: System clipboard access
- `mpos.battery_voltage`: Battery level reading (ESP32 only)
- `mpos.sensor_manager`: Unified sensor access - see [docs/frameworks/sensor-manager.md](../docs/docs/frameworks/sensor-manager.md)
- `mpos.audio.audioflinger`: Audio playback service - see [docs/frameworks/audioflinger.md](../docs/docs/frameworks/audioflinger.md)
- `mpos.lights`: LED control - see [docs/frameworks/lights-manager.md](../docs/docs/frameworks/lights-manager.md)

## Audio System (AudioFlinger)

MicroPythonOS provides a centralized audio service called **AudioFlinger** for managing audio playback.

**📖 User Documentation**: See [docs/frameworks/audioflinger.md](../docs/docs/frameworks/audioflinger.md) for complete API reference, examples, and troubleshooting.

### Implementation Details (for Claude Code)

- **Location**: `lib/mpos/audio/audioflinger.py`
- **Pattern**: Module-level singleton (similar to `battery_voltage.py`)
- **Thread-safe**: Uses locks for concurrent access
- **Hardware abstraction**: Supports I2S (GPIO 2, 47, 16) and Buzzer (GPIO 46 on Fri3d)
- **Audio focus**: 3-tier priority system (ALARM > NOTIFICATION > MUSIC)
- **Configuration**: `data/com.micropythonos.settings/config.json` key: `audio_device`

### Critical Code Locations

- Audio service: `lib/mpos/audio/audioflinger.py`
- I2S implementation: `lib/mpos/audio/i2s_audio.py`
- Buzzer implementation: `lib/mpos/audio/buzzer.py`
- RTTTL parser: `lib/mpos/audio/rtttl.py`
- Board init (Waveshare): `lib/mpos/board/waveshare_esp32_s3_touch_lcd_2.py` (line ~105)
- Board init (Fri3d): `lib/mpos/board/fri3d_2024.py` (line ~300)

## LED Control (LightsManager)

MicroPythonOS provides LED control for NeoPixel RGB LEDs (Fri3d badge only).

**📖 User Documentation**: See [docs/frameworks/lights-manager.md](../docs/docs/frameworks/lights-manager.md) for complete API reference, animation patterns, and examples.

### Implementation Details (for Claude Code)

- **Location**: `lib/mpos/lights.py`
- **Pattern**: Module-level singleton (similar to `battery_voltage.py`)
- **Hardware**: 5 NeoPixel RGB LEDs on GPIO 12 (Fri3d badge only)
- **Buffered**: LED colors buffered until `write()` is called
- **Thread-safe**: No locking (single-threaded usage recommended)
- **Desktop**: Functions return `False` (no-op) on desktop builds

### Critical Code Locations

- LED service: `lib/mpos/lights.py`
- Board init (Fri3d): `lib/mpos/board/fri3d_2024.py` (line ~290)
- NeoPixel dependency: Uses `neopixel` module from MicroPython

## Sensor System (SensorManager)

MicroPythonOS provides a unified sensor framework called **SensorManager** for motion sensors (accelerometer, gyroscope) and temperature sensors.

📖 User Documentation: See [docs/frameworks/sensor-manager.md](../docs/docs/frameworks/sensor-manager.md) for complete API reference, calibration guide, game examples, and troubleshooting.

### Implementation Details (for Claude Code)

- **Location**: `lib/mpos/sensor_manager.py`
- **Pattern**: Module-level singleton (similar to `battery_voltage.py`)
- **Units**: Standard SI (m/s² for acceleration, deg/s for gyroscope, °C for temperature)
- **Calibration**: Persistent via SharedPreferences (`data/com.micropythonos.sensors/config.json`)
- **Thread-safe**: Uses locks for concurrent access
- **Auto-detection**: Identifies IMU type via chip ID registers
  - QMI8658: chip_id=0x05 at reg=0x00
  - WSEN_ISDS: chip_id=0x6A at reg=0x0F
- **Desktop**: Functions return `None` (graceful fallback) on desktop builds
- **Important**: Driver constants defined with `const()` cannot be imported at runtime - SensorManager uses hardcoded values instead

### Critical Code Locations

- Sensor service: `lib/mpos/sensor_manager.py`
- QMI8658 driver: `lib/mpos/hardware/drivers/qmi8658.py`
- WSEN_ISDS driver: `lib/mpos/hardware/drivers/wsen_isds.py`
- Board init (Waveshare): `lib/mpos/board/waveshare_esp32_s3_touch_lcd_2.py` (line ~130)
- Board init (Fri3d): `lib/mpos/board/fri3d_2024.py` (line ~320)
- Board init (Linux): `lib/mpos/board/linux.py` (line ~115)

## Animations and Game Loops

MicroPythonOS supports frame-based animations and game loops using the TaskHandler event system. This pattern is used for games, particle effects, and smooth animations.

### The update_frame() Pattern

The core pattern involves:
1. Registering a callback that fires every frame
2. Calculating delta time for framerate-independent physics
3. Updating object positions and properties
4. Rendering to LVGL objects
5. Unregistering when animation completes

**Basic structure**:
```python
from mpos.apps import Activity
import mpos.ui
import time
import lvgl as lv

class MyAnimatedApp(Activity):
    last_time = 0

    def onCreate(self):
        # Set up your UI
        self.screen = lv.obj()
        # ... create objects ...
        self.setContentView(self.screen)

    def onResume(self, screen):
        # Register the frame callback
        self.last_time = time.ticks_ms()
        mpos.ui.task_handler.add_event_cb(self.update_frame, 1)

    def onPause(self, screen):
        # Unregister when app goes to background
        mpos.ui.task_handler.remove_event_cb(self.update_frame)

    def update_frame(self, a, b):
        # Calculate delta time for framerate independence
        current_time = time.ticks_ms()
        delta_ms = time.ticks_diff(current_time, self.last_time)
        delta_time = delta_ms / 1000.0  # Convert to seconds
        self.last_time = current_time

        # Update your animation/game logic here
        # Use delta_time to make physics framerate-independent
```

### Framerate-Independent Physics

All movement and physics should be multiplied by `delta_time` to ensure consistent behavior regardless of framerate:

```python
# Example from QuasiBird game
GRAVITY = 200  # pixels per second²
PIPE_SPEED = 100  # pixels per second

def update_frame(self, a, b):
    current_time = time.ticks_ms()
    delta_time = time.ticks_diff(current_time, self.last_time) / 1000.0
    self.last_time = current_time

    # Update velocity with gravity
    self.bird_velocity += self.GRAVITY * delta_time

    # Update position with velocity
    self.bird_y += self.bird_velocity * delta_time

    # Update bird sprite position
    self.bird_img.set_y(int(self.bird_y))

    # Move pipes
    for pipe in self.pipes:
        pipe.x -= self.PIPE_SPEED * delta_time
```

**Key principles**:
- Constants define rates in "per second" units (pixels/second, degrees/second)
- Multiply all rates by `delta_time` when applying them
- This ensures objects move at the same speed regardless of framerate
- Use `time.ticks_ms()` and `time.ticks_diff()` for timing (handles rollover correctly)

### Object Pooling for Performance

Pre-create LVGL objects and reuse them instead of creating/destroying during animation:

```python
# Example from LightningPiggy confetti animation
MAX_CONFETTI = 21
confetti_images = []
confetti_pieces = []
used_img_indices = set()

def onStart(self, screen):
    # Pre-create all image objects (hidden initially)
    for i in range(self.MAX_CONFETTI):
        img = lv.image(lv.layer_top())
        img.set_src(f"{self.ASSET_PATH}confetti{i % 5}.png")
        img.add_flag(lv.obj.FLAG.HIDDEN)
        self.confetti_images.append(img)

def _spawn_one(self):
    # Find a free image slot
    for idx, img in enumerate(self.confetti_images):
        if img.has_flag(lv.obj.FLAG.HIDDEN) and idx not in self.used_img_indices:
            break
    else:
        return  # No free slot

    # Create particle data (not LVGL object)
    piece = {
        'img_idx': idx,
        'x': random.uniform(0, self.SCREEN_WIDTH),
        'y': 0,
        'vx': random.uniform(-80, 80),
        'vy': random.uniform(-150, 0),
        'rotation': 0,
        'scale': 1.0,
        'age': 0.0
    }
    self.confetti_pieces.append(piece)
    self.used_img_indices.add(idx)

def update_frame(self, a, b):
    delta_time = time.ticks_diff(time.ticks_ms(), self.last_time) / 1000.0
    self.last_time = time.ticks_ms()

    new_pieces = []
    for piece in self.confetti_pieces:
        # Update physics
        piece['x'] += piece['vx'] * delta_time
        piece['y'] += piece['vy'] * delta_time
        piece['vy'] += self.GRAVITY * delta_time
        piece['rotation'] += piece['spin'] * delta_time
        piece['age'] += delta_time

        # Update LVGL object
        img = self.confetti_images[piece['img_idx']]
        img.remove_flag(lv.obj.FLAG.HIDDEN)
        img.set_pos(int(piece['x']), int(piece['y']))
        img.set_rotation(int(piece['rotation'] * 10))
        img.set_scale(int(256 * piece['scale']))

        # Check if particle should die
        if piece['y'] > self.SCREEN_HEIGHT or piece['age'] > piece['lifetime']:
            img.add_flag(lv.obj.FLAG.HIDDEN)
            self.used_img_indices.discard(piece['img_idx'])
        else:
            new_pieces.append(piece)

    self.confetti_pieces = new_pieces
```

**Object pooling benefits**:
- Avoid memory allocation/deallocation during animation
- Reuse LVGL image objects (expensive to create)
- Hide/show objects instead of create/delete
- Track which slots are in use with a set
- Separate particle data (Python dict) from rendering (LVGL object)

### Particle Systems and Effects

**Staggered spawning** (spawn particles over time instead of all at once):
```python
def start_animation(self):
    self.spawn_timer = 0
    self.spawn_interval = 0.15  # seconds between spawns
    mpos.ui.task_handler.add_event_cb(self.update_frame, 1)

def update_frame(self, a, b):
    delta_time = time.ticks_diff(time.ticks_ms(), self.last_time) / 1000.0

    # Staggered spawning
    self.spawn_timer += delta_time
    if self.spawn_timer >= self.spawn_interval:
        self.spawn_timer = 0
        for _ in range(random.randint(1, 2)):
            if len(self.particles) < self.MAX_PARTICLES:
                self._spawn_one()
```

**Particle lifecycle** (age, scale, death):
```python
piece = {
    'x': x, 'y': y,
    'vx': random.uniform(-80, 80),
    'vy': random.uniform(-150, 0),
    'spin': random.uniform(-500, 500),  # degrees/sec
    'age': 0.0,
    'lifetime': random.uniform(5.0, 10.0),
    'rotation': random.uniform(0, 360),
    'scale': 1.0
}

# In update_frame
piece['age'] += delta_time
piece['scale'] = max(0.3, 1.0 - (piece['age'] / piece['lifetime']) * 0.7)

# Death check
dead = (
    piece['x'] < -60 or piece['x'] > SCREEN_WIDTH + 60 or
    piece['y'] > SCREEN_HEIGHT + 60 or
    piece['age'] > piece['lifetime']
)
```

### Game Loop Patterns

**Scrolling backgrounds** (parallax and tiling):
```python
# Parallax clouds (multiple layers at different speeds)
CLOUD_SPEED = 30  # pixels/sec (slower than foreground)
cloud_positions = [50, 180, 320]

for i, cloud_img in enumerate(self.cloud_images):
    self.cloud_positions[i] -= self.CLOUD_SPEED * delta_time

    # Wrap around when off-screen
    if self.cloud_positions[i] < -60:
        self.cloud_positions[i] = SCREEN_WIDTH + 20

    cloud_img.set_x(int(self.cloud_positions[i]))

# Tiled ground (infinite scrolling)
self.ground_x -= self.PIPE_SPEED * delta_time
self.ground_img.set_offset_x(int(self.ground_x))  # LVGL handles wrapping
```

**Object pooling for game entities**:
```python
# Pre-create pipe images
MAX_PIPES = 4
pipe_images = []

for i in range(MAX_PIPES):
    top_pipe = lv.image(screen)
    top_pipe.set_src("M:path/to/pipe.png")
    top_pipe.set_rotation(1800)  # 180 degrees * 10
    top_pipe.add_flag(lv.obj.FLAG.HIDDEN)

    bottom_pipe = lv.image(screen)
    bottom_pipe.set_src("M:path/to/pipe.png")
    bottom_pipe.add_flag(lv.obj.FLAG.HIDDEN)

    pipe_images.append({"top": top_pipe, "bottom": bottom_pipe, "in_use": False})

# Update visible pipes
def update_pipe_images(self):
    for pipe_img in self.pipe_images:
        pipe_img["in_use"] = False

    for i, pipe in enumerate(self.pipes):
        if i < self.MAX_PIPES:
            pipe_imgs = self.pipe_images[i]
            pipe_imgs["in_use"] = True
            pipe_imgs["top"].remove_flag(lv.obj.FLAG.HIDDEN)
            pipe_imgs["top"].set_pos(int(pipe.x), int(pipe.gap_y - 200))
            pipe_imgs["bottom"].remove_flag(lv.obj.FLAG.HIDDEN)
            pipe_imgs["bottom"].set_pos(int(pipe.x), int(pipe.gap_y + pipe.gap_size))

    # Hide unused slots
    for pipe_img in self.pipe_images:
        if not pipe_img["in_use"]:
            pipe_img["top"].add_flag(lv.obj.FLAG.HIDDEN)
            pipe_img["bottom"].add_flag(lv.obj.FLAG.HIDDEN)
```

**Collision detection**:
```python
def check_collision(self):
    # Boundaries
    if self.bird_y <= 0 or self.bird_y >= SCREEN_HEIGHT - 40 - self.bird_size:
        return True

    # AABB (Axis-Aligned Bounding Box) collision
    bird_left = self.BIRD_X
    bird_right = self.BIRD_X + self.bird_size
    bird_top = self.bird_y
    bird_bottom = self.bird_y + self.bird_size

    for pipe in self.pipes:
        pipe_left = pipe.x
        pipe_right = pipe.x + pipe.width

        # Check horizontal overlap
        if bird_right > pipe_left and bird_left < pipe_right:
            # Check if bird is outside the gap
            if bird_top < pipe.gap_y or bird_bottom > pipe.gap_y + pipe.gap_size:
                return True

    return False
```

### Animation Control and Cleanup

**Starting/stopping animations**:
```python
def start_animation(self):
    self.animation_running = True
    self.last_time = time.ticks_ms()
    mpos.ui.task_handler.add_event_cb(self.update_frame, 1)

    # Optional: auto-stop after duration
    lv.timer_create(self.stop_animation, 15000, None).set_repeat_count(1)

def stop_animation(self, timer=None):
    self.animation_running = False
    # Don't remove callback yet - let it clean up and remove itself

def update_frame(self, a, b):
    # ... update logic ...

    # Stop when animation completes
    if not self.animation_running and len(self.particles) == 0:
        mpos.ui.task_handler.remove_event_cb(self.update_frame)
        print("Animation finished")
```

**Lifecycle integration**:
```python
def onResume(self, screen):
    # Only start if needed (e.g., game in progress)
    if self.game_started and not self.game_over:
        self.last_time = time.ticks_ms()
        mpos.ui.task_handler.add_event_cb(self.update_frame, 1)

def onPause(self, screen):
    # Always stop when app goes to background
    mpos.ui.task_handler.remove_event_cb(self.update_frame)
```

### Performance Tips

1. **Pre-create LVGL objects**: Creating objects during animation causes lag
2. **Use object pools**: Reuse objects instead of create/destroy
3. **Limit particle counts**: Use `MAX_PARTICLES` constant (21 is a good default)
4. **Integer positions**: Convert float positions to int before setting: `img.set_pos(int(x), int(y))`
5. **Delta time**: Always use delta time for framerate independence
6. **Layer management**: Use `lv.layer_top()` for overlays (confetti, popups)
7. **Rotation units**: LVGL rotation is in 1/10 degrees: `set_rotation(int(degrees * 10))`
8. **Scale units**: LVGL scale is 256 = 100%: `set_scale(int(256 * scale_factor))`
9. **Hide vs destroy**: Hide objects with `add_flag(lv.obj.FLAG.HIDDEN)` instead of deleting
10. **Cleanup**: Always unregister callbacks in `onPause()` to prevent memory leaks

### Example Apps

- **QuasiBird** (`MPOS-QuasiBird/assets/quasibird.py`): Full game with physics, scrolling, object pooling
- **LightningPiggy** (`LightningPiggyApp/.../displaywallet.py`): Confetti particle system with staggered spawning
