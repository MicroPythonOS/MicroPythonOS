# MicroPythonOS Testing Guide

This directory contains the test suite for MicroPythonOS. Tests can run on both desktop (for fast iteration) and on-device (for hardware verification).

## How to Run Tests

```bash
# Run all tests on desktop
python3 scripts/test_runner.py

# Run a single test on desktop
python3 scripts/test_runner.py tests/test_adpcm_ima.py

# Run a single test on device
python3 scripts/test_runner.py tests/test_adpcm_ima.py --ondevice

# Run on device with custom port
python3 scripts/test_runner.py tests/test_adpcm_ima.py --ondevice --port /dev/pts/5

# MPOS_TEST_PORT env var sets default serial port
```

## Test Architecture

### Directory Structure

```
tests/
├── screenshots/             # Captured screenshots for visual regression
├── test_*.py               # Test files
└── README.md               # This file
```

### Testing Modules

MicroPythonOS provides two testing modules:

1. **`mpos.testing`** - Hardware and system mocks
   - Location: `internal_filesystem/lib/mpos/testing/`
   - Use for: Mocking hardware (Pin, PWM, I2S, NeoPixel), network, async operations
   
2. **`mpos.ui.testing`** - LVGL/UI testing utilities
   - Location: `internal_filesystem/lib/mpos/ui/testing.py`
   - Use for: UI interaction, screenshots, widget inspection

## Graphical Test Utilities

Graphical tests should use the helpers in `mpos.ui.testing` instead of ad hoc LVGL traversal.

### GraphicalTestCase

Base class for graphical (LVGL) tests. Provides:
- Automatic screen creation/cleanup
- Widget finding utilities
- Custom assertions

```python
from mpos.ui.testing import GraphicalTestCase
import lvgl as lv

class TestMyUI(GraphicalTestCase):
    def test_something(self):
        label = lv.label(self.screen)
        label.set_text("Hello")

        self.wait_for_render()
        self.assertTextPresent("Hello")
```

**Key Methods:**
- `wait_for_render(iterations=5)` - Process LVGL tasks
- `find_label_with_text(text)` - Find label widget
- `click_button(text)` - Click a button by label text
- `assertTextPresent(text)` - Assert text is on screen

### KeyboardTestCase

Extends GraphicalTestCase for keyboard tests. Provides:
- Keyboard and textarea creation
- Reliable keyboard button clicking
- Textarea assertions

```python
from mpos.ui.testing import KeyboardTestCase

class TestMyKeyboard(KeyboardTestCase):
    def test_typing(self):
        self.create_keyboard_scene()

        self.click_keyboard_button("h")
        self.click_keyboard_button("i")

        self.assertTextareaText("hi")
```

**Key Methods:**
- `create_keyboard_scene()` - Create textarea + MposKeyboard
- `click_keyboard_button(text)` - Click keyboard button reliably
- `type_text(text)` - Type a string
- `get_textarea_text()` - Get textarea content
- `clear_textarea()` - Clear textarea
- `assertTextareaText(expected)` - Assert textarea content
- `assertTextareaEmpty()` - Assert textarea is empty

## Camera-based screen verification

`scripts/mpos_screen_camera.py` compares what a host webcam sees with the
device's own framebuffer (`MPOSController.screenshot()`). Frames are aligned
with SIFT + RANSAC, so rotation, scale and perspective do not matter, and the
tool reports structural similarity (NCC), focus/sharpness and per-icon-cell
likeness. It can also gate pass/fail against thresholds.

Host requirements: `ffmpeg`, `v4l-utils` (`v4l2-ctl`), `numpy` and
`opencv-python-headless`.

```bash
# list cameras, find and lock the sharpest manual focus, then verify the screen
python3 scripts/mpos_screen_camera.py list
python3 scripts/mpos_screen_camera.py focus-sweep --port /dev/ttyACM0 --start 30 --stop 55 --step 5
python3 scripts/mpos_screen_camera.py verify --port /dev/ttyACM0 --out-dir tmp/camtests
```

Artifacts (raw frame, deskewed screen, device-vs-camera comparison, edge maps
and `metrics.jsonl`) go to `--out-dir` (default `tmp/camtests`). The same
features are available from Python via `MPOSController.screen_camera_frame()`,
`.screen_camera_measure()`, `.screen_camera_verify()` and
`.screen_camera_focus_sweep()`.

The framebuffer reference is read from the device and cached by its SHA-1 under
`~/.cache/mpos_screen_camera`, because a full frame can take minutes over
USB-CDC on some hosts. To work from a saved image instead:

```bash
python3 scripts/mpos_screen_camera.py capture-reference --port /dev/ttyACM0 --out tmp/camtests/reference.png
python3 scripts/mpos_screen_camera.py verify --port /dev/ttyACM0 --reference tmp/camtests/reference.png
```

The synthetic tests need no hardware and are skipped when numpy/opencv are
missing:

```bash
python3 tests/cpython_screen_camera.py
```

The release-validation flow (`scripts/validate_ota_release.py`) uses the same
camera checkpoints to prove a previous release can install the new one through
the notification → OSUpdate path. Its hardware-free helper tests are:

```bash
python3 tests/cpython_validate_ota_release.py
```

See `../docs/docs/other/ota-release-validation.md` for the full procedure.

## MP3 playback

MP3 decoding is done by the `mp3dec` native module (`c_mpos/src/mp3dec.c`,
wrapping the public-domain minimp3 decoder in `c_mpos/minimp3/`). The Python
side lives in `mpos/audio/mp3.py` (header parsing plus whole-file decode
helpers) and `mpos/audio/stream_mp3.py` (the playback stream).

`tests/data/mp3/` holds five short tone renders (0.25 s silence, then A4/A5/A6
at 440/880/1760 Hz) covering MPEG-1/2/2.5, CBR and VBR (Xing), mono and
stereo, and 8/22.05/44.1/48 kHz. They were generated with:

```bash
ffmpeg -i tones.wav -codec:a libmp3lame -b:a 128k -write_xing 0 \
    tone_a4a5a6_44100_stereo_128cbr.mp3
ffmpeg -i tones.wav -codec:a libmp3lame -q:a 4 \
    tone_a4a5a6_44100_stereo_vbr.mp3
ffmpeg -i tones.wav -ac 1 -ar 22050 -codec:a libmp3lame -b:a 64k \
    tone_a4_22050_mono_64cbr.mp3
ffmpeg -i tones.wav -ac 1 -ar 8000 -codec:a libmp3lame -b:a 16k \
    tone_a4_8000_mono_16cbr.mp3
ffmpeg -i tones.wav -ar 48000 -codec:a libmp3lame -b:a 320k \
    tone_a4_48000_stereo_320cbr.mp3
```

- `tests/test_mp3dec.py` decodes them at several feed chunk sizes and checks
  frame and sample totals, sample rate/channels, ID3 skipping, volume shift,
  reset, and the tone frequency of the decoded PCM. A partial frame at a chunk
  boundary must be kept, not dropped, so the totals have to be identical for
  1 KiB, 4 KiB and 8 KiB feeds.
- `tests/cpython_mp3_info.py` runs under CPython and checks the pure-Python
  header/Xing/ID3 parser (and `get_info()` durations and bitrates) against
  ffprobe values.
- `tests/test_stream_mp3.py` covers AudioManager routing (`.mp3` →
  `MP3Stream`, `.wav` → `WAVStream`), sample-rate negotiation from the MP3
  header, and the desktop player fallback (decode to a temporary WAV when only
  `aplay`/`paplay` is available).
- `tests/manual_test_dac.py --file /music/test.mp3 --notes a4,a5,a6` plays an
  MP3 through the headphone/DAC jack and scores it acoustically on the host.

## Buzzer acoustic verification

`scripts/mpos_buzzer_acoustic.py` plays a known note sequence on the badge
buzzer and confirms it from a USB microphone recording made on the host. Each
loud segment is matched to the expected note: the strongest spectral peak is
folded down to the nearest harmonic, which also works for low notes whose
fundamental sits under the piezo resonance (a buzzer is a square-wave PWM
output, and small piezo discs peak around 3-4 kHz).

Host requirements: `arecord` (`alsa-utils`) and `numpy`. Run it on the machine
the sound card and the badge are attached to; the manual entry point is
`tests/manual_test_buzzer.py`:

```bash
# list capture devices
python3 scripts/mpos_buzzer_acoustic.py list

# play a4,a5,a6,a7 and gate pass/fail on the recording
python3 tests/manual_test_buzzer.py --notes a4,a5,a6,a7 --volume 100

# re-analyze an earlier recording without a device
python3 scripts/mpos_buzzer_acoustic.py analyze --wav tmp/buzzertests/manual-<stamp>.wav --notes a4,a5,a6,a7
```

Recordings and `metrics.json` / `metrics.jsonl` go to `--out-dir` (default
`tmp/buzzertests`). The same feature is available from Python via
`MPOSController.buzzer_acoustic_measure()` and `.buzzer_acoustic_verify()`.
Without `--relayport` a four-note run takes about twenty seconds; adding
`--relayport /dev/ttyUSB0` power-cycles the badge first and takes about forty.
The synthetic analyzer tests need no hardware:

```bash
python3 tests/cpython_buzzer_acoustic.py
```

## DAC acoustic verification

`scripts/mpos_dac_acoustic.py` checks the analogue path: the badge renders a
known tone sequence through an i2s output (the on-board DAC / headphone jack),
a capture device on the host records it, and the analyzer confirms each tone.
It is the counterpart of the buzzer check: same recording helpers, but the
audio goes through the codec instead of a PWM pin, so the fundamentals are
clean and the measured SNR is much higher (about 60 dB on zbox1).

No cable is needed if the badge drives a speaker: both acoustic tools default
to a USB microphone (on zbox1 the webcam's C925e, which also records the
buzzer) and pick the channel count from the device, since USB microphones
refuse mono. Wiring the badge jack into the on-board line input is quieter and
more precise — `--device plughw:0,0 --capture-gain 20` (+4 dB): the tool
restores the previous mixer value afterwards. Either way the tone WAV is
generated on the badge, so nothing has to be uploaded:

```bash
python3 tests/manual_test_dac.py
python3 tests/manual_test_dac.py --device plughw:0,0 --capture-gain 20
python3 tests/manual_test_dac.py --notes a4,a5,a6 --relayport /dev/ttyUSB0
python3 tests/manual_test_dac.py --file /music/test.mp3 --notes a4,a5,a6
```

`--file` plays an existing file on the badge instead of generated tones; with-
out `--notes` it just reports what was captured (peak frequency per loud
segment), which is useful when bringing up a new decoder or output. Metrics are
written to `--out-dir` (default `tmp/dactests`) and the same feature is
available as `MPOSController.dac_acoustic_measure()` /
`.dac_acoustic_verify()`. Synthetic tests need no hardware:

```bash
python3 tests/cpython_dac_acoustic.py
```

## First-use and render-time paths

Some UI code only runs the first time a feature is used, and some callbacks run
*while LVGL is drawing*. Warm-cache tests miss both:

- Clear the FontManager caches (`_composed_font_cache`, `_emoji_*`,
  `_imgfont_*`) and render emoji in a textarea placeholder, a keyboard field and
  a label. `tests/test_graphical_emoji_font_while_drawing.py` covers the
  placeholder case.
- Do not call `lv.snapshot_take*` from a draw callback (imgfont/style/event): it
  waits for the draw that invoked it and hangs the system without a traceback.
  Defer it with `lv.async_call`, as `FontManager` does.
- A hang is a bug: rerun with `--timeout`, capture the last serial output, and
  add a regression test.

## Mock Classes

Import mocks from `mpos.testing`:

```python
from mpos.testing import (
    # Hardware mocks
    MockMachine,      # Full machine module mock
    MockPin,          # GPIO pins
    MockPWM,          # PWM for buzzer
    MockI2S,          # Audio I2S
    MockTimer,        # Hardware timers
    MockNeoPixel,     # LED strips
    MockSocket,       # Network sockets
    
    # MPOS mocks
    MockTaskManager,  # Async task management
    MockDownloadManager,  # HTTP downloads
    
    # Network mocks
    MockNetwork,      # WiFi/network module
    MockRequests,     # HTTP requests
    MockResponse,     # HTTP responses
    
    # Utility mocks
    MockTime,         # Time functions
    MockJSON,         # JSON parsing
    
    # Helpers
    inject_mocks,     # Inject mocks into sys.modules
    create_mock_module,  # Create mock module
)
```

### Injecting Mocks

```python
from mpos.testing import inject_mocks, MockMachine, MockNetwork

# Inject before importing modules that use hardware
inject_mocks({
    'machine': MockMachine(),
    'network': MockNetwork(connected=True),
})

# Now import the module under test
from mpos.hardware import some_module
```

### Mock Examples

**MockNeoPixel:**
```python
from mpos.testing import MockNeoPixel, MockPin

pin = MockPin(5)
leds = MockNeoPixel(pin, 10)

leds[0] = (255, 0, 0)  # Set first LED to red
leds.write()

assert leds.write_count == 1
assert leds[0] == (255, 0, 0)
```

**MockRequests:**
```python
from mpos.testing import MockRequests

mock_requests = MockRequests()
mock_requests.set_next_response(
    status_code=200,
    text='{"status": "ok"}',
    headers={'Content-Type': 'application/json'}
)

response = mock_requests.get("https://api.example.com/data")
assert response.status_code == 200
```

**MockTimer:**
```python
from mpos.testing import MockTimer

timer = MockTimer(0)
timer.init(period=1000, mode=MockTimer.PERIODIC, callback=my_callback)

# Manually trigger for testing
timer.trigger()

# Or trigger all timers
MockTimer.trigger_all()
```

## Test Naming Conventions

- `test_*.py` - Standard unit tests
- `test_graphical_*.py` - Tests requiring LVGL/UI
- `manual_test_*.py` - Manual tests (not run automatically)

## Writing New Tests

### Simple Unit Test

```python
import unittest

class TestMyFeature(unittest.TestCase):
    def test_something(self):
        result = my_function()
        self.assertEqual(result, expected)
```

### Graphical Test

```python
from mpos.ui.testing import GraphicalTestCase
import lvgl as lv

class TestMyUI(GraphicalTestCase):
    def test_button_click(self):
        button = lv.button(self.screen)
        label = lv.label(button)
        label.set_text("Click Me")

        self.wait_for_render()
        self.click_button("Click Me")

        # Verify result
```

### Keyboard Test

```python
from mpos.ui.testing import KeyboardTestCase

class TestMyKeyboard(KeyboardTestCase):
    def test_input(self):
        self.create_keyboard_scene()

        self.type_text("hello")
        self.assertTextareaText("hello")

        self.click_keyboard_button("Enter")
```

### Test with Mocks

```python
import unittest
from mpos.testing import MockNetwork, inject_mocks

class TestNetworkFeature(unittest.TestCase):
    def setUp(self):
        self.mock_network = MockNetwork(connected=True)
        inject_mocks({'network': self.mock_network})
    
    def test_connected(self):
        from my_module import check_connection
        self.assertTrue(check_connection())
    
    def test_disconnected(self):
        self.mock_network.set_connected(False)
        from my_module import check_connection
        self.assertFalse(check_connection())
```

## Best Practices

1. **Use base classes** - Extend `GraphicalTestBase` or `KeyboardTestBase` for UI tests
2. **Use mpos.testing mocks** - Don't create inline mocks; use the centralized ones
3. **Clean up in tearDown** - Base classes handle this, but custom tests should clean up
4. **Don't include `if __name__ == '__main__'`** - The test runner handles this
5. **Use descriptive test names** - `test_keyboard_q_button_works` not `test_1`
6. **Add docstrings** - Explain what the test verifies and why

## Debugging Tests

```bash
# Run with verbose output
python3 scripts/test_runner.py tests/test_my_test.py

# Run with GDB (desktop only)
gdb --args ./lvgl_micropython/build/lvgl_micropy_unix -X heapsize=8M tests/test_my_test.py
```

## Screenshots

Screenshots are saved to `tests/screenshots/` in raw format. Convert to PNG:

```bash
cd tests/screenshots
./convert_to_png.sh
```
