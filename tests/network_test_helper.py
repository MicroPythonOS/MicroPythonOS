"""
Network testing helper module for MicroPythonOS.

This module provides mock implementations of network-related modules
for testing without requiring actual network connectivity. These mocks
are designed to be used with dependency injection in the classes being tested.

Usage:
    from network_test_helper import MockNetwork, MockRequests, MockTimer

    # Create mocks
    mock_network = MockNetwork(connected=True)
    mock_requests = MockRequests()

    # Configure mock responses
    mock_requests.set_next_response(status_code=200, text='{"key": "value"}')

    # Pass to class being tested
    obj = MyClass(network_module=mock_network, requests_module=mock_requests)

    # Test behavior
    result = obj.fetch_data()
    assert mock_requests.last_url == "http://expected.url"
"""

import time


class MockNetwork:
    """
    Mock network module for testing network connectivity.

    Simulates the MicroPython 'network' module with WLAN interface.
    """

    STA_IF = 0  # Station interface constant
    AP_IF = 1   # Access Point interface constant

    class MockWLAN:
        """Mock WLAN interface."""

        def __init__(self, interface, connected=True):
            self.interface = interface
            self._connected = connected
            self._active = True
            self._config = {}
            self._scan_results = []  # Can be configured for testing

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

        def scan(self):
            """Scan for available networks."""
            return self._scan_results

    def __init__(self, connected=True):
        """
        Initialize mock network module.

        Args:
            connected: Initial connection state (default: True)
        """
        self._connected = connected
        self._wlan_instances = {}

    def WLAN(self, interface):
        """
        Create or return a WLAN interface.

        Args:
            interface: Interface type (STA_IF or AP_IF)

        Returns:
            MockWLAN instance
        """
        if interface not in self._wlan_instances:
            self._wlan_instances[interface] = self.MockWLAN(interface, self._connected)
        return self._wlan_instances[interface]

    def set_connected(self, connected):
        """
        Change the connection state of all WLAN interfaces.

        Args:
            connected: New connection state
        """
        self._connected = connected
        for wlan in self._wlan_instances.values():
            wlan._connected = connected


class MockRaw:
    """
    Mock raw HTTP response for streaming.

    Simulates the 'raw' attribute of requests.Response for chunked reading.
    """

    def __init__(self, content, fail_after_bytes=None):
        """
        Initialize mock raw response.

        Args:
            content: Binary content to stream
            fail_after_bytes: If set, raise OSError(-113) after reading this many bytes
        """
        self.content = content
        self.position = 0
        self.fail_after_bytes = fail_after_bytes

    def read(self, size):
        """
        Read a chunk of data.

        Args:
            size: Number of bytes to read

        Returns:
            bytes: Chunk of data (may be smaller than size at end of stream)

        Raises:
            OSError: If fail_after_bytes is set and reached
        """
        # Check if we should simulate network failure
        if self.fail_after_bytes is not None and self.position >= self.fail_after_bytes:
            raise OSError(-113, "ECONNABORTED")

        chunk = self.content[self.position:self.position + size]
        self.position += len(chunk)
        return chunk


class MockResponse:
    """
    Mock HTTP response.

    Simulates requests.Response object with status code, text, headers, etc.
    """

    def __init__(self, status_code=200, text='', headers=None, content=b'', fail_after_bytes=None):
        """
        Initialize mock response.

        Args:
            status_code: HTTP status code (default: 200)
            text: Response text content (default: '')
            headers: Response headers dict (default: {})
            content: Binary response content (default: b'')
            fail_after_bytes: If set, raise OSError after reading this many bytes
        """
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
        self.content = content
        self._closed = False

        # Mock raw attribute for streaming
        self.raw = MockRaw(content, fail_after_bytes=fail_after_bytes)

    def close(self):
        """Close the response."""
        self._closed = True

    def json(self):
        """Parse response as JSON."""
        import json
        return json.loads(self.text)


class MockRequests:
    """
    Mock requests module for testing HTTP operations.

    Provides configurable mock responses and exception injection for testing
    HTTP client code without making actual network requests.
    """

    def __init__(self):
        """Initialize mock requests module."""
        self.last_url = None
        self.last_headers = None
        self.last_timeout = None
        self.last_stream = None
        self.last_request = None  # Full request info dict
        self.next_response = None
        self.raise_exception = None
        self.call_history = []

    def get(self, url, stream=False, timeout=None, headers=None):
        """
        Mock GET request.

        Args:
            url: URL to fetch
            stream: Whether to stream the response
            timeout: Request timeout in seconds
            headers: Request headers dict

        Returns:
            MockResponse object

        Raises:
            Exception: If an exception was configured via set_exception()
        """
        self.last_url = url
        self.last_headers = headers
        self.last_timeout = timeout
        self.last_stream = stream

        # Store full request info
        self.last_request = {
            'method': 'GET',
            'url': url,
            'stream': stream,
            'timeout': timeout,
            'headers': headers or {}
        }

        # Record call in history
        self.call_history.append(self.last_request.copy())

        if self.raise_exception:
            exc = self.raise_exception
            self.raise_exception = None  # Clear after raising
            raise exc

        if self.next_response:
            response = self.next_response
            self.next_response = None  # Clear after returning
            return response

        # Default response
        return MockResponse()

    def post(self, url, data=None, json=None, timeout=None, headers=None):
        """
        Mock POST request.

        Args:
            url: URL to post to
            data: Form data to send
            json: JSON data to send
            timeout: Request timeout in seconds
            headers: Request headers dict

        Returns:
            MockResponse object

        Raises:
            Exception: If an exception was configured via set_exception()
        """
        self.last_url = url
        self.last_headers = headers
        self.last_timeout = timeout

        # Record call in history
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
        """
        Configure the next response to return.

        Args:
            status_code: HTTP status code (default: 200)
            text: Response text (default: '')
            headers: Response headers dict (default: {})
            content: Binary response content (default: b'')
            fail_after_bytes: If set, raise OSError after reading this many bytes

        Returns:
            MockResponse: The configured response object
        """
        self.next_response = MockResponse(status_code, text, headers, content, fail_after_bytes=fail_after_bytes)
        return self.next_response

    def set_exception(self, exception):
        """
        Configure an exception to raise on the next request.

        Args:
            exception: Exception instance to raise
        """
        self.raise_exception = exception

    def clear_history(self):
        """Clear the call history."""
        self.call_history = []


class MockJSON:
    """
    Mock JSON module for testing JSON parsing.

    Allows injection of parse errors for testing error handling.
    """

    def __init__(self):
        """Initialize mock JSON module."""
        self.raise_exception = None

    def loads(self, text):
        """
        Parse JSON string.

        Args:
            text: JSON string to parse

        Returns:
            Parsed JSON object

        Raises:
            Exception: If an exception was configured via set_exception()
        """
        if self.raise_exception:
            exc = self.raise_exception
            self.raise_exception = None
            raise exc

        # Use Python's real json module for actual parsing
        import json
        return json.loads(text)

    def dumps(self, obj):
        """
        Serialize object to JSON string.

        Args:
            obj: Object to serialize

        Returns:
            str: JSON string
        """
        import json
        return json.dumps(obj)

    def set_exception(self, exception):
        """
        Configure an exception to raise on the next loads() call.

        Args:
            exception: Exception instance to raise
        """
        self.raise_exception = exception


class MockTimer:
    """
    Mock Timer for testing periodic callbacks.

    Simulates machine.Timer without actual delays. Useful for testing
    code that uses timers for periodic tasks.
    """

    # Class-level registry of all timers
    _all_timers = {}
    _next_timer_id = 0

    PERIODIC = 1
    ONE_SHOT = 0

    def __init__(self, timer_id):
        """
        Initialize mock timer.

        Args:
            timer_id: Timer ID (0-3 on most MicroPython platforms)
        """
        self.timer_id = timer_id
        self.callback = None
        self.period = None
        self.mode = None
        self.active = False
        MockTimer._all_timers[timer_id] = self

    def init(self, period=None, mode=None, callback=None):
        """
        Initialize/configure the timer.

        Args:
            period: Timer period in milliseconds
            mode: Timer mode (PERIODIC or ONE_SHOT)
            callback: Callback function to call on timer fire
        """
        self.period = period
        self.mode = mode
        self.callback = callback
        self.active = True

    def deinit(self):
        """Deinitialize the timer."""
        self.active = False
        self.callback = None

    def trigger(self, *args, **kwargs):
        """
        Manually trigger the timer callback (for testing).

        Args:
            *args: Arguments to pass to callback
            **kwargs: Keyword arguments to pass to callback
        """
        if self.callback and self.active:
            self.callback(*args, **kwargs)

    @classmethod
    def get_timer(cls, timer_id):
        """
        Get a timer by ID.

        Args:
            timer_id: Timer ID to retrieve

        Returns:
            MockTimer instance or None if not found
        """
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


class MockSocket:
    """
    Mock socket for testing socket operations.

    Simulates usocket module without actual network I/O.
    """

    AF_INET = 2
    SOCK_STREAM = 1

    def __init__(self, af=None, sock_type=None):
        """
        Initialize mock socket.

        Args:
            af: Address family (AF_INET, etc.)
            sock_type: Socket type (SOCK_STREAM, etc.)
        """
        self.af = af
        self.sock_type = sock_type
        self.connected = False
        self.bound = False
        self.listening = False
        self.address = None
        self.port = None
        self._send_exception = None
        self._recv_data = b''
        self._recv_position = 0

    def connect(self, address):
        """
        Simulate connecting to an address.

        Args:
            address: Tuple of (host, port)
        """
        self.connected = True
        self.address = address

    def bind(self, address):
        """
        Simulate binding to an address.

        Args:
            address: Tuple of (host, port)
        """
        self.bound = True
        self.address = address

    def listen(self, backlog):
        """
        Simulate listening for connections.

        Args:
            backlog: Maximum number of queued connections
        """
        self.listening = True

    def send(self, data):
        """
        Simulate sending data.

        Args:
            data: Bytes to send

        Returns:
            int: Number of bytes sent

        Raises:
            Exception: If configured via set_send_exception()
        """
        if self._send_exception:
            exc = self._send_exception
            self._send_exception = None
            raise exc
        return len(data)

    def recv(self, size):
        """
        Simulate receiving data.

        Args:
            size: Maximum bytes to receive

        Returns:
            bytes: Received data
        """
        chunk = self._recv_data[self._recv_position:self._recv_position + size]
        self._recv_position += len(chunk)
        return chunk

    def close(self):
        """Close the socket."""
        self.connected = False

    def set_send_exception(self, exception):
        """
        Configure an exception to raise on next send().

        Args:
            exception: Exception instance to raise
        """
        self._send_exception = exception

    def set_recv_data(self, data):
        """
        Configure data to return from recv().

        Args:
            data: Bytes to return from recv() calls
        """
        self._recv_data = data
        self._recv_position = 0


def socket(af=MockSocket.AF_INET, sock_type=MockSocket.SOCK_STREAM):
    """
    Create a mock socket.

    Args:
        af: Address family (default: AF_INET)
        sock_type: Socket type (default: SOCK_STREAM)

    Returns:
        MockSocket instance
    """
    return MockSocket(af, sock_type)


class MockTime:
    """
    Mock time module for testing time-dependent code.

    Allows manual control of time progression for deterministic testing.
    """

    def __init__(self, start_time=0):
        """
        Initialize mock time module.

        Args:
            start_time: Initial time in milliseconds (default: 0)
        """
        self._current_time_ms = start_time
        self._sleep_calls = []

    def ticks_ms(self):
        """
        Get current time in milliseconds.

        Returns:
            int: Current time in milliseconds
        """
        return self._current_time_ms

    def ticks_diff(self, ticks1, ticks2):
        """
        Calculate difference between two tick values.

        Args:
            ticks1: End time
            ticks2: Start time

        Returns:
            int: Difference in milliseconds
        """
        return ticks1 - ticks2

    def sleep(self, seconds):
        """
        Simulate sleep (doesn't actually sleep).

        Args:
            seconds: Number of seconds to sleep
        """
        self._sleep_calls.append(seconds)

    def sleep_ms(self, milliseconds):
        """
        Simulate sleep in milliseconds.

        Args:
            milliseconds: Number of milliseconds to sleep
        """
        self._sleep_calls.append(milliseconds / 1000.0)

    def advance(self, milliseconds):
        """
        Advance the mock time.

        Args:
            milliseconds: Number of milliseconds to advance
        """
        self._current_time_ms += milliseconds

    def get_sleep_calls(self):
        """
        Get history of sleep calls.

        Returns:
            list: List of sleep durations in seconds
        """
        return self._sleep_calls

    def clear_sleep_calls(self):
        """Clear the sleep call history."""
        self._sleep_calls = []
