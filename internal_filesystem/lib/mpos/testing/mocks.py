"""
Mock implementations for MicroPythonOS testing.

This module provides mock implementations of hardware and system modules
for testing without actual hardware. Works on both desktop and device.
"""

import sys


# =============================================================================
# Helper Functions
# =============================================================================

class MockModule:
    """
    Simple class that acts as a module container.
    MicroPython doesn't have types.ModuleType, so we use this instead.
    """
    pass


def create_mock_module(name, **attrs):
    """
    Create a mock module with the given attributes.
    
    Args:
        name: Module name (for debugging)
        **attrs: Attributes to set on the module
        
    Returns:
        MockModule instance with attributes set
    """
    module = MockModule()
    module.__name__ = name
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


def inject_mocks(mock_specs):
    """
    Inject mock modules into sys.modules.
    
    Args:
        mock_specs: Dict mapping module names to mock instances/classes
                   e.g., {'machine': MockMachine(), 'mpos.task_manager': mock_tm}
    """
    for name, mock in mock_specs.items():
        sys.modules[name] = mock


# =============================================================================
# Hardware Mocks - machine module
# =============================================================================

class MockPin:
    """Mock machine.Pin for testing GPIO operations."""
    
    IN = 0
    OUT = 1
    PULL_UP = 2
    PULL_DOWN = 3
    
    def __init__(self, pin_number, mode=None, pull=None):
        self.pin_number = pin_number
        self.mode = mode
        self.pull = pull
        self._value = 0
    
    def value(self, val=None):
        """Get or set pin value."""
        if val is None:
            return self._value
        self._value = val
    
    def on(self):
        """Set pin high."""
        self._value = 1
    
    def off(self):
        """Set pin low."""
        self._value = 0


class MockPWM:
    """Mock machine.PWM for testing PWM operations (buzzer, etc.)."""
    
    def __init__(self, pin, freq=0, duty=0):
        self.pin = pin
        self.last_freq = freq
        self.last_duty = duty
    
    def freq(self, value=None):
        """Get or set frequency."""
        if value is not None:
            self.last_freq = value
        return self.last_freq
    
    def duty_u16(self, value=None):
        """Get or set duty cycle (16-bit)."""
        if value is not None:
            self.last_duty = value
        return self.last_duty
    
    def duty(self, value=None):
        """Get or set duty cycle (10-bit)."""
        if value is not None:
            self.last_duty = value * 64  # Convert to 16-bit
        return self.last_duty // 64
    
    def deinit(self):
        """Deinitialize PWM."""
        self.last_freq = 0
        self.last_duty = 0


class MockI2S:
    """Mock machine.I2S for testing audio I2S operations."""
    
    TX = 0
    RX = 1
    MONO = 0
    STEREO = 1
    
    def __init__(self, id, sck=None, ws=None, sd=None, mode=None, 
                 bits=16, format=None, rate=44100, ibuf=None):
        self.id = id
        self.sck = sck
        self.ws = ws
        self.sd = sd
        self.mode = mode
        self.bits = bits
        self.format = format
        self.rate = rate
        self.ibuf = ibuf
        self._write_buffer = bytearray(1024)
        self._bytes_written = 0
    
    def write(self, buf):
        """Write audio data (blocking)."""
        self._bytes_written += len(buf)
        return len(buf)
    
    def write_readinto(self, write_buf, read_buf):
        """Non-blocking write with readback."""
        self._bytes_written += len(write_buf)
        return len(write_buf)
    
    def deinit(self):
        """Deinitialize I2S."""
        pass


class MockTimer:
    """Mock machine.Timer for testing periodic callbacks."""
    
    _all_timers = {}
    
    PERIODIC = 1
    ONE_SHOT = 0
    
    def __init__(self, timer_id=-1):
        self.timer_id = timer_id
        self.callback = None
        self.period = None
        self.mode = None
        self.active = False
        if timer_id >= 0:
            MockTimer._all_timers[timer_id] = self
    
    def init(self, period=None, mode=None, callback=None):
        """Initialize/configure the timer."""
        self.period = period
        self.mode = mode
        self.callback = callback
        self.active = True
    
    def deinit(self):
        """Deinitialize the timer."""
        self.active = False
        self.callback = None
    
    def trigger(self, *args, **kwargs):
        """Manually trigger the timer callback (for testing)."""
        if self.callback and self.active:
            self.callback(*args, **kwargs)
    
    @classmethod
    def get_timer(cls, timer_id):
        """Get a timer by ID."""
        return cls._all_timers.get(timer_id)
    
    @classmethod
    def trigger_all(cls):
        """Trigger all active timers (for testing)."""
        for timer in cls._all_timers.values():
            if timer.active:
                timer.trigger()
    
    @classmethod
    def reset_all(cls):
        """Reset all timers (clear registry)."""
        cls._all_timers.clear()


class MockNeoPixel:
    """Mock neopixel.NeoPixel for testing LED operations."""
    
    def __init__(self, pin, num_leds, bpp=3, timing=1):
        self.pin = pin
        self.num_leds = num_leds
        self.bpp = bpp
        self.timing = timing
        self.pixels = [(0, 0, 0)] * num_leds
        self.write_count = 0
    
    def __setitem__(self, index, value):
        """Set LED color (R, G, B) or (R, G, B, W) tuple."""
        if 0 <= index < self.num_leds:
            self.pixels[index] = value
    
    def __getitem__(self, index):
        """Get LED color."""
        if 0 <= index < self.num_leds:
            return self.pixels[index]
        return (0, 0, 0)
    
    def __len__(self):
        """Return number of LEDs."""
        return self.num_leds
    
    def fill(self, color):
        """Fill all LEDs with the same color."""
        for i in range(self.num_leds):
            self.pixels[i] = color
    
    def write(self):
        """Update hardware (mock - just increment counter)."""
        self.write_count += 1
    
    def get_all_colors(self):
        """Get all LED colors (for testing assertions)."""
        return self.pixels.copy()
    
    def reset_write_count(self):
        """Reset the write counter (for testing)."""
        self.write_count = 0


class MockMachine:
    """
    Mock machine module containing all hardware mocks.
    
    Usage:
        sys.modules['machine'] = MockMachine()
    """
    
    Pin = MockPin
    PWM = MockPWM
    I2S = MockI2S
    Timer = MockTimer
    
    @staticmethod
    def freq(freq=None):
        """Get or set CPU frequency."""
        return 240000000  # 240 MHz
    
    @staticmethod
    def reset():
        """Reset the device (no-op in mock)."""
        pass
    
    @staticmethod
    def soft_reset():
        """Soft reset the device (no-op in mock)."""
        pass


# =============================================================================
# MPOS Mocks - TaskManager
# =============================================================================

class MockTask:
    """Mock asyncio Task for testing."""
    
    def __init__(self):
        self.ph_key = 0
        self._done = False
        self.coro = None
        self._result = None
        self._exception = None
    
    def done(self):
        """Check if task is done."""
        return self._done
    
    def cancel(self):
        """Cancel the task."""
        self._done = True
    
    def result(self):
        """Get task result."""
        if self._exception:
            raise self._exception
        return self._result


class MockTaskManager:
    """
    Mock TaskManager for testing async operations.
    
    Usage:
        mock_tm = create_mock_module('mpos.task_manager', TaskManager=MockTaskManager)
        sys.modules['mpos.task_manager'] = mock_tm
    """
    
    task_list = []
    
    @classmethod
    def create_task(cls, coroutine):
        """Create a mock task from a coroutine."""
        task = MockTask()
        task.coro = coroutine
        cls.task_list.append(task)
        return task
    
    @staticmethod
    async def sleep(seconds):
        """Mock async sleep (no actual delay)."""
        pass
    
    @staticmethod
    async def sleep_ms(milliseconds):
        """Mock async sleep in milliseconds (no actual delay)."""
        pass
    
    @staticmethod
    async def wait_for(awaitable, timeout):
        """Mock wait_for with timeout."""
        return await awaitable
    
    @staticmethod
    def notify_event():
        """Create a mock async event."""
        class MockEvent:
            def __init__(self):
                self._set = False
            
            async def wait(self):
                pass
            
            def set(self):
                self._set = True
            
            def is_set(self):
                return self._set
        
        return MockEvent()
    
    @classmethod
    def clear_tasks(cls):
        """Clear all tracked tasks (for test cleanup)."""
        cls.task_list = []


# =============================================================================
# Network Mocks
# =============================================================================

class MockNetwork:
    """Mock network module for testing network connectivity."""
    
    STA_IF = 0
    AP_IF = 1
    
    class MockWLAN:
        """Mock WLAN interface."""
        
        def __init__(self, interface, connected=True):
            self.interface = interface
            self._connected = connected
            self._active = True
            self._config = {}
            self._scan_results = []
        
        def isconnected(self):
            """Return whether the WLAN is connected."""
            return self._connected
        
        def active(self, is_active=None):
            """Get/set whether the interface is active."""
            if is_active is None:
                return self._active
            self._active = is_active
        
        def connect(self, ssid, password):
            """Simulate connecting to a network."""
            self._connected = True
            self._config['ssid'] = ssid
        
        def disconnect(self):
            """Simulate disconnecting from network."""
            self._connected = False
        
        def config(self, param):
            """Get configuration parameter."""
            return self._config.get(param)
        
        def ifconfig(self):
            """Get IP configuration."""
            if self._connected:
                return ('192.168.1.100', '255.255.255.0', '192.168.1.1', '8.8.8.8')
            return ('0.0.0.0', '0.0.0.0', '0.0.0.0', '0.0.0.0')

        def ipconfig(self, key=None):
            """Return IP configuration details, mirroring network.WLAN.ipconfig."""
            config = self.ifconfig()
            mapping = {
                'addr4': config[0],
                'netmask4': config[1],
                'gateway4': config[2],
                'dns4': config[3],
            }
            if key is None:
                return mapping
            return mapping.get(key)
        
        def scan(self):
            """Scan for available networks."""
            return self._scan_results
    
    def __init__(self, connected=True):
        self._connected = connected
        self._wlan_instances = {}
    
    def WLAN(self, interface):
        """Create or return a WLAN interface."""
        if interface not in self._wlan_instances:
            self._wlan_instances[interface] = self.MockWLAN(interface, self._connected)
        return self._wlan_instances[interface]
    
    def set_connected(self, connected):
        """Change the connection state of all WLAN interfaces."""
        self._connected = connected
        for wlan in self._wlan_instances.values():
            wlan._connected = connected


class MockRaw:
    """Mock raw HTTP response for streaming."""
    
    def __init__(self, content, fail_after_bytes=None):
        self.content = content
        self.position = 0
        self.fail_after_bytes = fail_after_bytes
    
    def read(self, size):
        """Read a chunk of data."""
        if self.fail_after_bytes is not None and self.position >= self.fail_after_bytes:
            raise OSError(-113, "ECONNABORTED")
        
        chunk = self.content[self.position:self.position + size]
        self.position += len(chunk)
        return chunk


class MockResponse:
    """Mock HTTP response."""
    
    def __init__(self, status_code=200, text='', headers=None, content=b'', fail_after_bytes=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
        self.content = content
        self._closed = False
        self.raw = MockRaw(content, fail_after_bytes=fail_after_bytes)
    
    def close(self):
        """Close the response."""
        self._closed = True
    
    def json(self):
        """Parse response as JSON."""
        import json
        return json.loads(self.text)


class MockRequests:
    """Mock requests module for testing HTTP operations."""
    
    def __init__(self):
        self.last_url = None
        self.last_headers = None
        self.last_timeout = None
        self.last_stream = None
        self.last_request = None
        self.next_response = None
        self.raise_exception = None
        self.call_history = []
    
    def get(self, url, stream=False, timeout=None, headers=None):
        """Mock GET request."""
        self.last_url = url
        self.last_headers = headers
        self.last_timeout = timeout
        self.last_stream = stream
        
        self.last_request = {
            'method': 'GET',
            'url': url,
            'stream': stream,
            'timeout': timeout,
            'headers': headers or {}
        }
        self.call_history.append(self.last_request.copy())
        
        if self.raise_exception:
            exc = self.raise_exception
            self.raise_exception = None
            raise exc
        
        if self.next_response:
            response = self.next_response
            self.next_response = None
            return response
        
        return MockResponse()
    
    def post(self, url, data=None, json=None, timeout=None, headers=None):
        """Mock POST request."""
        self.last_url = url
        self.last_headers = headers
        self.last_timeout = timeout
        
        self.call_history.append({
            'method': 'POST',
            'url': url,
            'data': data,
            'json': json,
            'timeout': timeout,
            'headers': headers
        })
        
        if self.raise_exception:
            exc = self.raise_exception
            self.raise_exception = None
            raise exc
        
        if self.next_response:
            response = self.next_response
            self.next_response = None
            return response
        
        return MockResponse()
    
    def set_next_response(self, status_code=200, text='', headers=None, content=b'', fail_after_bytes=None):
        """Configure the next response to return."""
        self.next_response = MockResponse(status_code, text, headers, content, fail_after_bytes=fail_after_bytes)
        return self.next_response
    
    def set_exception(self, exception):
        """Configure an exception to raise on the next request."""
        self.raise_exception = exception
    
    def clear_history(self):
        """Clear the call history."""
        self.call_history = []


class MockSocket:
    """Mock socket for testing socket operations."""
    
    AF_INET = 2
    SOCK_STREAM = 1
    
    def __init__(self, af=None, sock_type=None):
        self.af = af
        self.sock_type = sock_type
        self.connected = False
        self.bound = False
        self.listening = False
        self.address = None
        self._send_exception = None
        self._recv_data = b''
        self._recv_position = 0
    
    def connect(self, address):
        """Simulate connecting to an address."""
        self.connected = True
        self.address = address
    
    def bind(self, address):
        """Simulate binding to an address."""
        self.bound = True
        self.address = address
    
    def listen(self, backlog):
        """Simulate listening for connections."""
        self.listening = True
    
    def send(self, data):
        """Simulate sending data."""
        if self._send_exception:
            exc = self._send_exception
            self._send_exception = None
            raise exc
        return len(data)
    
    def recv(self, size):
        """Simulate receiving data."""
        chunk = self._recv_data[self._recv_position:self._recv_position + size]
        self._recv_position += len(chunk)
        return chunk
    
    def close(self):
        """Close the socket."""
        self.connected = False
    
    def set_send_exception(self, exception):
        """Configure an exception to raise on next send()."""
        self._send_exception = exception
    
    def set_recv_data(self, data):
        """Configure data to return from recv()."""
        self._recv_data = data
        self._recv_position = 0


# =============================================================================
# Utility Mocks
# =============================================================================

class MockTime:
    """Mock time module for testing time-dependent code."""
    
    def __init__(self, start_time=0):
        self._current_time_ms = start_time
        self._sleep_calls = []
    
    def ticks_ms(self):
        """Get current time in milliseconds."""
        return self._current_time_ms
    
    def ticks_diff(self, ticks1, ticks2):
        """Calculate difference between two tick values."""
        return ticks1 - ticks2
    
    def sleep(self, seconds):
        """Simulate sleep (doesn't actually sleep)."""
        self._sleep_calls.append(seconds)
    
    def sleep_ms(self, milliseconds):
        """Simulate sleep in milliseconds."""
        self._sleep_calls.append(milliseconds / 1000.0)
    
    def advance(self, milliseconds):
        """Advance the mock time."""
        self._current_time_ms += milliseconds
    
    def get_sleep_calls(self):
        """Get history of sleep calls."""
        return self._sleep_calls
    
    def clear_sleep_calls(self):
        """Clear the sleep call history."""
        self._sleep_calls = []


class MockJSON:
    """Mock JSON module for testing JSON parsing."""
    
    def __init__(self):
        self.raise_exception = None
    
    def loads(self, text):
        """Parse JSON string."""
        if self.raise_exception:
            exc = self.raise_exception
            self.raise_exception = None
            raise exc
        
        import json
        return json.loads(text)
    
    def dumps(self, obj):
        """Serialize object to JSON string."""
        import json
        return json.dumps(obj)
    
    def set_exception(self, exception):
        """Configure an exception to raise on the next loads() call."""
        self.raise_exception = exception


class MockDownloadManager:
    """Mock DownloadManager for testing async downloads."""
    
    def __init__(self):
        self.download_data = b''
        self.should_fail = False
        self.fail_after_bytes = None
        self.headers_received = None
        self.url_received = None
        self.call_history = []
        self.chunk_size = 1024
        self.simulated_speed_bps = 100 * 1024
    
    async def download_url(self, url, outfile=None, total_size=None,
                          progress_callback=None, chunk_callback=None, headers=None,
                          speed_callback=None):
        """Mock async download with flexible output modes."""
        self.url_received = url
        self.headers_received = headers
        
        self.call_history.append({
            'url': url,
            'outfile': outfile,
            'total_size': total_size,
            'headers': headers,
            'has_progress_callback': progress_callback is not None,
            'has_chunk_callback': chunk_callback is not None,
            'has_speed_callback': speed_callback is not None
        })
        
        if self.should_fail:
            if outfile or chunk_callback:
                return False
            return None
        
        if self.fail_after_bytes is not None and self.fail_after_bytes == 0:
            raise OSError(-113, "ECONNABORTED")
        
        bytes_sent = 0
        chunks = []
        total_data_size = len(self.download_data)
        effective_total_size = total_size if total_size else total_data_size
        last_progress_pct = -1.0
        bytes_since_speed_update = 0
        speed_update_threshold = 1000
        
        while bytes_sent < total_data_size:
            if self.fail_after_bytes is not None and bytes_sent >= self.fail_after_bytes:
                raise OSError(-113, "ECONNABORTED")
            
            chunk = self.download_data[bytes_sent:bytes_sent + self.chunk_size]
            
            if chunk_callback:
                await chunk_callback(chunk)
            elif outfile:
                pass
            else:
                chunks.append(chunk)
            
            bytes_sent += len(chunk)
            bytes_since_speed_update += len(chunk)
            
            if progress_callback and effective_total_size > 0:
                percent = round((bytes_sent * 100) / effective_total_size, 2)
                if percent != last_progress_pct:
                    await progress_callback(percent)
                    last_progress_pct = percent
            
            if speed_callback and bytes_since_speed_update >= speed_update_threshold:
                await speed_callback(self.simulated_speed_bps)
                bytes_since_speed_update = 0
        
        if outfile or chunk_callback:
            return True
        else:
            return b''.join(chunks)
    
    def set_download_data(self, data):
        """Configure the data to return from downloads."""
        self.download_data = data
    
    def set_should_fail(self, should_fail):
        """Configure whether downloads should fail."""
        self.should_fail = should_fail
    
    def set_fail_after_bytes(self, bytes_count):
        """Configure network failure after specified bytes."""
        self.fail_after_bytes = bytes_count
    
    def clear_history(self):
        """Clear the call history."""
        self.call_history = []


# =============================================================================
# Threading Mocks
# =============================================================================

class MockThread:
    """
    Mock _thread module for testing threaded operations.
    
    Usage:
        sys.modules['_thread'] = MockThread
    """
    
    _started_threads = []
    _stack_size = 0
    
    @classmethod
    def start_new_thread(cls, func, args):
        """Record thread start but don't actually start a thread."""
        cls._started_threads.append((func, args))
        return len(cls._started_threads)
    
    @classmethod
    def stack_size(cls, size=None):
        """Mock stack_size."""
        if size is not None:
            cls._stack_size = size
        return cls._stack_size
    
    @classmethod
    def clear_threads(cls):
        """Clear recorded threads (for test cleanup)."""
        cls._started_threads = []
    
    @classmethod
    def get_started_threads(cls):
        """Get list of started threads (for test assertions)."""
        return cls._started_threads


class MockApps:
    """
    Mock mpos.apps module for testing (deprecated, use MockAppManager instead).
    
    This is kept for backward compatibility with existing tests.
    
    Usage:
        sys.modules['mpos.apps'] = MockApps
    """
    
    @staticmethod
    def start_app(fullname):
        """Mock start_app function."""
        return True
    
    @staticmethod
    def restart_launcher():
        """Mock restart_launcher function."""
        return True
    
    @staticmethod
    def execute_script(script_source, is_file, classname, cwd=None):
        """Mock execute_script function."""
        return True


class MockAppManager:
    """
    Mock mpos.content.app_manager module for testing.
    
    Usage:
        sys.modules['mpos.content.app_manager'] = MockAppManager
    """
    
    @staticmethod
    def start_app(fullname):
        """Mock start_app function."""
        return True
    
    @staticmethod
    def restart_launcher():
        """Mock restart_launcher function."""
        return True
    
    @staticmethod
    def execute_script(script_source, is_file, classname, cwd=None):
        """Mock execute_script function."""
        return True