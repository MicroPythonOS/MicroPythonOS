# MicroPythonOS Testing Guide

This directory contains the test suite for MicroPythonOS. Tests can run on both desktop (for fast iteration) and on-device (for hardware verification).

## Quick Start

```bash
# Run all tests
./tests/unittest.sh

# Run a specific test
./tests/unittest.sh tests/test_graphical_keyboard_q_button_bug.py

# Run on device
./tests/unittest.sh tests/test_graphical_keyboard_q_button_bug.py --ondevice
```

## Test Architecture

### Directory Structure

```
tests/
├── base/                    # Base test classes (DRY patterns)
│   ├── __init__.py         # Exports GraphicalTestBase, KeyboardTestBase
│   ├── graphical_test_base.py
│   └── keyboard_test_base.py
├── screenshots/             # Captured screenshots for visual regression
├── test_*.py               # Test files
├── unittest.sh             # Test runner script
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

## Base Test Classes

### GraphicalTestBase

Base class for all graphical (LVGL) tests. Provides:
- Automatic screen creation/cleanup
- Screenshot capture
- Widget finding utilities
- Custom assertions

```python
from base import GraphicalTestBase

class TestMyUI(GraphicalTestBase):
    def test_something(self):
        # self.screen is already created
        label = lv.label(self.screen)
        label.set_text("Hello")
        
        self.wait_for_render()
        self.assertTextPresent("Hello")
        self.capture_screenshot("my_test.raw")
```

**Key Methods:**
- `wait_for_render(iterations=5)` - Process LVGL tasks
- `capture_screenshot(filename)` - Save screenshot
- `find_label_with_text(text)` - Find label widget
- `click_button(button)` - Simulate button click
- `assertTextPresent(text)` - Assert text is on screen
- `assertWidgetVisible(widget)` - Assert widget is visible

### KeyboardTestBase

Extends GraphicalTestBase for keyboard tests. Provides:
- Keyboard and textarea creation
- Reliable keyboard button clicking
- Textarea assertions

```python
from base import KeyboardTestBase

class TestMyKeyboard(KeyboardTestBase):
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
- `test_graphical_*.py` - Tests requiring LVGL/UI (detected by unittest.sh)
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
from base import GraphicalTestBase
import lvgl as lv

class TestMyUI(GraphicalTestBase):
    def test_button_click(self):
        button = lv.button(self.screen)
        label = lv.label(button)
        label.set_text("Click Me")
        
        self.wait_for_render()
        self.click_button(button)
        
        # Verify result
```

### Keyboard Test

```python
from base import KeyboardTestBase

class TestMyKeyboard(KeyboardTestBase):
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
./tests/unittest.sh tests/test_my_test.py

# Run with GDB (desktop only)
gdb --args ./lvgl_micropython/build/lvgl_micropy_unix -X heapsize=8M tests/test_my_test.py
```

## Screenshots

Screenshots are saved to `tests/screenshots/` in raw format. Convert to PNG:

```bash
cd tests/screenshots
./convert_to_png.sh
```
