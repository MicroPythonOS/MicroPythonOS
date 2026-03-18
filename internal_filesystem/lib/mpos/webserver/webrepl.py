# This module should be imported from REPL, not run from command line.
import binascii
import hashlib
import time
from micropython import const
try:
    import network
except ImportError:
    network = None
import os
import socket
import sys
import websocket
import _webrepl
from mpos import TaskManager

listen_s = None
client_s = None
accept_task = None
accept_loop_running = False
_dupterm_notify_cb = None
active_dupterm = None
_dupterm_input_buffer = bytearray()

DEBUG = 0
WEBSOCKET_DEBUG = True

_MP_STREAM_POLL = const(3)
_MP_STREAM_POLL_RD = const(0x0001)
_MP_STREAM_POLL_WR = const(0x0004)

_DEFAULT_STATIC_HOST = const("https://micropython.org/webrepl/")
static_host = _DEFAULT_STATIC_HOST


def _log_bytes(prefix, data, limit=80):
    if not WEBSOCKET_DEBUG:
        return
    if data is None:
        print(f"MODWEBREPL: {prefix}: <None>")
        return
    if isinstance(data, str):
        data = data.encode()
    preview = data[:limit]
    hex_preview = " ".join(f"{b:02x}" for b in preview)
    tail = "..." if len(data) > limit else ""
    print(f"MODWEBREPL: {prefix}: len={len(data)} hex={hex_preview}{tail}")



def _escape_payload_bytes(raw, limit=120):
    if raw is None:
        return ""
    preview = raw[:limit]
    parts = []
    for b in preview:
        if b == 0x0d:
            parts.append("\\r")
        elif b == 0x0a:
            parts.append("\\n")
        elif b == 0x09:
            parts.append("\\t")
        elif 0x20 <= b < 0x7f:
            parts.append(chr(b))
        else:
            parts.append(f"\\x{b:02x}")
    return "".join(parts)



def _log_decoded_payload(prefix, data, limit=120):
    if not WEBSOCKET_DEBUG:
        return
    if data is None:
        print(f"MODWEBREPL: {prefix}: <None>")
        return
    if isinstance(data, str):
        raw = data.encode()
    else:
        raw = data
    hex_preview = " ".join(f"{b:02x}" for b in raw[:limit])
    text_preview = _escape_payload_bytes(raw, limit=limit)
    tail = "..." if len(raw) > limit else ""
    print(
        f"MODWEBREPL: {prefix}: len={len(raw)} hex={hex_preview}{tail} text={text_preview}{tail}"
    )

def _decode_ws_frames_for_log(data):
    if data is None:
        return []
    if isinstance(data, str):
        data = data.encode()
    frames = []
    idx = 0
    data_len = len(data)
    while idx + 2 <= data_len:
        b1 = data[idx]
        b2 = data[idx + 1]
        idx += 2
        opcode = b1 & 0x0F
        masked = (b2 & 0x80) != 0
        payload_len = b2 & 0x7F
        if payload_len == 126:
            if idx + 2 > data_len:
                break
            payload_len = int.from_bytes(data[idx : idx + 2], "big")
            idx += 2
        elif payload_len == 127:
            if idx + 8 > data_len:
                break
            payload_len = int.from_bytes(data[idx : idx + 8], "big")
            idx += 8
        mask_key = None
        if masked:
            if idx + 4 > data_len:
                break
            mask_key = data[idx : idx + 4]
            idx += 4
        if idx + payload_len > data_len:
            break
        payload = data[idx : idx + payload_len]
        idx += payload_len
        if masked and mask_key is not None:
            payload = bytes(payload[i] ^ mask_key[i % 4] for i in range(payload_len))
        frames.append((opcode, payload))
    return frames


class _LoggedSocket:
    def __init__(self, sock, label="webrepl"):
        self._sock = sock
        self._label = label
        if WEBSOCKET_DEBUG:
            print(f"MODWEBREPL: {self._label} wrapper init")

    def makefile(self, *args, **kwargs):
        return self._sock.makefile(*args, **kwargs)

    def recv(self, size):
        data = self._sock.recv(size)
        _log_bytes(f"{self._label}.recv({size})", data)
        return data

    def read(self, size=-1):
        data = self._sock.read(size)
        _log_bytes(f"{self._label}.read({size})", data)
        return data

    def readinto(self, buf):
        read_len = self._sock.readinto(buf)
        if read_len is not None:
            _log_bytes(f"{self._label}.readinto", memoryview(buf)[:read_len])
        return read_len

    def write(self, data):
        _log_bytes(f"{self._label}.write", data)
        return self._sock.write(data)

    def send(self, data):
        _log_bytes(f"{self._label}.send", data)
        return self._sock.send(data)

    def sendall(self, data):
        _log_bytes(f"{self._label}.sendall", data)
        return self._sock.sendall(data)

    def ioctl(self, request, arg):
        if WEBSOCKET_DEBUG:
            print(f"MODWEBREPL: {self._label}.ioctl(request={request}, arg={arg})")
        return self._sock.ioctl(request, arg)

    def __getattr__(self, name):
        return getattr(self._sock, name)


class _LoggedDupterm:
    def __init__(self, wrapped, label="webrepl.dupterm"):
        self._wrapped = wrapped
        self._label = label
        if WEBSOCKET_DEBUG:
            print(f"MODWEBREPL: {self._label} wrapper init")

    def read(self, size=-1):
        data = self._wrapped.read(size)
        _log_bytes(f"{self._label}.read({size})", data)
        return data

    def write(self, data):
        _log_bytes(f"{self._label}.write", data)
        return self._wrapped.write(data)

    def ioctl(self, request, arg):
        if WEBSOCKET_DEBUG:
            print(f"MODWEBREPL: {self._label}.ioctl(request={request}, arg={arg})")
        return self._wrapped.ioctl(request, arg)

    def __getattr__(self, name):
        return getattr(self._wrapped, name)


class _PollableWebsocket:
    def __init__(self, wrapped, poll_sock, label="webrepl.poll"):
        self._wrapped = wrapped
        self._poll_sock = poll_sock
        self._label = label
        if WEBSOCKET_DEBUG:
            print(f"MODWEBREPL: {self._label} wrapper init")

    def read(self, size=-1):
        return self._wrapped.read(size)

    def write(self, data):
        return self._wrapped.write(data)

    def ioctl(self, request, arg):
        if request == _MP_STREAM_POLL:
            if WEBSOCKET_DEBUG:
                print(f"MODWEBREPL: {self._label}.poll request arg=0x{arg:x}")
            poll_sock = self._poll_sock
            if poll_sock is not None and hasattr(poll_sock, "ioctl"):
                try:
                    ret = poll_sock.ioctl(request, arg)
                except Exception as exc:
                    if WEBSOCKET_DEBUG:
                        print(f"MODWEBREPL: {self._label}.poll error: {exc!r}")
                    ret = 0
            else:
                ret = 0
            if ret == 0:
                ret = arg & (_MP_STREAM_POLL_RD | _MP_STREAM_POLL_WR)
                if WEBSOCKET_DEBUG:
                    print(f"MODWEBREPL: {self._label}.poll fallback ret=0x{ret:x}")
            else:
                if WEBSOCKET_DEBUG:
                    print(f"MODWEBREPL: {self._label}.poll ret=0x{ret:x}")
            return ret
        if WEBSOCKET_DEBUG:
            print(f"MODWEBREPL: {self._label}.ioctl passthrough request={request} arg={arg}")
        ret = self._wrapped.ioctl(request, arg)
        if WEBSOCKET_DEBUG:
            print(f"MODWEBREPL: {self._label}.ioctl passthrough ret={ret}")
        return ret

    def __getattr__(self, name):
        return getattr(self._wrapped, name)


class _NormalizeNewlineDupterm:
    def __init__(self, wrapped, label="webrepl.normalize"):
        self._wrapped = wrapped
        self._label = label

    def read(self, size=-1):
        data = self._wrapped.read(size)
        if data:
            normalized = _normalize_newlines(data)
            if normalized != data and WEBSOCKET_DEBUG:
                _log_bytes(f"{self._label}.read({size})", normalized)
            return normalized
        return data

    def write(self, data):
        return self._wrapped.write(data)

    def ioctl(self, request, arg):
        if WEBSOCKET_DEBUG:
            print(f"MODWEBREPL: {self._label}.ioctl(request={request}, arg={arg})")
        return self._wrapped.ioctl(request, arg)

    def __getattr__(self, name):
        return getattr(self._wrapped, name)


class _DuptermStream:
    def __init__(self, wrapped, label="webrepl.dupterm_stream"):
        self._wrapped = wrapped
        self._label = label
        if WEBSOCKET_DEBUG:
            print(f"MODWEBREPL: {self._label} wrapper init")

    def _drain_buffer(self, size=-1):
        global _dupterm_input_buffer
        if not _dupterm_input_buffer:
            return b""
        if size is None or size < 0:
            data = bytes(_dupterm_input_buffer)
            _dupterm_input_buffer[:] = b""
            return data
        if size == 0:
            return b""
        take = min(size, len(_dupterm_input_buffer))
        data = bytes(_dupterm_input_buffer[:take])
        del _dupterm_input_buffer[:take]
        return data

    def read(self, size=-1):
        data = self._drain_buffer(size)
        if data:
            return data
        return self._wrapped.read(size)

    def readinto(self, buf):
        data = self._drain_buffer(len(buf))
        if data:
            buf[: len(data)] = data
            return len(data)
        readinto = getattr(self._wrapped, "readinto", None)
        if readinto is not None:
            return readinto(buf)
        data = self._wrapped.read(len(buf))
        if data:
            buf[: len(data)] = data
            return len(data)
        return 0

    def write(self, data):
        return self._wrapped.write(data)

    def ioctl(self, request, arg):
        if request == _MP_STREAM_POLL:
            if _dupterm_input_buffer:
                return arg & _MP_STREAM_POLL_RD
            return self._wrapped.ioctl(request, arg)
        return self._wrapped.ioctl(request, arg)

    def __getattr__(self, name):
        return getattr(self._wrapped, name)



def _normalize_newlines(data):
    if data is None:
        return data
    if isinstance(data, str):
        data = data.encode()
    prev = None
    out = bytearray()
    for b in data:
        if b == 0x0a and prev != 0x0d:
            out.append(0x0d)
        else:
            out.append(b)
        prev = b
    return bytes(out)



def server_handshake(cl):
    req = cl.makefile("rwb", 0)
    # Skip HTTP GET line.
    l = req.readline()
    if WEBSOCKET_DEBUG:
        print(f"MODWEBREPL: handshake request line: {l!r}")
    if DEBUG:
        sys.stdout.write(repr(l))

    webkey = None
    upgrade = False
    websocket = False

    while True:
        l = req.readline()
        if not l:
            # EOF in headers.
            return False
        if l == b"\r\n":
            break
        if WEBSOCKET_DEBUG:
            print(f"MODWEBREPL: handshake header: {l!r}")
        if DEBUG:
            sys.stdout.write(l)
        h, v = [x.strip() for x in l.split(b":", 1)]
        if DEBUG:
            print((h, v))
        if h == b"Sec-WebSocket-Key":
            webkey = v
        elif h == b"Connection" and b"Upgrade" in v:
            upgrade = True
        elif h == b"Upgrade" and v == b"websocket":
            websocket = True

    if not (upgrade and websocket and webkey):
        return False

    if DEBUG:
        print("Sec-WebSocket-Key:", webkey, len(webkey))

    d = hashlib.sha1(webkey)
    d.update(b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11")
    respkey = d.digest()
    respkey = binascii.b2a_base64(respkey)[:-1]
    if DEBUG:
        print("respkey:", respkey)

    cl.send(
        b"""\
HTTP/1.1 101 Switching Protocols\r
Upgrade: websocket\r
Connection: Upgrade\r
Sec-WebSocket-Accept: """
    )
    cl.send(respkey)
    cl.send("\r\n\r\n")
    if WEBSOCKET_DEBUG:
        print("MODWEBREPL: handshake complete: 101 Switching Protocols sent")

    return True


def send_html(cl):
    cl.send(
        b"""\
HTTP/1.0 200 OK\r
\r
<base href=\""""
    )
    cl.send(static_host)
    cl.send(
        b"""\"></base>\r
<script src="webrepl_content.js"></script>\r
"""
    )
    cl.close()


def setup_conn(port, accept_handler):
    global listen_s
    listen_s = socket.socket()
    listen_s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    ai = socket.getaddrinfo("0.0.0.0", port)
    addr = ai[0][4]

    listen_s.bind(addr)
    listen_s.listen(1)
    accept_callback_set = False
    if accept_handler:
        try:
            listen_s.setsockopt(socket.SOL_SOCKET, 20, accept_handler)
            accept_callback_set = True
        except (TypeError, OSError):
            # Unix port doesn't support callback socket options; ignore.
            pass
    if network:
        for i in (network.WLAN.IF_AP, network.WLAN.IF_STA):
            iface = network.WLAN(i)
            if iface.active():
                print("WebREPL server started on http://%s:%d/" % (iface.ifconfig()[0], port))
    return listen_s, accept_callback_set


def _feed_dupterm_input(data):
    if not data:
        return
    if isinstance(data, str):
        data = data.encode()
    _dupterm_input_buffer.extend(data)


def set_active_dupterm(dupterm_obj):
    global active_dupterm
    active_dupterm = dupterm_obj
    if WEBSOCKET_DEBUG:
        if dupterm_obj is None:
            print("MODWEBREPL: active_dupterm cleared")
        else:
            print(
                "MODWEBREPL: active_dupterm set"
                f" id=0x{id(dupterm_obj):x} type={type(dupterm_obj)}"
            )


def get_active_dupterm():
    return active_dupterm


def _dupterm_notify_wrapper(sock):
    if WEBSOCKET_DEBUG:
        print(f"MODWEBREPL: dupterm_notify fired sock={sock!r}")
    if _dupterm_notify_cb:
        try:
            ret = _dupterm_notify_cb(sock)
            if WEBSOCKET_DEBUG:
                print("MODWEBREPL: dupterm_notify cb done")
            return ret
        except Exception as exc:
            if WEBSOCKET_DEBUG:
                print(f"MODWEBREPL: dupterm_notify cb error: {exc!r}")
            return None
    if WEBSOCKET_DEBUG:
        print("MODWEBREPL: dupterm_notify no cb")
    return None


async def _dupterm_pump(sock):
    if WEBSOCKET_DEBUG:
        print("MODWEBREPL: dupterm pump start")
    notified_once = False
    pump_iter = 0
    last_heartbeat_ms = time.ticks_ms()
    heartbeat_interval_ms = 1000
    while True:
        pump_iter += 1
        if WEBSOCKET_DEBUG:
            print(f"MODWEBREPL: dupterm pump iter={pump_iter}")
        now_ms = time.ticks_ms()
        if time.ticks_diff(now_ms, last_heartbeat_ms) >= heartbeat_interval_ms:
            last_heartbeat_ms = now_ms
            print("MODWEBREPL tick")
        if client_s is not sock:
            await TaskManager.sleep_ms(20)
            continue
        if _dupterm_notify_cb:
            try:
                _dupterm_notify_cb(None)
                if WEBSOCKET_DEBUG and not notified_once:
                    print("MODWEBREPL: dupterm pump notified")
                    notified_once = True
            except Exception as exc:
                if WEBSOCKET_DEBUG:
                    print(f"MODWEBREPL: dupterm_notify pump error iter={pump_iter}: {exc!r}")
                break
        else:
            if WEBSOCKET_DEBUG:
                print("MODWEBREPL: dupterm pump idle (no dupterm_notify)")
        await TaskManager.sleep_ms(20)


def accept_conn(listen_sock):
    global client_s, _dupterm_notify_cb
    cl, remote_addr = listen_sock.accept()
    if WEBSOCKET_DEBUG:
        print(f"MODWEBREPL: accept from: {remote_addr!r} ({type(remote_addr)})")
    logged_cl = _LoggedSocket(cl, label="webrepl.sock") if WEBSOCKET_DEBUG else cl

    if not server_handshake(logged_cl):
        send_html(cl)
        return False

    if WEBSOCKET_DEBUG:
        print("MODWEBREPL: checking existing dupterm")
    prev = os.dupterm(None)
    if WEBSOCKET_DEBUG:
        print(f"MODWEBREPL: dupterm was {'set' if prev else 'empty'}, restoring")
    os.dupterm(prev)
    if prev:
        print("\nConcurrent WebREPL connection from", remote_addr, "rejected")
        cl.close()
        return False
    print("\nWebREPL connection from:", remote_addr)
    client_s = cl

    if WEBSOCKET_DEBUG:
        print("MODWEBREPL: creating websocket wrapper")
    ws = websocket.websocket(logged_cl if WEBSOCKET_DEBUG else cl, True)
    if WEBSOCKET_DEBUG:
        print("MODWEBREPL: wrapping websocket poll")
    ws = _PollableWebsocket(ws, logged_cl if WEBSOCKET_DEBUG else cl)
    if WEBSOCKET_DEBUG:
        print("MODWEBREPL: wrapping with _webrepl")
    ws = _webrepl._webrepl(ws)
    if sys.platform in ("linux", "darwin"):
        if WEBSOCKET_DEBUG:
            print("MODWEBREPL: normalize newline on unix")
        ws = _NormalizeNewlineDupterm(ws)
        ws = _DuptermStream(ws)
    elif WEBSOCKET_DEBUG:
        print("MODWEBREPL: wrapping dupterm logger")
        ws = _LoggedDupterm(ws)

    cl.setblocking(False)
    if WEBSOCKET_DEBUG:
        print("MODWEBREPL: dupterm set")

    dupterm_notify = getattr(os, "dupterm_notify", None)
    if dupterm_notify:
        if WEBSOCKET_DEBUG:
            print("MODWEBREPL: dupterm_notify available, setting socket option")
        _dupterm_notify_cb = dupterm_notify
        try:
            cl.setsockopt(socket.SOL_SOCKET, 20, _dupterm_notify_wrapper)
            if WEBSOCKET_DEBUG:
                print("MODWEBREPL: dupterm_notify socket option set (wrapped)")
        except Exception as exc:
            if WEBSOCKET_DEBUG:
                print(f"MODWEBREPL: dupterm_notify socket option failed: {exc!r}")
    else:
        if WEBSOCKET_DEBUG:
            print("MODWEBREPL: dupterm_notify not available")

    if WEBSOCKET_DEBUG:
        print("MODWEBREPL: os.dupterm assign")
    os.dupterm(ws)
    set_active_dupterm(ws)
    if WEBSOCKET_DEBUG:
        print("MODWEBREPL: os.dupterm assigned")

    if WEBSOCKET_DEBUG:
        print("MODWEBREPL: start websocket frame pump")

    try:
        TaskManager.create_task(_dupterm_pump(cl))
        if WEBSOCKET_DEBUG:
            print("MODWEBREPL: dupterm pump task created")
    except Exception as exc:
        if WEBSOCKET_DEBUG:
            print(f"MODWEBREPL: dupterm pump task failed: {exc!r}")

    return True


def stop():
    global listen_s, client_s, accept_task, accept_loop_running, _dupterm_notify_cb
    accept_loop_running = False
    _dupterm_notify_cb = None
    set_active_dupterm(None)
    if WEBSOCKET_DEBUG:
        print("MODWEBREPL: stopping webrepl")
    os.dupterm(None)
    if client_s:
        if WEBSOCKET_DEBUG:
            print("MODWEBREPL: closing client socket")
        client_s.close()
    if listen_s:
        if WEBSOCKET_DEBUG:
            print("MODWEBREPL: closing listen socket")
        listen_s.close()
    accept_task = None
    if WEBSOCKET_DEBUG:
        print("MODWEBREPL: stop complete")


def _should_background_accept(accept_handler, accept_callback_set):
    if accept_handler is None:
        return False
    if accept_callback_set:
        return False
    return sys.platform in ("linux", "darwin")


def _start_background_accept(listen_sock, accept_handler):
    global accept_task, accept_loop_running
    try:
        listen_sock.setblocking(False)
    except Exception:
        pass

    async def _accept_loop():
        global accept_loop_running
        accept_loop_running = True
        if WEBSOCKET_DEBUG:
            print("MODWEBREPL: background accept loop start")
        while accept_loop_running:
            try:
                accept_handler(listen_sock)
            except OSError:
                pass
            except Exception as exc:
                print("WebREPL accept loop error:", exc)
            await TaskManager.sleep_ms(50)
        if WEBSOCKET_DEBUG:
            print("MODWEBREPL: background accept loop stop")

    accept_task = TaskManager.create_task(_accept_loop())


def start(port=8266, password=None, accept_handler=accept_conn):
    global static_host
    stop()
    webrepl_pass = password
    if webrepl_pass is None:
        try:
            import webrepl_cfg

            webrepl_pass = webrepl_cfg.PASS
            if hasattr(webrepl_cfg, "BASE"):
                static_host = webrepl_cfg.BASE
        except:
            print("WebREPL is not configured, run 'import webrepl_setup'")

    if WEBSOCKET_DEBUG:
        if webrepl_pass is None:
            print("MODWEBREPL: start with no password configured")
        else:
            print("MODWEBREPL: start with password configured")
    _webrepl.password(webrepl_pass)
    s, accept_callback_set = setup_conn(port, accept_handler)
    if WEBSOCKET_DEBUG:
        print(
            "MODWEBREPL: listening port=%d accept_handler=%s callback_set=%s"
            % (port, bool(accept_handler), accept_callback_set)
        )

    if accept_handler is None:
        print("Starting webrepl in foreground mode")
        # Run accept_conn to serve HTML until we get a websocket connection.
        while not accept_conn(s):
            pass
    elif _should_background_accept(accept_handler, accept_callback_set):
        _start_background_accept(s, accept_handler)
        if password is None:
            print("Started webrepl in normal mode (background accept on Unix)")
        else:
            print("Started webrepl in manual override mode (background accept on Unix)")
    elif password is None:
        print("Started webrepl in normal mode")
    else:
        print("Started webrepl in manual override mode")


def start_foreground(port=8266, password=None):
    start(port, password, None)
