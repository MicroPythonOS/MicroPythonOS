#!/usr/bin/env python3
"""
MicroPythonOS Controller — Drive MicroPythonOS from CPython.

Usage:
    from mpos_controller import MPOSController

    with MPOSController() as mpos:
        out = mpos.exec("print('hello')")
        val = mpos.eval("1 + 1")
        bmp = mpos.screenshot()
        print(mpos.get_visible_text())
"""

import ast
import json
import os
import pty
import select
import signal
import struct
import subprocess
import sys
import time
import platform


# ── Helpers ──────────────────────────────────────────────────────────

def _resolve_binary(target=None):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.normpath(os.path.join(script_dir, ".."))
    build_dir = os.path.join(repo_root, "lvgl_micropython", "build")
    if target:
        path = os.path.join(build_dir, target)
        if os.path.exists(path):
            return os.path.abspath(path)
    for candidate in ["lvgl_micropy_unix", "lvgl_micropy_macOS"]:
        path = os.path.join(build_dir, candidate)
        if os.path.exists(path):
            return os.path.abspath(path)
    raise FileNotFoundError(
        f"No MicroPythonOS binary in {build_dir}. "
        f"Run ./scripts/build_mpos.sh unix first."
    )


def _resolve_cwd():
    d = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(d, "..", "internal_filesystem"))


def _build_bmp(width, height, rgb888_pixels):
    row_stride = (width * 3 + 3) // 4 * 4
    pixel_data_size = row_stride * height
    file_size = 54 + pixel_data_size
    header = bytearray(54)
    header[0:2] = b"BM"
    header[2:6] = struct.pack("<I", file_size)
    header[10:14] = struct.pack("<I", 54)
    header[14:18] = struct.pack("<I", 40)
    header[18:22] = struct.pack("<I", width)
    header[22:26] = struct.pack("<i", -height)
    header[26:28] = struct.pack("<H", 1)
    header[28:30] = struct.pack("<H", 24)
    header[30:34] = struct.pack("<I", 0)
    header[34:38] = struct.pack("<I", pixel_data_size)
    bmp = bytearray(header)
    if row_stride == width * 3:
        bmp.extend(rgb888_pixels)
    else:
        for y in range(height):
            s = y * width * 3
            bmp.extend(rgb888_pixels[s:s + width * 3])
            bmp.extend(b"\x00" * (row_stride - width * 3))
    return bytes(bmp)


# ── Stream ──────────────────────────────────────────────────────────

class _PTYStream:
    def __init__(self, fd):
        self.fd = fd

    def read(self, n=1):
        return os.read(self.fd, n)

    def write(self, data):
        os.write(self.fd, data)

    def fileno(self):
        return self.fd


class _SerialStream:
    def __init__(self, ser):
        self.ser = ser

    def read(self, n=1):
        return self.ser.read(n) or b""

    def write(self, data):
        self.ser.write(data)

    def fileno(self):
        return self.ser.fileno()


# ── aioREPL Client ──────────────────────────────────────────────────

SENTINEL = "~~~MPOS~~~"


class AIOREPLClient:
    """Talk to MicroPythonOS through the aioREPL inside TaskManager."""

    def __init__(self, stream):
        self.stream = stream

    def _data_waiting(self, timeout=0):
        r, _, _ = select.select([self.stream], [], [], timeout)
        return bool(r)

    def _drain(self, timeout=0.5):
        data = b""
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            if self._data_waiting(0.05):
                chunk = self.stream.read(4096)
                if chunk:
                    data += chunk
            else:
                break
        return data

    def read_until(self, ending, timeout=30):
        data = b""
        t0 = time.monotonic()
        while True:
            if data.endswith(ending):
                break
            if not self._data_waiting(0.01):
                if timeout is not None and time.monotonic() - t0 > timeout:
                    break
                continue
            chunk = self.stream.read(1)
            if not chunk:
                continue
            data += chunk
        return data

    def wait_for_boot(self, timeout=30):
        t0 = time.monotonic()
        self._drain(0.3)
        while time.monotonic() - t0 < timeout:
            self.stream.write(b"\x03")
            time.sleep(0.2)
            if self._data_waiting(0.3):
                data = self.stream.read(4096)
                if b">>> " in data:
                    self.stream.write(b"\n")
                    time.sleep(0.3)
                    self._drain(0.5)
                    return
        data = self.read_until(b">>> ", timeout=5)
        if not data.endswith(b">>> "):
            raise TimeoutError(
                "aioREPL prompt not found.\n" + data.decode("utf-8", "replace")[-2000:]
            )
        self.stream.write(b"\n")
        time.sleep(0.5)
        self._drain(1.0)

    def exec(self, code, timeout=30):
        """
        Execute *code* (single line, or semicolon-joined) and return stdout output.

        A sentinel ``print()`` is injected before *code* to delimit
        echoed input from actual output.
        """
        self._drain(0.2)
        wrapped = "print('{}'); ".format(SENTINEL) + code.rstrip()
        self.stream.write(wrapped.encode("utf-8") + b"\n")
        data = self.read_until(b">>> ", timeout=timeout)
        result = data[:-4]
        marker = SENTINEL.encode()
        idx = result.rfind(marker)
        if idx >= 0:
            result = result[idx + len(marker):]
        return result.strip()

    def exec_multiline(self, code, timeout=30):
        """Execute multi-line *code* by wrapping in ``exec()``."""
        escaped = (
            code.rstrip()
            .replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace("\n", "\\n")
        )
        return self.exec("exec('{}')".format(escaped))

    def eval(self, expression):
        raw = self.exec("print(repr({}))".format(expression))
        return ast.literal_eval(raw.decode("utf-8"))


# ── Process Backend ─────────────────────────────────────────────────

class ProcessBackend:
    """Spawn ``lvgl_micropy_unix`` via PTY and control through aioREPL."""

    def __init__(self, binary=None, heapsize="32M", cwd=None, boot_module="main"):
        self.binary = binary or _resolve_binary()
        self.heapsize = heapsize
        self.cwd = cwd or _resolve_cwd()
        self.boot_module = boot_module
        self.proc = None
        self.master_fd = None
        self.repl = None
        self._width = 320
        self._height = 240

    def start(self):
        master_fd, slave_fd = pty.openpty()
        self.proc = subprocess.Popen(
            [
                self.binary,
                "-X", "heapsize=" + self.heapsize,
                "-v", "-i", "-m", self.boot_module,
            ],
            stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
            close_fds=True, preexec_fn=os.setsid, cwd=self.cwd,
        )
        os.close(slave_fd)
        self.master_fd = master_fd
        self.repl = AIOREPLClient(_PTYStream(master_fd))
        self.repl.wait_for_boot()
        self._cache_display_resolution()
        return True

    def _cache_display_resolution(self):
        try:
            self._width = self.eval(
                "lv.screen_active().get_display().get_horizontal_resolution()"
            )
            self._height = self.eval(
                "lv.screen_active().get_display().get_vertical_resolution()"
            )
        except Exception:
            pass

    def stop(self):
        if self.proc:
            try:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                    self.proc.wait(timeout=2)
                except Exception:
                    pass
            self.proc = None
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
            self.master_fd = None

    def __del__(self):
        self.stop()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()

    # -- REPL ----------------------------------------------------------

    def exec(self, code):
        return self.repl.exec(code)

    def exec_multiline(self, code):
        return self.repl.exec_multiline(code)

    def eval(self, expr):
        return self.repl.eval(expr)

    # -- screen capture ------------------------------------------------

    def screenshot(self):
        tmp = "/tmp/_mpos_shot.raw"
        code = (
            "import lvgl as lv; "
            "w = lv.screen_active().get_display().get_horizontal_resolution(); "
            "h = lv.screen_active().get_display().get_vertical_resolution(); "
            "img = lv.image_dsc_t(); "
            "buf = bytearray(w * h * 3); "
            "lv.snapshot_take_to_buf(lv.screen_active(), lv.COLOR_FORMAT.RGB888, img, buf, len(buf)); "
            "f = open('{}', 'wb'); f.write(buf); f.close()"
        ).format(tmp)
        self.exec(code)
        try:
            raw = self._read_remote_file(tmp)
            return _build_bmp(self._width, self._height, raw)
        finally:
            try:
                self.exec("import os; os.remove('{}')".format(tmp))
            except Exception:
                pass

    def _read_remote_file(self, path):
        import base64
        chunk_size = 768
        size = self.eval(
            "__import__('os').stat('{}')[6]".format(path)
        )
        data = bytearray()
        self.exec("_rf = open('{}', 'rb')".format(path))
        try:
            while len(data) < size:
                out = self.exec(
                    "import ubinascii; "
                    "d = _rf.read({}); "
                    "print(ubinascii.b2a_base64(d).decode().strip())".format(
                        chunk_size
                    )
                )
                decoded = base64.b64decode(out.strip())
                if not decoded:
                    break
                data.extend(decoded)
        finally:
            self.exec("_rf.close()")
        return bytes(data)

    def write_remote_file(self, path, data):
        import base64
        chunk_size = 192
        b64 = base64.b64encode(data).decode("ascii")
        self.exec("_wf = open('{}', 'wb')".format(path))
        try:
            for i in range(0, len(b64), chunk_size):
                part = b64[i:i + chunk_size]
                self.exec(
                    "import ubinascii; _wf.write(ubinascii.a2b_base64('{}'))".format(
                        part
                    )
                )
        finally:
            self.exec("_wf.close()")

    # -- input ---------------------------------------------------------

    def press(self, x, y):
        self.exec(
            "from mpos.ui.testing import simulate_click, wait_for_render; "
            "simulate_click({}, {}); "
            "wait_for_render()".format(x, y)
        )

    def press_key(self, key):
        self.exec(
            "from mpos.ui.testing import click_button, wait_for_render; "
            "click_button('{}'); "
            "wait_for_render()".format(key)
        )

    # -- screen introspection -------------------------------------------

    def get_visible_text(self):
        raw = self.exec_multiline("""
from mpos.ui.testing import get_screen_text_content
import lvgl as lv
t = get_screen_text_content(lv.screen_active())
for s in t:
    print(repr(s))
""")
        result = []
        for line in raw.decode("utf-8").split("\n"):
            line = line.rstrip("\r")
            if line:
                try:
                    result.append(ast.literal_eval(line))
                except (SyntaxError, ValueError):
                    result.append(line)
        return result

    def find_text(self, text):
        return text in self.get_visible_text()

    @property
    def display_size(self):
        return self._width, self._height


# ── Serial Backend ─────────────────────────────────────────────────

try:
    import serial as _serial
except ImportError:
    _serial = None


class SerialBackend:
    """Connect to a physical MicroPythonOS device over serial/UART."""

    def __init__(self, port="/dev/ttyACM0", baudrate=115200, reset=True):
        if _serial is None:
            raise ImportError("pyserial is required for SerialBackend: pip install pyserial")
        self.port = port
        self.baudrate = baudrate
        self.reset = reset
        self.ser = None
        self.repl = None
        self._width = 320
        self._height = 240

    def start(self):
        self.ser = _serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            timeout=0.05,
            write_timeout=1,
        )
        if self.reset:
            self.ser.dtr = False
            self.ser.rts = False
            time.sleep(0.1)
            self.ser.dtr = True
            self.ser.rts = True
            time.sleep(0.1)
            self.ser.dtr = False
            self.ser.rts = False
            time.sleep(1.5)
        self.repl = AIOREPLClient(_SerialStream(self.ser))
        self.repl.wait_for_boot(timeout=15)
        self._cache_display_resolution()
        return True

    def _cache_display_resolution(self):
        try:
            self._width = self.eval(
                "lv.screen_active().get_display().get_horizontal_resolution()"
            )
            self._height = self.eval(
                "lv.screen_active().get_display().get_vertical_resolution()"
            )
        except Exception:
            pass

    def stop(self):
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None
            self.repl = None

    def __del__(self):
        self.stop()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()

    def exec(self, code):
        return self.repl.exec(code)

    def exec_multiline(self, code):
        return self.repl.exec_multiline(code)

    def eval(self, expr):
        return self.repl.eval(expr)

    def screenshot(self):
        tmp = "/tmp/_mpos_shot.raw"
        code = (
            "import lvgl as lv; "
            "w = lv.screen_active().get_display().get_horizontal_resolution(); "
            "h = lv.screen_active().get_display().get_vertical_resolution(); "
            "img = lv.image_dsc_t(); "
            "buf = bytearray(w * h * 3); "
            "lv.snapshot_take_to_buf(lv.screen_active(), lv.COLOR_FORMAT.RGB888, img, buf, len(buf)); "
            "f = open('{}', 'wb'); f.write(buf); f.close()"
        ).format(tmp)
        self.exec(code)
        try:
            raw = self._read_remote_file(tmp)
            return _build_bmp(self._width, self._height, raw)
        finally:
            try:
                self.exec("import os; os.remove('{}')".format(tmp))
            except Exception:
                pass

    def _read_remote_file(self, path):
        import base64
        chunk_size = 768
        size = self.eval(
            "__import__('os').stat('{}')[6]".format(path)
        )
        data = bytearray()
        self.exec("_rf = open('{}', 'rb')".format(path))
        try:
            while len(data) < size:
                out = self.exec(
                    "import ubinascii; "
                    "d = _rf.read({}); "
                    "print(ubinascii.b2a_base64(d).decode().strip())".format(
                        chunk_size
                    )
                )
                decoded = base64.b64decode(out.strip())
                if not decoded:
                    break
                data.extend(decoded)
        finally:
            self.exec("_rf.close()")
        return bytes(data)

    def write_remote_file(self, path, data):
        import base64
        chunk_size = 192
        b64 = base64.b64encode(data).decode("ascii")
        self.exec("_wf = open('{}', 'wb')".format(path))
        try:
            for i in range(0, len(b64), chunk_size):
                part = b64[i:i + chunk_size]
                self.exec(
                    "import ubinascii; _wf.write(ubinascii.a2b_base64('{}'))".format(
                        part
                    )
                )
        finally:
            self.exec("_wf.close()")

    def press(self, x, y):
        self.exec(
            "from mpos.ui.testing import simulate_click, wait_for_render; "
            "simulate_click({}, {}); "
            "wait_for_render()".format(x, y)
        )

    def press_key(self, key):
        self.exec(
            "from mpos.ui.testing import click_button, wait_for_render; "
            "click_button('{}'); "
            "wait_for_render()".format(key)
        )

    def get_visible_text(self):
        raw = self.exec_multiline("""
from mpos.ui.testing import get_screen_text_content
import lvgl as lv
t = get_screen_text_content(lv.screen_active())
for s in t:
    print(repr(s))
""")
        result = []
        for line in raw.decode("utf-8").split("\n"):
            line = line.rstrip("\r")
            if line:
                try:
                    result.append(ast.literal_eval(line))
                except (SyntaxError, ValueError):
                    result.append(line)
        return result

    def find_text(self, text):
        return text in self.get_visible_text()

    @property
    def display_size(self):
        return self._width, self._height


# ── MPOSController ──────────────────────────────────────────────────

class MPOSController:
    """Unified controller for MicroPythonOS."""

    _BACKENDS = {"process": ProcessBackend, "serial": SerialBackend}

    def __init__(self, backend="process", **kwargs):
        cls = self._BACKENDS.get(backend)
        if cls is None:
            raise ValueError("Unknown backend {!r}".format(backend))
        self._backend = cls(**kwargs)

    def start(self):
        return self._backend.start()

    def stop(self):
        self._backend.stop()

    def exec(self, code):
        return self._backend.exec(code)

    def exec_multiline(self, code):
        return self._backend.exec_multiline(code)

    def eval(self, expr):
        return self._backend.eval(expr)

    def screenshot(self):
        return self._backend.screenshot()

    def press(self, x, y):
        self._backend.press(x, y)

    def press_key(self, key):
        self._backend.press_key(key)

    def read_file(self, path):
        return self._backend._read_remote_file(path)

    def write_file(self, path, data):
        self._backend.write_remote_file(path, data)

    def get_visible_text(self):
        return self._backend.get_visible_text()

    def find_text(self, text):
        return self._backend.find_text(text)

    @property
    def display_size(self):
        return self._backend.display_size

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()


# ── CLI ──────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="MicroPythonOS Controller")
    parser.add_argument(
        "action", nargs="?", default="exec",
        help="Action: exec, eval, screenshot (default: exec)",
    )
    parser.add_argument("args", nargs="*", help="Arguments")
    parser.add_argument("--binary", help="Path to lvgl_micropy_unix binary")
    parser.add_argument("--heapsize", default="32M")
    args = parser.parse_args()
    ctrl = MPOSController(binary=args.binary, heapsize=args.heapsize)

    if args.action == "exec":
        code = " ".join(args.args) if args.args else "print('ready')"
        with ctrl:
            out = ctrl.exec(code)
            sys.stdout.buffer.write(out)
            sys.stdout.buffer.write(b"\n")
    elif args.action == "eval":
        expr = " ".join(args.args) if args.args else "None"
        with ctrl:
            val = ctrl.eval(expr)
            print(val)
    elif args.action == "screenshot":
        path = args.args[0] if args.args else "screenshot.bmp"
        with ctrl:
            bmp = ctrl.screenshot()
            with open(path, "wb") as f:
                f.write(bmp)
            print("Wrote", path, "({} bytes)".format(len(bmp)))
    else:
        parser.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
