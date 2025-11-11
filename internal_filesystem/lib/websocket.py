# websocket.py
# MicroPython WebSocketApp implementation for python-nostr port
# Compatible with websocket-client's WebSocketApp API, using MicroPython aiohttp

import uasyncio as asyncio
import time
import ucollections
import aiohttp
from aiohttp import WSMsgType, ClientWebSocketResponse

# Simplified logging for MicroPython with timestamps
def _log_debug(msg):
    print(f"[DEBUG {time.ticks_ms()}] {msg}")

def _log_error(msg):
    print(f"[ERROR {time.ticks_ms()}] {msg}")

# Simplified ABNF for opcode compatibility
class ABNF:
    OPCODE_TEXT = 1
    OPCODE_BINARY = 2
    OPCODE_CLOSE = 8
    OPCODE_PING = 9
    OPCODE_PONG = 10

# Exceptions
class WebSocketException(Exception):
    pass

class WebSocketConnectionClosedException(WebSocketException):
    pass

class WebSocketTimeoutException(WebSocketException):
    pass

# Queue for callback dispatching
_callback_queue = ucollections.deque((), 100)  # Empty tuple, maxlen=100

def _run_callback(callback, *args):
    if not callback:
        print("_run_callback: skipping None callback")
        return
    """Add callback to queue for execution."""
    try:
        _callback_queue.append((callback, args))
        _log_debug(f"Queued callback {callback}, args={args}, queue size: {len(_callback_queue)}")
        # print("Doing callback directly:")
        # callback(*args)
    except IndexError:
        _log_error("ERROR: websocket.py callback queue full, dropping callback")

async def _process_callbacks_async():
    """Process queued callbacks asynchronously."""
    import _thread
    while True: # this stops when "NWCWallet: manage_wallet_thread stopping, closing connections..."
        #print(f"_process_callbacks_async thread {_thread.get_ident()}: _process_callbacks_async")
        while _callback_queue:
            _log_debug("Processing callbacks queue...")
            try:
                callback, args = _callback_queue.popleft()
                if callback is not None:
                    #_log_debug(f"Executing callback {callback} with {len(args)} args")
                    #for i, arg in enumerate(args):
                    #    _log_debug(f"Arg {i}: {arg}")
                    try:
                        callback(*args)
                    except Exception as e:
                        _log_error(f"Error in callback {callback}: {e}")
                else:
                    _log_debug("Skipping None callback")
            except IndexError:
                _log_debug("Callback queue empty")
                break
        await asyncio.sleep(0.5)  # Yield to other tasks

class WebSocketApp:
    def __init__(
        self,
        url,
        header=None,
        on_open=None,
        on_reconnect=None,
        on_message=None,
        on_error=None,
        on_close=None,
        on_ping=None,
        on_pong=None,
        on_cont_message=None,
        keep_running=True,  # Ignored for compatibility
        get_mask_key=None,
        cookie=None,
        subprotocols=None,
        on_data=None,
        socket=None,
    ):
        self.url = url
        self.header = header if header is not None else {}
        self.cookie = cookie
        self.on_open = on_open
        self.on_reconnect = on_reconnect
        self.on_message = on_message
        self.on_data = on_data
        self.on_error = on_error
        self.on_close = on_close
        self.on_ping = on_ping
        self.on_pong = on_pong
        self.on_cont_message = on_cont_message
        self.get_mask_key = get_mask_key
        self.subprotocols = subprotocols
        self.prepared_socket = socket  # Ignored, not supported
        self.ws = None
        self.session = None
        self.running = False
        self.ping_interval = 0
        self.ping_timeout = None
        self.ping_payload = ""
        self.last_ping_tm = 0
        self.last_pong_tm = 0
        self.has_errored = False
        self._loop = asyncio.get_event_loop()

    def send(self, data, opcode=ABNF.OPCODE_TEXT):
        """Send a message."""
        if not self.ws or not self.running:
            _log_error("Send failed: Connection closed or not running")
            raise WebSocketConnectionClosedException("Connection is already closed.")
        _log_debug(f"Scheduling send: opcode={opcode}, data={str(data)[:20]}...")
        asyncio.create_task(self._send_async(data, opcode))

    def send_text(self, text_data):
        """Send UTF-8 text."""
        self.send(text_data, ABNF.OPCODE_TEXT)

    def send_bytes(self, data):
        """Send binary data."""
        self.send(data, ABNF.OPCODE_BINARY)

    async def close(self, **kwargs):
        """Close the WebSocket connection."""
        _log_debug("Close requested")
        self.running = False
        asyncio.create_task(self._close_async())

    async def _close_async(self):
        """Async close implementation."""
        _log_debug("Closing WebSocket connection")
        try:
            if self.ws and not self.ws.ws.closed:
                _log_debug("Sending WebSocket close frame")
                await self.ws.close()
            else:
                _log_debug("WebSocket already closed or not initialized")
            if self.session:
                _log_debug("Closing ClientSession")
                await self.session.__aexit__(None, None, None)
            else:
                _log_debug("No ClientSession to close")
        except Exception as e:
            _log_error(f"Error closing WebSocket: {e}")

    def _start_ping_task(self):
        """Start ping task."""
        if self.ping_interval:
            _log_debug(f"NOT Starting ping task with interval {self.ping_interval}s")
            asyncio.create_task(self._send_ping_async())

    def _stop_ping_thread(self):
        """No-op, ping handled in async task."""
        pass

    async def _send_ping_async(self):
        """Send periodic pings."""
        while self.running and self.ping_interval:
            self.last_ping_tm = time.time()
            try:
                if self.ws and not self.ws.ws.closed:
                    self.ping_payload = "ping"
                    _log_debug(f"Sending ping with payload: {self.ping_payload}")
                    await self.ws.send_bytes(self.ping_payload.encode() if isinstance(self.ping_payload, str) else self.ping_payload)
                else:
                    _log_debug("Skipping ping: WebSocket not connected")
            except Exception as e:
                _log_error(f"Failed to send ping: {e}")
            await asyncio.sleep(self.ping_interval)

    def ready(self):
        """Check if connection is active."""
        status = self.ws is not None and self.running
        _log_debug(f"Connection status: ready={status}")
        return status

    async def run_forever(
        self,
        sockopt=None,
        sslopt=None,
        ping_interval=0,
        ping_timeout=None,
        ping_payload="",
        http_proxy_host=None,
        http_proxy_port=None,
        http_no_proxy=None,
        http_proxy_auth=None,
        http_proxy_timeout=None,
        skip_utf8_validation=False,
        host=None,
        origin=None,
        dispatcher=None,
        suppress_origin=False,
        proxy_type=None,
        reconnect=None,
    ):
        """Run the WebSocket event loop in the main thread."""
        _log_debug("Starting run_forever")
        if sockopt or http_proxy_host or http_proxy_port or http_no_proxy or http_proxy_auth or proxy_type:
            raise WebSocketException("Proxy and sockopt not supported in MicroPython")
        if dispatcher:
            raise WebSocketException("Custom dispatcher not supported")
        if ping_timeout is not None and ping_timeout <= 0:
            raise WebSocketException("Ensure ping_timeout > 0")
        if ping_interval is not None and ping_interval < 0:
            raise WebSocketException("Ensure ping_interval >= 0")
        if ping_timeout and ping_interval and ping_interval <= ping_timeout:
            raise WebSocketException("Ensure ping_interval > ping_timeout")

        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.ping_payload = ping_payload
        self.running = True

        # Run the event loop in the main thread
        try:
            self._loop.run_until_complete(self._async_main())
        except KeyboardInterrupt:
            _log_debug("run_forever got KeyboardInterrupt")
            self.close()
            return False
        except Exception as e:
            _log_error(f"run_forever's _loop.run_until_complete() for {self.url} got general exception: {e}")
            self.has_errored = True
            self.running = False
            #return True
        _log_debug("run_forever completed")
        return self.has_errored

    async def _async_main(self):
        """Main async loop for WebSocket handling."""
        _log_debug("Starting _async_main")
        reconnect = 0  # Default, as RECONNECT may not be defined
        try:
            from websocket import RECONNECT
            reconnect = RECONNECT
        except ImportError:
            pass
        if reconnect is not None:
            reconnect = reconnect
        _log_debug(f"Reconnect interval set to {reconnect}s")

        # Start callback processing task
        try:
            # Make sure the queue is empty
            callback_task = asyncio.create_task(_process_callbacks_async())
            _log_debug("Started callback processing task")
        except Exception as e:
            print(f"websocket.py: create_ask(_process_callbacks_async()) had exception {e}")

        while self.running:
            _log_debug("Main loop iteration: self.running=True")
            try:
                await self._connect_and_run() # keep waiting for it, until finished
            except Exception as e:
                _log_error(f"_async_main's await self._connect_and_run() got exception: {e}")
                self.has_errored = True
                _run_callback(self.on_error, self, e)
                if not reconnect:
                    _log_debug("No reconnect configured, breaking loop")
                    break
                _log_debug(f"Reconnecting after error in {reconnect}s")
                await asyncio.sleep(reconnect)
                if self.on_reconnect:
                    _run_callback(self.on_reconnect, self)

        # Cleanup
        _log_debug("Initiating cleanup")
        _run_callback(self.on_close, self, None, None)
        await asyncio.sleep(1) # wait a bit for _process_callbacks_async to call on_close
        self.running = False
        callback_task.cancel()  # Stop callback task
        try:
            await callback_task
        except asyncio.CancelledError:
            _log_debug("Callback task cancelled")
        await self._close_async()
        _log_debug("_async_main completed")

    async def _connect_and_run(self):
        """Connect and handle WebSocket messages."""
        _log_debug(f"Connecting to {self.url}")
        ssl_context = None
        if self.url.startswith("wss://"):
            import ssl
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ssl_context.verify_mode = ssl.CERT_NONE
            _log_debug("Using SSL with no certificate verification")

        self.session = aiohttp.ClientSession(headers=self.header)
        async with self.session.ws_connect(self.url, ssl=ssl_context) as ws:
            if not ws:
                print("ERROR: ws_connect got None instead of ws object!")
                _run_callback(self.on_error, self, str(e))
                return

            self.ws = ws
            _log_debug("WebSocket connected, running on_open callback")
            _run_callback(self.on_open, self)
            #self._start_ping_task() this ping task isn't part of the protocol, pings are sent by the server

            async for msg in ws:
                import micropython
                print(f"websocket.py _connect_and_run thread stack used: {micropython.stack_use()}")
                _log_debug(f"websocket.py _connect_and_run received msg: type={msg.type}, length: {len(msg.data)} and data={str(msg.data)[:120]}...")
                if not self.running:
                    _log_debug("Not running, breaking message loop")
                    break

                # Handle ping/pong timeout
                if self.ping_timeout and self.last_ping_tm:
                    if time.time() - self.last_ping_tm > self.ping_timeout:
                        _log_error("Ping/pong timed out")
                        raise WebSocketTimeoutException("ping/pong timed out")

                # Process message
                if msg.type == WSMsgType.TEXT:
                    data = msg.data
                    _run_callback(self.on_data, self, data, ABNF.OPCODE_TEXT, True)
                    _run_callback(self.on_message, self, data)  # Standard websocket-client
                elif msg.type == WSMsgType.BINARY:
                    data = msg.data
                    _run_callback(self.on_data, self, data, ABNF.OPCODE_BINARY, True)
                    _run_callback(self.on_message, self, data)  # Standard websocket-client
                elif msg.type == WSMsgType.ERROR or ws.ws.closed:
                    _log_error("WebSocket error or closed")
                    raise WebSocketConnectionClosedException("WebSocket closed")
                elif msg.type == ABNF.OPCODE_PING:
                    data = msg.data
                    _run_callback(self.on_ping, self, data)

    async def _send_async(self, data, opcode):
        """Async send implementation."""
        _log_debug(f"Sending: opcode={opcode}, data={str(data)[:700]}")
        try:
            if opcode == ABNF.OPCODE_TEXT:
                await self.ws.send_str(data)
            elif opcode == ABNF.OPCODE_BINARY:
                await self.ws.send_bytes(data)
            else:
                raise WebSocketException(f"Unsupported opcode: {opcode}")
            _log_debug("Send successful")
        except Exception as e:
            _log_error(f"Send failed: {e}")
            _run_callback(self.on_error, self, e)

    def _callback(self, callback, *args):
        """Compatibility wrapper for callback execution."""
        _run_callback(callback, self, *args)

    def _get_close_args(self, close_frame):
        """Extract close code and reason (simplified)."""
        _log_debug("Getting close args (not supported)")
        return [None, None]  # aiohttp doesn't provide close frame details

    def create_dispatcher(self, ping_timeout, dispatcher, is_ssl, handleDisconnect):
        """Not supported."""
        _log_error("Custom dispatcher not supported")
        raise WebSocketException("Custom dispatcher not supported")
