"""
Regression test for MicroPythonOS#299: uaiowebsocket must not try to send a
pong itself on an incoming PING. The bundled aiohttp port answers pings
inside WebSocketClient.receive() and its ClientWebSocketResponse has no
pong() method, so the old call raised AttributeError and logged an ERROR on
every relay ping. The PING path now only runs the on_ping callback.

The module is loaded from lib/ (purging any frozen copy) so the test sees
the source under test without a firmware rebuild.

Usage:
    python3 scripts/test_runner.py tests/test_uaiowebsocket_ping.py
"""
import sys, unittest

sys.modules.pop("uaiowebsocket", None)
if "lib" not in sys.path[:1]:
    sys.path.insert(0, "lib")
import uaiowebsocket
from aiohttp.aiohttp_ws import ClientWebSocketResponse


class _App:
    """Only what _handle_ping touches on self."""
    def __init__(self):
        self.pings = []
        self.on_ping = lambda ws, data: self.pings.append(data)


class TestPingHandling(unittest.TestCase):
    def test_bundled_aiohttp_has_no_pong(self):
        # Documents the constraint the fix is built on.
        self.assertFalse(hasattr(ClientWebSocketResponse, "pong"))

    def test_ping_runs_callback_only(self):
        app = _App()
        uaiowebsocket.WebSocketApp._handle_ping(app, b"relay-ping")
        # callbacks are queued by _run_callback; drain the queue synchronously
        while uaiowebsocket._callback_queue:
            cb, args = uaiowebsocket._callback_queue.popleft()
            cb(*args)
        self.assertEqual(app.pings, [b"relay-ping"])

    def test_no_pong_attribute_needed_anywhere(self):
        src = open("lib/uaiowebsocket.py").read()
        self.assertFalse(".pong(" in src)


if __name__ == "__main__":
    unittest.main()
