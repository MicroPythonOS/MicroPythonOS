import os
import socket
import uio
import struct

import _webrepl
from . import webrepl
import websocket
import lvgl as lv

from mpos.ui.display_metrics import DisplayMetrics

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


def _build_bmp_header(width, height, pixel_data_size):
    bmp_header_size = 54
    file_size = bmp_header_size + pixel_data_size
    header = bytearray(bmp_header_size)
    header[0:2] = b"BM"
    header[2:6] = struct.pack("<I", file_size)
    header[10:14] = struct.pack("<I", bmp_header_size)
    header[14:18] = struct.pack("<I", 40)
    header[18:22] = struct.pack("<I", width)
    header[22:26] = struct.pack("<i", -height)
    header[26:28] = struct.pack("<H", 1)
    header[28:30] = struct.pack("<H", 24)
    header[30:34] = struct.pack("<I", 0)
    header[34:38] = struct.pack("<I", pixel_data_size)
    return header


def _snapshot_to_bmp():
    width = DisplayMetrics.width()
    height = DisplayMetrics.height()
    rgb_size = width * height * 3
    row_stride = ((width * 3 + 3) // 4) * 4
    pixel_data_size = row_stride * height

    rgb_buffer = bytearray(rgb_size)
    image_dsc = lv.image_dsc_t()
    lv.snapshot_take_to_buf(
        lv.screen_active(),
        lv.COLOR_FORMAT.RGB888,
        image_dsc,
        rgb_buffer,
        rgb_size,
    )

    bmp = bytearray(54 + pixel_data_size)
    bmp[0:54] = _build_bmp_header(width, height, pixel_data_size)

    view = memoryview(bmp)[54:]
    if row_stride == width * 3:
        view[:rgb_size] = rgb_buffer
    else:
        for y in range(height):
            src_start = y * width * 3
            src_end = src_start + width * 3
            dest_start = y * row_stride
            view[dest_start : dest_start + width * 3] = rgb_buffer[src_start:src_end]

    return bmp


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
    print("\nWebREPL connection from:", remote_addr)
    webrepl.client_s = cl

    ws = websocket.websocket(cl, True)
    ws = _webrepl._webrepl(ws)
    cl.setblocking(False)
    if hasattr(os, "dupterm_notify"):
        cl.setsockopt(socket.SOL_SOCKET, 20, os.dupterm_notify)
    os.dupterm(ws)

    return True


def accept_handler(listen_sock):
    cl, remote_addr = listen_sock.accept()
    print("\webrepl_http connection from:", remote_addr)
    try:
        path, headers, raw_request = _read_http_request(cl)
        if not path:
            cl.close()
            return False

        if _is_websocket_request(headers):
            if not webrepl.server_handshake(_MakefileSocket(cl, raw_request)):
                cl.close()
                return False
            return _start_webrepl_session(cl, remote_addr)

        if path in WEBREPL_ASSETS:
            asset_path, content_type = WEBREPL_ASSETS[path]
            return _send_file_response(cl, asset_path, content_type)

        if path == b"/screenshot.bmp":
            bmp = _snapshot_to_bmp()
            _send_response(cl, b"200 OK", b"image/bmp", bmp)
            return False

        _send_response(cl, b"404 Not Found", b"text/plain", b"Not Found")
        return False
    except Exception as exc:
        print("webrepl_http: error handling connection:", exc)
        try:
            cl.close()
        except Exception:
            pass
        return False
