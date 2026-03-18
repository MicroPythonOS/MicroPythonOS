import os
import socket
import sys
import time
import uio

from mpos import TaskManager

import _webrepl
from . import webrepl
import websocket

WEBREPL_HTML_PATH = "builtin/html/webrepl_inlined_minified.html"
'''
# Unused as these files are minified and inlined:
#WEBREPL_HTML_PATH = "/builtin/html/webrepl.html"
WEBREPL_CONTENT_PATH = "/builtin/html/webrepl.js"
WEBREPL_TERM_PATH = "/builtin/html/term.js"
WEBREPL_CSS_PATH = "/builtin/html/webrepl.css"
WEBREPL_FILE_SAVER_PATH = "/builtin/html/FileSaver.js"
'''

WEBREPL_ASSETS = {
    b"/": (WEBREPL_HTML_PATH, b"text/html"),
    b"/index.html": (WEBREPL_HTML_PATH, b"text/html"),
    #b"/webrepl.css": (WEBREPL_CSS_PATH, b"text/css"),
    #b"/webrepl.js": (WEBREPL_CONTENT_PATH, b"application/javascript"),
    #b"/term.js": (WEBREPL_TERM_PATH, b"application/javascript"),
    #b"/FileSaver.js": (WEBREPL_FILE_SAVER_PATH, b"application/javascript"),
}


class _MakefileSocket:
    def __init__(self, sock, raw_request):
        self._sock = sock
        self._raw_request = raw_request

    def makefile(self, *args, **kwargs):
        return uio.BytesIO(self._raw_request)

    def __getattr__(self, name):
        return getattr(self._sock, name)


def _read_http_request(cl):
    req = cl.makefile("rwb", 0)
    first_line = req.readline()
    if not first_line:
        return None, None, b""

    raw_request = first_line
    headers = {}
    while True:
        line = req.readline()
        if not line:
            break
        raw_request += line
        if line == b"\r\n":
            break
        if b":" in line:
            key, value = line.split(b":", 1)
            headers[key.strip().lower()] = value.strip().lower()

    parts = first_line.split()
    path = parts[1] if len(parts) >= 2 else b"/"
    if b"?" in path:
        path = path.split(b"?", 1)[0]

    return path, headers, raw_request


def _is_websocket_request(headers):
    connection = headers.get(b"connection", b"")
    upgrade = headers.get(b"upgrade", b"")
    return b"upgrade" in connection and upgrade == b"websocket"


def _send_response(cl, status, content_type, body):
    cl.send(b"HTTP/1.0 " + status + b"\r\n")
    cl.send(b"Server: MicroPythonOS\r\n")
    cl.send(b"Content-Type: " + content_type + b"\r\n")
    cl.send(b"Content-Length: %d\r\n\r\n" % len(body))
    cl.send(body)
    cl.close()


def _send_file_response(cl, path, content_type):
    try:
        with open(path, "rb") as handle:
            body = handle.read()
    except OSError:
        _send_response(cl, b"404 Not Found", b"text/plain", b"Not Found")
        return False

    _send_response(cl, b"200 OK", content_type, body)
    return False


def _start_webrepl_session(cl, remote_addr):
    _start_pump_test_task()
    print("\nWebREPL connection from:", remote_addr)

    prev = os.dupterm(None)
    os.dupterm(prev)
    if prev:
        print("\nConcurrent WebREPL connection from", remote_addr, "rejected")
        try:
            cl.close()
        except Exception:
            pass
        return False

    webrepl.client_s = cl

    if webrepl.WEBSOCKET_DEBUG:
        print("webrepl_http: creating websocket wrapper")
        print(
            "webrepl_http: socket capabilities read=%s write=%s recv=%s send=%s ioctl=%s"
            % (
                hasattr(cl, "read"),
                hasattr(cl, "write"),
                hasattr(cl, "recv"),
                hasattr(cl, "send"),
                hasattr(cl, "ioctl"),
            )
        )
    try:
        ws = websocket.websocket(cl, True)
    except Exception as exc:
        print("webrepl_http: websocket wrapper creation failed:", exc)
        print("webrepl_http: socket type:", type(cl))
        print("webrepl_http: socket repr:", cl)
        print(
            "webrepl_http: socket attrs:"
            " read=%s write=%s recv=%s send=%s ioctl=%s makefile=%s"
            % (
                hasattr(cl, "read"),
                hasattr(cl, "write"),
                hasattr(cl, "recv"),
                hasattr(cl, "send"),
                hasattr(cl, "ioctl"),
                hasattr(cl, "makefile"),
            )
        )
        try:
            import sys as _sys

            _sys.print_exception(exc)
        except Exception:
            pass
        raise
    if webrepl.WEBSOCKET_DEBUG:
        print("webrepl_http: wrapping with _webrepl")
    ws = _webrepl._webrepl(ws)
    if webrepl.WEBSOCKET_DEBUG:
        if sys.platform in ("linux", "darwin"):
            print("webrepl_http: skip dupterm logger on unix (stream protocol required)")
        else:
            print("webrepl_http: wrapping dupterm logger")
            ws = webrepl._LoggedDupterm(ws)
    try:
        cl.setblocking(False)
    except Exception as exc:
        print("webrepl_http: failed to set non-blocking socket:", exc)
    if webrepl.WEBSOCKET_DEBUG:
        print("webrepl_http: dupterm set")
    if hasattr(os, "dupterm_notify"):
        try:
            cl.setsockopt(socket.SOL_SOCKET, 20, os.dupterm_notify)
        except OSError as exc:
            print("webrepl_http: dupterm_notify sockopt failed:", exc)
    try:
        os.dupterm(ws)
        webrepl.set_active_dupterm(ws)
        if webrepl.WEBSOCKET_DEBUG:
            print("webrepl_http: active dupterm set")
    except OSError as exc:
        print("webrepl_http: dupterm failed:", exc)
        webrepl.set_active_dupterm(None)
        try:
            cl.close()
        except Exception:
            pass
        return False

    if webrepl.WEBSOCKET_DEBUG and sys.platform in ("linux", "darwin"):
        _start_websocket_peek(cl)

    return True


_ws_peek_task = None
_ws_peek_running = False

_pump_test_task = None
_pump_test_running = False
_pump_notify_interval_ms = 50
_pump_log_interval_ms = 1000
_pump_read_interval_ms = 250


def _start_pump_test_task():
    global _pump_test_task, _pump_test_running
    if _pump_test_running:
        return

    async def _pump_test_loop():
        global _pump_test_running
        _pump_test_running = True
        last_log_ms = time.ticks_ms()
        last_poll_log_ms = last_log_ms
        last_read_ms = last_log_ms
        last_diag_ms = last_log_ms
        while _pump_test_running:
            sock = webrepl.client_s
            now_ms = time.ticks_ms()
            if sock is None:
                if time.ticks_diff(now_ms, last_log_ms) >= _pump_log_interval_ms:
                    last_log_ms = now_ms
                    print("WEBREPL_HTTP_PUMP: idle (no client)")
                await TaskManager.sleep_ms(_pump_notify_interval_ms)
                continue

            dupterm_getter = getattr(webrepl, "get_active_dupterm", None)
            dupterm_obj = dupterm_getter() if dupterm_getter else None
            dupterm_ioctl = getattr(dupterm_obj, "ioctl", None) if dupterm_obj else None
            if time.ticks_diff(now_ms, last_log_ms) >= _pump_log_interval_ms:
                last_log_ms = now_ms
                if dupterm_obj is None:
                    print("WEBREPL_HTTP_PUMP: active dupterm missing")
                else:
                    print(
                        "WEBREPL_HTTP_PUMP: active dupterm"
                        f" id=0x{id(dupterm_obj):x} type={type(dupterm_obj)} ioctl={dupterm_ioctl is not None}"
                    )
            if dupterm_ioctl is not None:
                poll_ret = None
                try:
                    poll_req = getattr(webrepl, "_MP_STREAM_POLL", 3)
                    poll_rd = getattr(webrepl, "_MP_STREAM_POLL_RD", 0x0001)
                    poll_ret = dupterm_ioctl(poll_req, poll_rd)
                    if time.ticks_diff(now_ms, last_poll_log_ms) >= _pump_log_interval_ms:
                        last_poll_log_ms = now_ms
                        print(
                            "WEBREPL_HTTP_PUMP: dupterm ioctl poll"
                            f" ret=0x{poll_ret:x} req=0x{poll_req:x} rd=0x{poll_rd:x}"
                        )
                except Exception as exc:
                    if time.ticks_diff(now_ms, last_poll_log_ms) >= _pump_log_interval_ms:
                        last_poll_log_ms = now_ms
                        print("WEBREPL_HTTP_PUMP: dupterm ioctl poll error", exc)
                if poll_ret is not None and (poll_ret & getattr(webrepl, "_MP_STREAM_POLL_RD", 0x0001)):
                    if time.ticks_diff(now_ms, last_read_ms) >= _pump_read_interval_ms:
                        last_read_ms = now_ms
                        try:
                            readinto = getattr(dupterm_obj, "readinto", None)
                            if readinto is not None:
                                buf = bytearray(1)
                                got = readinto(buf)
                                print(
                                    "WEBREPL_HTTP_PUMP: dupterm readinto(1)"
                                    f" got={got} data={buf[:got]!r}"
                                )
                            else:
                                data = dupterm_obj.read(1)
                                print(
                                    "WEBREPL_HTTP_PUMP: dupterm read(1)"
                                    f" data={data!r}"
                                )
                        except Exception as exc:
                            print("WEBREPL_HTTP_PUMP: dupterm read error", exc)
            else:
                if dupterm_obj is not None and time.ticks_diff(now_ms, last_diag_ms) >= _pump_log_interval_ms:
                    last_diag_ms = now_ms
                    read_fn = getattr(dupterm_obj, "read", None)
                    if read_fn is not None:
                        try:
                            data = read_fn(0)
                            print("WEBREPL_HTTP_PUMP: dupterm read(0) diagnostic", data)
                        except Exception as exc:
                            try:
                                data = read_fn(1)
                                print("WEBREPL_HTTP_PUMP: dupterm read(1) diagnostic", data)
                            except Exception as exc_inner:
                                print(
                                    "WEBREPL_HTTP_PUMP: dupterm read diagnostic error",
                                    exc,
                                    exc_inner,
                                )
                    else:
                        print("WEBREPL_HTTP_PUMP: dupterm missing read attribute")
                dupterm_notify = getattr(os, "dupterm_notify", None)
                if dupterm_notify is not None:
                    try:
                        dupterm_notify(None)
                        if time.ticks_diff(now_ms, last_log_ms) >= _pump_log_interval_ms:
                            last_log_ms = now_ms
                            print("WEBREPL_HTTP_PUMP: fallback dupterm_notify")
                    except Exception as exc:
                        if time.ticks_diff(now_ms, last_log_ms) >= _pump_log_interval_ms:
                            last_log_ms = now_ms
                            print("WEBREPL_HTTP_PUMP: dupterm_notify error", exc)
                elif hasattr(sock, "ioctl"):
                    try:
                        poll_req = 3
                        poll_rd = 0x0001
                        sock.ioctl(poll_req, poll_rd)
                        if time.ticks_diff(now_ms, last_log_ms) >= _pump_log_interval_ms:
                            last_log_ms = now_ms
                            print("WEBREPL_HTTP_PUMP: fallback socket ioctl poll")
                    except Exception as exc:
                        if time.ticks_diff(now_ms, last_log_ms) >= _pump_log_interval_ms:
                            last_log_ms = now_ms
                            print("WEBREPL_HTTP_PUMP: socket ioctl poll error", exc)
                else:
                    if time.ticks_diff(now_ms, last_log_ms) >= _pump_log_interval_ms:
                        last_log_ms = now_ms
                        print("WEBREPL_HTTP_PUMP: no active dupterm or dupterm_notify")

            await TaskManager.sleep_ms(_pump_notify_interval_ms)

    _pump_test_task = TaskManager.create_task(_pump_test_loop())


def _start_websocket_peek(sock):
    global _ws_peek_task, _ws_peek_running
    if _ws_peek_running:
        return

    async def _peek_loop():
        global _ws_peek_running
        _ws_peek_running = True
        last = b""
        peek_flag = getattr(socket, "MSG_PEEK", None)
        while _ws_peek_running:
            if webrepl.client_s is not sock:
                break
            try:
                if peek_flag is not None:
                    try:
                        data = sock.recv(256, peek_flag)
                    except TypeError:
                        data = sock.recv(256)
                else:
                    data = sock.recv(256)
                if data:
                    if data != last:
                        last = data
                        webrepl._log_bytes("webrepl_http.sock.recv", data)
                        for opcode, payload in webrepl._decode_ws_frames_for_log(data):
                            if opcode in (1, 2):
                                webrepl._log_decoded_payload(
                                    "webrepl_http.ws.payload", payload
                                )
                                webrepl._feed_dupterm_input(payload)
                else:
                    break
            except OSError:
                pass
            await TaskManager.sleep_ms(50)
        _ws_peek_running = False

    _ws_peek_task = TaskManager.create_task(_peek_loop())


def accept_handler(listen_sock):
    cl, remote_addr = listen_sock.accept()
    print("\webrepl_http connection from:", remote_addr)
    if webrepl.WEBSOCKET_DEBUG:
        print(f"webrepl_http: path read starting for {remote_addr!r}")
    try:
        path, headers, raw_request = _read_http_request(cl)
        if webrepl.WEBSOCKET_DEBUG:
            print(f"webrepl_http: path={path!r} headers={headers}")
        if not path:
            cl.close()
            return False

        if _is_websocket_request(headers):
            if webrepl.WEBSOCKET_DEBUG:
                print("webrepl_http: websocket upgrade requested")
            if not webrepl.server_handshake(_MakefileSocket(cl, raw_request)):
                cl.close()
                return False
            return _start_webrepl_session(cl, remote_addr)

        if path in WEBREPL_ASSETS:
            asset_path, content_type = WEBREPL_ASSETS[path]
            return _send_file_response(cl, asset_path, content_type)

        _send_response(cl, b"404 Not Found", b"text/plain", b"Not Found")
        return False
    except Exception as exc:
        print("webrepl_http: error handling connection:", exc)
        try:
            cl.close()
        except Exception:
            pass
        return False
