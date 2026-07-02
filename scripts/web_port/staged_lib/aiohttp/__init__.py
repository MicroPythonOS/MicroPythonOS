# Browser (Emscripten) aiohttp shim — HTTP(S) via the _webnet fetch() bridge.
#
# Raw TCP sockets are unavailable in the browser (MICROPY_PY_SOCKET is off), so
# the device's socket-based aiohttp cannot run here. This shim implements the
# subset of the aiohttp client API that MicroPythonOS uses, on top of the
# non-blocking _webnet native module. Polling yields to the asyncio loop so the
# LVGL/UI task handler keeps running during requests.

import asyncio
import json as _json
import time
import _webnet

# WSMsgType comes from the (import-clean) device aiohttp_ws module; the browser
# WebSocket transport is implemented below on top of the _webnet native bridge.
from .aiohttp_ws import WSMsgType  # noqa: F401

HttpVersion10 = "HTTP/1.0"
HttpVersion11 = "HTTP/1.1"

__all__ = (
    "ClientSession",
    "ClientResponse",
    "ClientWebSocketResponse",
    "WebSocketClient",
    "WSMsgType",
    "HttpVersion10",
    "HttpVersion11",
)

_POLL_MS = 20


class _Content:
    # Minimal StreamReader-like object serving an in-memory body in chunks.
    def __init__(self, body):
        self._body = body
        self._pos = 0

    async def read(self, n=-1):
        if self._pos >= len(self._body):
            return b""
        if n is None or n < 0:
            chunk = self._body[self._pos:]
            self._pos = len(self._body)
        else:
            chunk = self._body[self._pos:self._pos + n]
            self._pos += len(chunk)
        return chunk

    async def readexactly(self, n):
        return await self.read(n)

    async def readline(self):
        if self._pos >= len(self._body):
            return b""
        nl = self._body.find(b"\n", self._pos)
        if nl < 0:
            chunk = self._body[self._pos:]
            self._pos = len(self._body)
        else:
            chunk = self._body[self._pos:nl + 1]
            self._pos = nl + 1
        return chunk


class ClientResponse:
    def __init__(self, handle, status, headers, body):
        self._handle = handle
        self.status = status
        self.headers = headers
        self.url = None
        self._body = body
        self.content = _Content(body)

    def _get_header(self, name, default=None):
        for k in self.headers:
            if k.lower() == name.lower():
                return self.headers[k]
        return default

    async def read(self, sz=-1):
        return self._body

    async def text(self, encoding="utf-8"):
        return self._body.decode(encoding)

    async def json(self):
        return _json.loads(self._body)

    def release(self):
        if self._handle is not None:
            _webnet.free(self._handle)
            self._handle = None

    def __repr__(self):
        return "<ClientResponse %s %s>" % (self.status, self.headers)


class _RequestContextManager:
    def __init__(self, coro):
        self._coro = coro
        self._resp = None

    async def __aenter__(self):
        self._resp = await self._coro
        return self._resp

    async def __aexit__(self, *args):
        if self._resp is not None:
            self._resp.release()
        return False

    def __await__(self):
        return self._coro.__await__()


# --- WebSocket support (browser WebSocket via the _webnet bridge) -----------

_WS_TEXT = 1
_WS_BINARY = 2
_WS_CLOSE = 8


class _WSMessage:
    def __init__(self, type, data):
        self.type = type
        self.data = data


class WebSocketClient:
    # Browser-backed WebSocket. Provides the small surface MPOS reads via
    # `ws.ws` (the .closed flag and the TEXT/BINARY/CLOSE opcodes) plus the
    # receive()/send()/close() coroutines used by ClientWebSocketResponse.
    CLOSE = _WS_CLOSE
    TEXT = _WS_TEXT
    BINARY = _WS_BINARY

    def __init__(self, handle):
        self._handle = handle
        self.closed = False

    async def receive(self):
        # Drain any queued message first, then report closure. Non-blocking:
        # yields to the asyncio loop so the UI keeps running.
        while True:
            t = _webnet.ws_peek_type(self._handle)
            if t:
                data = _webnet.ws_read(self._handle)
                if t == _WS_TEXT:
                    data = str(data, "utf-8")
                return t, data
            if _webnet.ws_state(self._handle) == 3:  # CLOSED
                self.closed = True
                return self.CLOSE, b""
            await asyncio.sleep_ms(_POLL_MS)

    async def send(self, data, opcode=None):
        if isinstance(data, str):
            _webnet.ws_send_text(self._handle, data)
        else:
            _webnet.ws_send_bytes(self._handle, data)

    async def close(self):
        if not self.closed:
            self.closed = True
            _webnet.ws_close(self._handle)


class ClientWebSocketResponse:
    def __init__(self, wsclient):
        self.ws = wsclient

    def __aiter__(self):
        return self

    async def __anext__(self):
        t, data = await self.ws.receive()
        if (not data and t == self.ws.CLOSE) or self.ws.closed:
            raise StopAsyncIteration
        return _WSMessage(t, data)

    async def receive(self):
        t, data = await self.ws.receive()
        return _WSMessage(t, data)

    async def close(self):
        await self.ws.close()

    async def send_str(self, data):
        if not isinstance(data, str):
            raise TypeError("data argument must be str (%r)" % type(data))
        await self.ws.send(data)

    async def send_bytes(self, data):
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("data argument must be byte-ish (%r)" % type(data))
        await self.ws.send(data)

    async def send_json(self, data):
        await self.send_str(_json.dumps(data))

    async def receive_str(self):
        msg = await self.receive()
        if msg.type != self.ws.TEXT:
            raise TypeError("Received message %s:%r is not str" % (msg.type, msg.data))
        return msg.data

    async def receive_bytes(self):
        msg = await self.receive()
        if msg.type != self.ws.BINARY:
            raise TypeError("Received message %s:%r is not bytes" % (msg.type, msg.data))
        return msg.data

    async def receive_json(self):
        return _json.loads(await self.receive_str())


class _WSRequestContextManager:
    def __init__(self, url, protocols):
        self._url = url
        self._protocols = protocols
        self._resp = None

    async def _connect(self):
        handle = _webnet.ws_open(self._url, _json.dumps(self._protocols or []))
        # Wait for the socket to open (or fail), yielding to the asyncio loop.
        while True:
            state = _webnet.ws_state(handle)
            if state == 1:  # OPEN
                break
            if state == 3:  # CLOSED before opening => failed
                err = _webnet.ws_error(handle) or "websocket connection failed"
                _webnet.ws_free(handle)
                raise OSError("ws_connect failed: " + err)
            await asyncio.sleep_ms(_POLL_MS)
        self._resp = ClientWebSocketResponse(WebSocketClient(handle))
        return self._resp

    async def __aenter__(self):
        return await self._connect()

    async def __aexit__(self, *args):
        if self._resp is not None:
            await self._resp.close()
            _webnet.ws_free(self._resp.ws._handle)
        return False

    def __await__(self):
        return self._connect().__await__()


class ClientSession:
    def __init__(self, base_url="", headers=None, **kwargs):
        self._base_url = base_url or ""
        self._base_headers = dict(headers) if headers else {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def close(self):
        pass

    async def _request(self, method, url, data=None, json=None, headers=None,
                       timeout=None, **kwargs):
        full = self._base_url + url
        merged = dict(self._base_headers)
        if headers:
            merged.update(headers)

        body = None
        if json is not None:
            body = _json.dumps(json).encode()
            if not any(k.lower() == "content-type" for k in merged):
                merged["Content-Type"] = "application/json"
        elif data is not None:
            body = data if isinstance(data, (bytes, bytearray)) else str(data).encode()

        handle = _webnet.fetch_start(method, full, _json.dumps(merged), body)

        deadline = None
        if timeout:
            deadline = time.ticks_add(time.ticks_ms(), int(timeout * 1000))

        # Non-blocking poll: yield to the asyncio loop so the UI stays live.
        while True:
            state = _webnet.poll(handle)
            if state == 1:
                break
            if state == -1:
                err = _webnet.error(handle)
                _webnet.free(handle)
                raise OSError("fetch failed: " + err)
            if deadline is not None and time.ticks_diff(time.ticks_ms(), deadline) > 0:
                _webnet.free(handle)
                raise OSError("fetch timeout")
            await asyncio.sleep_ms(_POLL_MS)

        status = _webnet.status(handle)
        try:
            hdrs = _json.loads(_webnet.headers(handle))
        except Exception:
            hdrs = {}
        body_bytes = _webnet.body(handle)
        resp = ClientResponse(handle, status, hdrs, body_bytes)
        resp.url = full
        return resp

    def request(self, method, url, **kwargs):
        return _RequestContextManager(self._request(method, url, **kwargs))

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def put(self, url, **kwargs):
        return self.request("PUT", url, **kwargs)

    def delete(self, url, **kwargs):
        return self.request("DELETE", url, **kwargs)

    def ws_connect(self, url, *, protocols=(), headers=None, ssl=None, **kwargs):
        # Browser WebSocket. Note: the browser WebSocket API cannot set custom
        # request headers, so `headers` (and the session headers) are ignored;
        # `ssl` is handled automatically for wss:// URLs.
        return _WSRequestContextManager(url, list(protocols))
