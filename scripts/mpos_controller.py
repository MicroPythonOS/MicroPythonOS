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
import atexit
import os
import pty
import select
import signal
import struct
import subprocess
import sys
import termios
import time


# ── Widget tree introspection ──────────────────────────────────────
# Uses mpos.ui.testing.get_screen_widget_tree() which is always
# available on the device (imported by main.py at startup).


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


def _mpremote_cmd(port=None, *rest):
    """
    Build an mpremote command, with the port when the port is known.

    If the command has no `connect`, mpremote uses `connect auto`. That
    selects sorted(comports())[0], which is the first USB serial device by
    name. If the host has two devices, that device can be the incorrect one.
    Because of this, each caller that knows the port must give the port here.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mpremote = os.path.normpath(os.path.join(
        script_dir, "..",
        "lvgl_micropython/lib/micropython/tools/mpremote/mpremote.py"))
    cmd = ["python3", mpremote]
    if port:
        cmd += ["connect", port]
    return cmd + list(rest)


def _count_usb_serial_devices():
    """
    Count the attached USB serial devices, or give None if the count is unknown.

    The count is unknown when pyserial is missing from *this* interpreter.
    That does not mean the host has no devices: _mpremote_cmd() starts
    mpremote with `python3`, which can be a different interpreter that does
    have pyserial. A missing pyserial therefore gives None, and not 0, so
    that the caller does not read it as "the host has no devices".
    """
    try:
        import serial.tools.list_ports
    except ImportError:
        return None
    return sum(
        1 for p in serial.tools.list_ports.comports()
        if p.vid is not None and p.pid is not None
    )


# Self-check pasted into every test run right after `import unittest`.
# unittest's assert methods are plain `assert` statements, which
# mpy-cross -O3 strips. When unittest resolves to such a build (e.g. a
# frozen copy already imported at boot, before lib/ is prepended to
# sys.path), every assertion is a silent no-op and the whole suite
# reports vacuously green.
#
# When that happens, try to self-heal: import the filesystem
# lib/unittest (sys.path has lib/ first here) and graft its working
# assert methods onto the cached module's TestCase, so classes that
# already subclassed it (e.g. GraphicalTestCase) are repaired too.
# Only when no working unittest is available does the run abort loudly
# instead of "passing".
_ASSERT_SELF_CHECK_CODE = (
    "def _mpos_asserts_ok(_ut):\n"
    "    try:\n"
    "        _ut.TestCase().assertTrue(False)\n"
    "        return False\n"
    "    except AssertionError:\n"
    "        return True\n"
    "_mpos_asserts_work = _mpos_asserts_ok(unittest)\n"
    "if not _mpos_asserts_work:\n"
    "    _mpos_stripped_ut = sys.modules.pop('unittest', None)\n"
    "    try:\n"
    "        import unittest as _mpos_fresh_ut\n"
    "    except ImportError:\n"
    "        _mpos_fresh_ut = None\n"
    "    if _mpos_stripped_ut is not None:\n"
    "        sys.modules['unittest'] = _mpos_stripped_ut\n"
    "    if (_mpos_fresh_ut is not None\n"
    "            and _mpos_fresh_ut is not _mpos_stripped_ut\n"
    "            and _mpos_asserts_ok(_mpos_fresh_ut)):\n"
    "        for _mpos_name in dir(_mpos_fresh_ut.TestCase):\n"
    "            if _mpos_name.startswith('assert'):\n"
    "                setattr(_mpos_stripped_ut.TestCase, _mpos_name,\n"
    "                        getattr(_mpos_fresh_ut.TestCase, _mpos_name))\n"
    "        _mpos_asserts_work = _mpos_asserts_ok(unittest)\n"
    "        if _mpos_asserts_work:\n"
    "            print('MPOS_TEST_RUNNER: repaired stripped unittest assert "
    "methods using lib/unittest')\n"
    "if not _mpos_asserts_work:\n"
    "    print("
    "'MPOS_TEST_RUNNER FATAL: unittest assertions are no-ops: unittest "
    "was imported from a build with assert statements stripped "
    "(mpy-cross -O3, e.g. the frozen lib of a prod firmware), no working "
    "lib/unittest was available to repair it, and test results would be "
    "vacuously green. Use a dev build, or ensure a non-optimized "
    "lib/unittest is on sys.path.')\n"
)


def _indent(code, prefix):
    return "".join(prefix + line + "\n" for line in code.splitlines())


def _build_test_code(test_path, tests_dir=None):
    with open(test_path) as f:
        test_content = f.read()
    code = "import sys\n"
    code += "sys.path.insert(0, 'lib')\n"
    if tests_dir:
        code += "sys.path.append(%r)\n" % tests_dir
    code += "try:\n"
    code += "    import mpos; mpos.TaskManager.disable()\n"
    code += "    import asyncio as _tc_asyncio\n"
    code += "    def _tc_patched(cls, coroutine):\n"
    code += "        if cls.disabled:\n"
    code += "            return None\n"
    code += "        async def _tc_cleanup():\n"
    code += "            try:\n"
    code += "                return await coroutine\n"
    code += "            finally:\n"
    code += "                if task in cls.task_list:\n"
    code += "                    cls.task_list.remove(task)\n"
    code += "        task = _tc_asyncio.create_task(_tc_cleanup())\n"
    code += "        cls.task_list.append(task)\n"
    code += "        return task\n"
    code += "    mpos.TaskManager.create_task = classmethod(_tc_patched)\n"
    code += "except Exception:\n"
    code += "    pass\n"
    code += "import unittest\n"
    code += _ASSERT_SELF_CHECK_CODE
    code += """\
for _k in list(globals().keys()):
    _v = globals()[_k]
    if isinstance(_v, type):
        try:
            if issubclass(_v, unittest.TestCase) and _k != 'TestCase':
                del globals()[_k]
        except Exception:
            pass
"""
    # Strip the file's own main-guard: in paste mode __name__ == "__main__",
    # so unittest.main() would run the suite and then the runner below would
    # run it again on already-mutated UI state (crashes on device). The
    # import-based runner keeps __name__ != "__main__", which is why desktop
    # never saw this.
    test_content = test_content.replace(
        'if __name__ == "__main__":\n    unittest.main()\n', ""
    )
    code += test_content + "\n"
    code += """\
suite = unittest.TestSuite()
for _k in dir():
    _v = globals()[_k]
    if isinstance(_v, type):
        try:
            if issubclass(_v, unittest.TestCase):
                suite.addTest(_v)
        except Exception:
            pass
"""
    code += "if not _mpos_asserts_work:\n"
    code += "    print('TEST WAS A FAILURE')\n"
    code += "else:\n"
    code += "    result = unittest.TextTestRunner().run(suite)\n"
    code += ("    print('TEST WAS A SUCCESS' if result.wasSuccessful() "
             "else 'TEST WAS A FAILURE')\n")
    return code


def _build_import_runner_code(tests_dir=None, coverage=False, coverage_paths=None):
    code = "import sys\n"
    code += "sys.path.insert(0, 'lib')\n"
    if tests_dir:
        code += "sys.path.append(%r)\n" % tests_dir

    # Save outer asyncio event loop state before test code corrupts it.
    # MicroPython asyncio stores the entire event loop in module-level
    # globals (_task_queue, _io_queue, cur_task).  Tests that call
    # asyncio.run(), new_event_loop(), or Loop.run_until_complete() from
    # within the running TaskManager event loop (via the aiorepl paste
    # mode) corrupt them, causing SIGSEGV in task_queue_push.
    #
    # The inner run_until_complete sets cur_task = None on exit, which is
    # the primary corruption.  Sharing _task_queue and _io_queue is safe
    # — the outer loop is idle in wait_io_event() during the test.
    # For tests that call new_event_loop() in setUp, we restore all three
    # globals in the finally block after unittest.main().
    code += (
        "import asyncio as _mpos_a\n"
        "_mpos_saved_task_queue = _mpos_a.core._task_queue\n"
        "_mpos_saved_io_queue = _mpos_a.core._io_queue\n"
        "_mpos_saved_cur_task = _mpos_a.core.cur_task\n"
        "\n"
        "def _mpos_restore_asyncio():\n"
        "    _mpos_a.core._task_queue = _mpos_saved_task_queue\n"
        "    _mpos_a.core._io_queue = _mpos_saved_io_queue\n"
        "    _mpos_a.core.cur_task = _mpos_saved_cur_task\n"
        "\n"
        "_mpos_orig_run = _mpos_a.run\n"
        "def _mpos_safe_run(coro):\n"
        "    try:\n"
        "        return _mpos_orig_run(coro)\n"
        "    finally:\n"
        "        _mpos_a.core.cur_task = _mpos_saved_cur_task\n"
        "_mpos_a.run = _mpos_safe_run\n"
        "\n"
        "_mpos_orig_new_loop = _mpos_a.new_event_loop\n"
        "def _mpos_safe_new_loop():\n"
        "    return _mpos_orig_new_loop()\n"
        "_mpos_a.new_event_loop = _mpos_safe_new_loop\n"
        "\n"
        "_mpos_orig_loop_rtc = _mpos_a.Loop.run_until_complete\n"
        "def _mpos_safe_loop_rtc(aw):\n"
        "    try:\n"
        "        return _mpos_orig_loop_rtc(aw)\n"
        "    finally:\n"
        "        _mpos_a.core.cur_task = _mpos_saved_cur_task\n"
        "_mpos_a.Loop.run_until_complete = staticmethod(_mpos_safe_loop_rtc)\n"
    )

    code += "import mpos; mpos.TaskManager.disable()\n"
    if coverage:
        code += "import mpos.coverage\n"
        code += "mpos.coverage.start()\n"
        code += "_cov_stop = mpos.coverage.stop\n"
    code += "try:\n"
    code += "    import unittest\n"
    code += _indent(_ASSERT_SELF_CHECK_CODE, "    ")
    code += "    if not _mpos_asserts_work:\n"
    code += "        print('TEST WAS A FAILURE')\n"
    code += "    else:\n"
    code += "        sys.modules.pop('_runner_test', None)\n"
    code += "        import _runner_test as _test_mod\n"
    code += "        result = unittest.main(module=_test_mod)\n"
    code += ("        print('TEST WAS A SUCCESS' if result.wasSuccessful() "
             "else 'TEST WAS A FAILURE')\n")
    if coverage:
        code += ("    _cov_rpt = {}\n"
                 "    try:\n"
                 "        _cov_stop()\n"
                 "        _cov_rpt = mpos.coverage._tracker.report_json()\n"
                 "    except Exception:\n"
                 "        pass\n")
        code += "    print('=== COVERAGE_DATA ===')\n"
        code += "    print(_cov_rpt)\n"
        code += "    print('=== END_COVERAGE_DATA ===')\n"
    code += "finally:\n"
    code += "    _mpos_restore_asyncio()\n"
    return code


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


def _parse_bmp(bmp_bytes):
    """Parse a BMP produced by _build_bmp and return (width, height, rgb888_bytes)."""
    if len(bmp_bytes) < 54 or bmp_bytes[0:2] != b"BM":
        raise ValueError("Invalid BMP data")
    width = struct.unpack("<I", bmp_bytes[18:22])[0]
    height = struct.unpack("<i", bmp_bytes[22:26])[0]
    if height < 0:
        height = -height
        top_down = True
    else:
        top_down = False
    row_stride = (width * 3 + 3) // 4 * 4
    pixel_data = bmp_bytes[54:]
    if row_stride == width * 3 and top_down:
        return width, height, pixel_data
    rows = []
    for y in range(height):
        src_y = y if top_down else (height - 1 - y)
        offset = src_y * row_stride
        rows.append(pixel_data[offset:offset + width * 3])
    return width, height, b"".join(rows)


def _find_widgets(tree, predicate, parent=None):
    """Recursively yield (widget, parent) pairs matching predicate(widget)."""
    if not isinstance(tree, list):
        return
    for widget in tree:
        if predicate(widget):
            yield widget, parent
        children = widget.get("children")
        if children:
            yield from _find_widgets(children, predicate, parent=widget)


def _widget_matches(widget, type=None, text=None, clickable=None):
    """Check if a widget matches the given criteria."""
    if type is not None and widget.get("type") != type:
        return False
    if text is not None and widget.get("text") != text:
        return False
    if clickable is not None and widget.get("clickable") != clickable:
        return False
    return True


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
        for i in range(0, len(data), 256):
            self.ser.write(data[i:i + 256])
            time.sleep(0.1)

    def fileno(self):
        return self.ser.fileno()


# ── aioREPL Client ──────────────────────────────────────────────────

SENTINEL = "~~~MPOS~~~"
END_MARKER = "~~~MPOS_END~~~"


class AIOREPLClient:
    """Talk to MicroPythonOS through the aioREPL inside TaskManager."""

    def __init__(self, stream):
        self.stream = stream

    def _data_waiting(self, timeout=0):
        r, _, _ = select.select([self.stream], [], [], timeout)
        return bool(r)

    def _write_pasted(self, payload, chunk_size=256):
        """Write a paste-mode payload in chunks, draining the echo between
        chunks. aiorepl echoes every pasted byte back; writing a large
        payload in one call can deadlock once the payload plus its echo
        fill the PTY buffers, because nothing reads the echo until the
        write completes."""
        for i in range(0, len(payload), chunk_size):
            self.stream.write(payload[i:i + chunk_size])
            self._drain(0.02)

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
        # A device REPL emits CRLF line endings; the desktop PTY (OPOST
        # cleared) emits bare LF. Accept both, or an *ending* that expects
        # "\n" never matches over serial and every exec waits out its full
        # timeout — then still returns the right bytes, because the caller
        # recovers the sentinels with rfind. Correct output, 30s late, on
        # every call: that is what made serial sessions mysteriously slow.
        endings = (ending,)
        if ending.endswith(b"\n") and not ending.endswith(b"\r\n"):
            endings = (ending, ending[:-1] + b"\r\n")
        data = b""
        t0 = time.monotonic()
        while True:
            if data.endswith(endings):
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

    def _try_get_prompt(self, action, wait=0.5, drain_before=True):
        """Send *action* bytes, then wait briefly for ``>>> ``."""
        if drain_before:
            self._drain(0.3)
        self.stream.write(action)
        time.sleep(wait)
        data = self._drain(1.0)
        if b">>> " in data:
            return True
        return False

    def wait_for_boot(self, timeout=30):
        t0 = time.monotonic()
        data = b""
        # 1. Try ENTER first — device may already be at a prompt
        if self._try_get_prompt(b"\r\n", wait=0.5):
            return
        # 2. Try Ctrl-B to exit raw REPL
        if self._try_get_prompt(b"\x02", wait=0.5):
            self.stream.write(b"\r\n")
            time.sleep(0.2)
            self._drain(0.3)
            return
        # 3. Main loop: poll for data, send Ctrl-C after 2s of silence
        ctrl_c_sent = False
        while time.monotonic() - t0 < timeout:
            if self._data_waiting(0.1):
                chunk = self.stream.read(4096)
                if chunk:
                    data += chunk
                    if b">>> " in data:
                        self._drain(0.3)
                        return
            elif not ctrl_c_sent and time.monotonic() - t0 > 2:
                self.stream.write(b"\x03")
                time.sleep(0.3)
                ctrl_c_sent = True
        # 4. Fallback: drain, try Ctrl-B, then do one last read
        tail = self._drain(1.0)
        data += tail
        if self._try_get_prompt(b"\x02", wait=0.5, drain_before=False):
            return
        data += self.read_until(b">>> ", timeout=5)
        if b">>> " in data:
            self._drain(0.3)
            return
        leftover = self._drain(2.0)
        data += leftover
        raise TimeoutError(
            "aioREPL prompt not found.\n"
            + data.decode("utf-8", "replace")[-3000:]
        )

    def exec(self, code, timeout=30):
        """
        Execute *code* and return stdout output.

        Uses paste mode (Ctrl-E / Ctrl-D) so multi-line code
        works without escaping.  Sentinels bracket the output so
        ``>>>`` in user code cannot trigger premature truncation.
        """
        self._drain(0.1)

        self.stream.write(b"\x05")
        time.sleep(0.2)
        self._drain(0.5)

        payload = ("print('{}')\n".format(SENTINEL)
                   + code.rstrip()
                   + "\nprint('{}')".format(END_MARKER))
        self._write_pasted(payload.encode("utf-8"))
        self.stream.write(b"\x04")

        # aiorepl echoes all paste-mode input, so ``>>>`` in source
        # strings could fool read_until.  Use the printed END_MARKER
        # (which is followed by a newline) as the end sentinel — the
        # echoed code has ``')`` after it, so read_until skips that.
        data = self.read_until(END_MARKER.encode() + b"\n", timeout=timeout)
        self._drain(0.5)
        result = data
        start_marker = SENTINEL.encode()
        idx = result.rfind(start_marker)
        if idx >= 0:
            result = result[idx + len(start_marker):]
        end_marker = END_MARKER.encode()
        idx = result.rfind(end_marker)
        if idx >= 0:
            result = result[:idx]
        return result.strip()

    def exec_multiline(self, code, timeout=30):
        """Execute multi-line *code* (paste mode handles it natively)."""
        return self.exec(code, timeout=timeout)

    def exec_streaming(self, code, timeout=30, line_callback=None):
        """Execute *code*, calling *line_callback* for each line of actual output.

        Same paste-mode protocol as ``exec()``, but flushes filtered output
        line-by-line instead of returning it all at the end.  Returns the
        full filtered result (same as ``exec()``) so callers can still
        inspect for success markers.
        """
        self._drain(0.1)

        self.stream.write(b"\x05")
        time.sleep(0.2)
        self._drain(0.5)

        payload = ("print('{}')\n".format(SENTINEL)
                    + code.rstrip()
                    + "\nprint('{}')".format(END_MARKER))
        self._write_pasted(payload.encode("utf-8"))
        self.stream.write(b"\x04")

        endings = (END_MARKER.encode() + b"\n", END_MARKER.encode() + b"\r\n")
        start_marker = SENTINEL.encode()
        end_marker = END_MARKER.encode()
        start_line = start_marker + b"\n"

        data = b""
        output_started = False
        tail_idx = 0
        seen_end = False

        t0 = time.monotonic()
        while True:
            if data.endswith(endings):
                break
            if not self._data_waiting(0.01):
                if timeout is not None and time.monotonic() - t0 > timeout:
                    break
                continue
            chunk = self.stream.read(1)
            if not chunk:
                continue
            data += chunk

            if not output_started:
                idx = data.find(start_line)
                if idx >= 0:
                    output_started = True
                    tail_idx = idx + len(start_line)
            elif line_callback is not None:
                tail = data[tail_idx:]
                while b"\n" in tail:
                    nl = tail.index(b"\n")
                    line_bytes = tail[:nl].rstrip(b"\r")
                    tail_idx += nl + 1
                    if line_bytes == end_marker:
                        seen_end = True
                        break
                    line_callback(line_bytes + b"\n")
                    tail = data[tail_idx:]
                if seen_end:
                    break

        self._drain(0.5)
        result = data
        idx = result.rfind(start_marker)
        if idx >= 0:
            result = result[idx + len(start_marker):]
        idx = result.rfind(end_marker)
        if idx >= 0:
            result = result[:idx]
        return result.strip()

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
        self._watchdog = None
        self._width = 320
        self._height = 240

    @staticmethod
    def _is_alive(pid):
        try:
            os.kill(int(pid), 0)
            return True
        except (OSError, ProcessLookupError):
            return False

    @staticmethod
    def _kill_orphaned(name):
        """Kill processes called `name` whose parent no longer exists (Linux)."""
        if not os.path.isdir("/proc"):
            # Non-Linux fallback: kill by name
            try:
                subprocess.run(
                    ["killall", "-9", name],
                    capture_output=True, timeout=5,
                )
            except Exception:
                pass
            return
        own_pid = os.getpid()
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            pid = int(entry)
            if pid == own_pid:
                continue
            try:
                with open("/proc/{}/comm".format(pid), "r") as f:
                    comm = f.read().strip()
            except Exception:
                continue
            if comm != name:
                continue
            try:
                ppid = None
                with open("/proc/{}/status".format(pid), "r") as f:
                    for line in f:
                        if line.startswith("PPid:"):
                            ppid = int(line.split()[1])
                            break
            except Exception:
                continue
            if ppid == 1 or not ProcessBackend._is_alive(ppid):
                try:
                    os.kill(pid, signal.SIGKILL)
                except Exception:
                    pass

    @staticmethod
    def _kill_stale_processes(binary_path=None):
        """Kill orphaned MPOS desktop processes from previous runs."""
        names = ["lvgl_micropy_unix", "lvgl_micropy_macOS", "run_desktop.sh"]
        if binary_path:
            basename = os.path.basename(binary_path)
            if basename and basename not in names:
                names.insert(0, basename)
        for name in names:
            ProcessBackend._kill_orphaned(name)
        time.sleep(0.2)

    def _signal_handler(self, signum, frame):
        """Clean up the child process when the controller receives SIGINT/SIGTERM."""
        self.stop()
        sys.exit(128 + signum)

    @staticmethod
    def _start_watchdog(parent_pid, child_pid):
        """Spawn a tiny watcher that kills the child if the controller dies."""
        code = (
            "import os, signal, sys, time\n"
            "parent = int(sys.argv[1])\n"
            "child = int(sys.argv[2])\n"
            "while True:\n"
            "    try:\n"
            "        os.kill(parent, 0)\n"
            "    except OSError:\n"
            "        break\n"
            "    try:\n"
            "        os.kill(child, 0)\n"
            "    except OSError:\n"
            "        sys.exit(0)\n"
            "    time.sleep(0.2)\n"
            "try:\n"
            "    os.killpg(os.getpgid(child), signal.SIGKILL)\n"
            "except Exception:\n"
            "    pass\n"
            "try:\n"
            "    os.kill(child, signal.SIGKILL)\n"
            "except Exception:\n"
            "    pass\n"
        )
        return subprocess.Popen(
            [sys.executable, "-c", code, str(parent_pid), str(child_pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )

    def start(self):
        # On macOS CI runners, audio hardware is absent and playing
        # notification sounds through the buzzer can hang the process.
        # Write an empty notification_sound setting to the prefs config
        # BEFORE the binary boots, so NotificationManager reads it
        # during startup and never touches audio hardware.
        if sys.platform == "darwin":
            import json as _json
            _prefs_dir = os.path.join(self.cwd, "prefs",
                                      "com.micropythonos.settings")
            _config_path = os.path.join(_prefs_dir, "config.json")
            os.makedirs(_prefs_dir, exist_ok=True)
            _config = {}
            try:
                with open(_config_path) as _f:
                    _config = _json.load(_f)
            except (FileNotFoundError, ValueError):
                pass
            _config["notification_sound"] = ""
            with open(_config_path, "w") as _f:
                _json.dump(_config, _f)
            print("MPOS_TEST_RUNNER: disabled notification sounds for macOS CI (pre-boot)")

        # Kill any leftover lvgl_micropy_unix processes from previous runs
        self._kill_stale_processes(self.binary)
        time.sleep(0.3)
        master_fd, slave_fd = pty.openpty()
        # Set master side to raw mode so control chars (Ctrl-C, Ctrl-D, Ctrl-E)
        # pass through unmodified instead of being intercepted by the line
        # discipline (which would consume Ctrl-D as EOF, break paste mode, etc.)
        try:
            iflag, oflag, cflag, lflag, ispeed, ospeed, cc = termios.tcgetattr(master_fd)
            iflag &= ~(termios.BRKINT | termios.IGNBRK | termios.ICRNL | termios.INLCR | termios.IGNCR | termios.IXON | termios.IXOFF | termios.PARMRK | termios.INPCK | termios.ISTRIP)
            oflag &= ~(termios.OPOST)
            cflag &= ~(termios.PARENB | termios.CSIZE)
            cflag |= termios.CS8
            lflag &= ~(termios.ECHO | termios.ECHONL | termios.ICANON | termios.ISIG | termios.IEXTEN)
            cc[termios.VMIN] = 1
            cc[termios.VTIME] = 0
            termios.tcsetattr(master_fd, termios.TCSANOW, [iflag, oflag, cflag, lflag, ispeed, ospeed, cc])
        except Exception:
            pass
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
        self._watchdog = self._start_watchdog(os.getpid(), self.proc.pid)
        atexit.register(self.stop)
        try:
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)
        except Exception:
            pass
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
                self.proc.wait(timeout=3)
            except Exception:
                pass
            if self.proc and self.proc.poll() is None:
                self.proc.kill()
                try:
                    self.proc.wait(timeout=2)
                except Exception:
                    pass
            self.proc = None
        if self._watchdog:
            try:
                self._watchdog.kill()
                self._watchdog.wait(timeout=2)
            except Exception:
                pass
            self._watchdog = None
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
            self.master_fd = None

    def restart(self):
        """Stop and restart the backend."""
        self.stop()
        time.sleep(0.3)
        self.start()

    def __del__(self):
        self.stop()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()

    # -- REPL ----------------------------------------------------------

    def exec(self, code, timeout=30):
        return self.repl.exec(code, timeout=timeout)

    def exec_multiline(self, code, timeout=30):
        return self.repl.exec_multiline(code, timeout=timeout)

    def eval(self, expr):
        return self.repl.eval(expr)

    # -- disk space ----------------------------------------------------

    def check_free_space(self):
        raw = self.exec(
            "import os; fs=os.statvfs('/'); print(fs[0]*fs[3])"
        )
        return int(raw.strip().decode("utf-8"))

    # -- screen capture ------------------------------------------------

    def screenshot(self):
        free = self.check_free_space()
        needed = self._width * self._height * 3
        if free < needed:
            raise RuntimeError(
                "Insufficient free space for screenshot: "
                "{} bytes free, need at least {} bytes".format(free, needed)
            )
        tmp = "/tmp/_mpos_shot.raw"
        code = (
            "import lvgl as lv; "
            "from mpos.ui.testing import capture_screenshot; "
            "capture_screenshot('{}', color_format=lv.COLOR_FORMAT.RGB888)".format(tmp)
        )
        self.exec(code)
        try:
            raw = self._read_remote_file(tmp)
            return _build_bmp(self._width, self._height, raw)
        finally:
            try:
                self.exec("import os; os.remove('{}')".format(tmp))
            except Exception:
                pass

    def save_screenshot(self, path):
        """Capture a screenshot and write it to *path* (BMP format)."""
        bmp = self.screenshot()
        with open(path, "wb") as f:
            f.write(bmp)
        return path

    def screenshot_pixels(self):
        """Return (width, height, rgb888_bytes) for the current screen."""
        return _parse_bmp(self.screenshot())

    def screenshot_image(self):
        """Return the screenshot as a PIL Image (RGB)."""
        try:
            from PIL import Image
        except ImportError as e:
            raise ImportError("PIL is required for screenshot_image(); install pillow") from e
        width, height, pixels = self.screenshot_pixels()
        return Image.frombytes("RGB", (width, height), pixels)

    def _read_remote_file(self, path):
        with open(path, "rb") as f:
            return f.read()

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

    def long_press(self, x, y, duration_ms=1000):
        self.exec(
            "from mpos.ui.testing import simulate_click, wait_for_render; "
            "simulate_click({}, {}, press_duration_ms={}); "
            "wait_for_render()".format(x, y, duration_ms)
        )

    def drag(self, x1, y1, x2, y2):
        self.exec_multiline("""
from mpos.ui.testing import simulate_click, wait_for_render
steps = 5
for i in range(steps + 1):
    x = {} + ({} - {}) * i // steps
    y = {} + ({} - {}) * i // steps
    simulate_click(x, y)
    wait_for_render()
""".format(x1, x2, x1, y1, y2, y1))

    def press_key(self, key):
        self.exec(
            "from mpos.ui.testing import click_button, wait_for_render; "
            "click_button('{}'); "
            "wait_for_render()".format(key)
        )

    def click_button(self, text):
        """Click the center of a button (or other clickable widget) labelled *text*."""
        tree = self.get_widget_tree()
        button = self._find_button_by_text(tree, text)
        if button is None:
            raise RuntimeError("No clickable widget with text {!r} found".format(text))
        self.press(button["center_x"], button["center_y"])

    def find_widget(self, type=None, text=None, clickable=None):
        """Return the first widget matching the given criteria, or None."""
        for widget, _parent in _find_widgets(
            self.get_widget_tree(),
            lambda w: _widget_matches(w, type=type, text=text, clickable=clickable),
        ):
            return widget
        return None

    def press_widget(self, type=None, text=None):
        """Click the center of the first widget matching *type* and/or *text*."""
        widget = self.find_widget(type=type, text=text, clickable=True)
        if widget is None:
            widget = self.find_widget(type=type, text=text)
        if widget is None:
            raise RuntimeError(
                "No widget found with type={!r}, text={!r}".format(type, text)
            )
        self.press(widget["center_x"], widget["center_y"])

    def _find_button_by_text(self, tree, text):
        """Find a clickable widget whose own text or child label text matches."""
        for widget, _parent in _find_widgets(
            tree, lambda w: _widget_matches(w, clickable=True)
        ):
            if widget.get("text") == text:
                return widget
            for child, _p in _find_widgets(
                widget.get("children", []), lambda w: w.get("text") == text
            ):
                return widget
        return None

    def wait_for_text(self, text, timeout=10, disappear=False):
        """Wait until *text* appears (or disappears) on screen. Returns True on success."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            found = self.find_text(text)
            if disappear and not found:
                return True
            if not disappear and found:
                return True
            time.sleep(0.25)
        return False

    def expect_text(self, text, timeout=10):
        """Raise RuntimeError if *text* is not visible within *timeout* seconds."""
        if not self.wait_for_text(text, timeout=timeout):
            raise RuntimeError("Expected text {!r} not found on screen".format(text))

    # -- screen introspection -------------------------------------------

    def get_widget_tree(self):
        raw = self.exec_multiline("""
from mpos.ui.testing import get_screen_widget_tree
import json
print(json.dumps(get_screen_widget_tree()))
""")
        import json as _json
        return _json.loads(raw.strip().decode("utf-8"))

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

    def run_test_file(self, test_path, tests_dir=None, timeout=300, coverage=False, line_callback=None):
        if self.repl is None:
            self.start()
        dest_path = os.path.join(self.cwd, "_runner_test.py")
        with open(test_path) as f:
            content = f.read()
        with open(dest_path, "w") as f:
            f.write(content)
        try:
            code = _build_import_runner_code(tests_dir, coverage=coverage)
            if line_callback is not None:
                out = self.repl.exec_streaming(code, timeout=timeout, line_callback=line_callback)
            else:
                out = self.exec_multiline(code, timeout=timeout)
            out_str = out.decode("utf-8", errors="replace")
            passed = "TEST WAS A SUCCESS" in out_str
            return passed, out
        except OSError:
            msg = ("\nPROCESS CRASHED — MicroPython binary died (PTY closed). "
                   "Check for segfault (exit 139), "
                   "import error, or LVGL misuse (passing non-LVGL object "
                   "to widget constructor). "
                   "Run the binary directly to see the crash:\n"
                   "  lvgl_micropy_unix -X heapsize=32M -c '...'\n")
            return False, msg.encode()
        finally:
            try:
                os.remove(dest_path)
            except OSError:
                pass


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
            write_timeout=5,
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
        self.repl.wait_for_boot(timeout=20)
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
            self._rotation = self.eval(
                "lv.display_get_default().get_rotation()"
            )
        except Exception:
            self._rotation = 0

    def stop(self):
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None
            self.repl = None

    def hard_reset(self, timeout=60):
        """Hard-reset the device and wait for full boot (main.py completion).

        Flow:
        1. Connect via serial, reach REPL, send machine.reset()
        2. machine.reset() causes USB disconnect — close serial immediately
           (keeping the fd open over USB/IP passthrough corrupts it)
        3. Re-attach USB/IP if running in a KVM (no-op for direct USB)
        4. Poll for the serial port to reappear
        5. Reconnect and read serial output until "Starting asyncio REPL..."
           appears, confirming main.py ran to completion (BLE, LVGL,
           AudioManager singleton, etc. all initialized).
           Do NOT use wait_for_boot() here — it sends Ctrl-C after 2s of
           silence, which interrupts main.py mid-boot.
        6. The serial port can flap on USB/IP — retry up to 20 times.
        """
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None
            self.repl = None

        # 1. Reach REPL and send machine.reset() (same as mpremote reset command)
        ser = _serial.Serial(
            self.port, self.baudrate, timeout=0.5, write_timeout=2,
        )
        try:
            stream = _SerialStream(ser)
            repl = AIOREPLClient(stream)
            repl.wait_for_boot(timeout=20)
            ser.write(b"import machine; machine.reset()\r\n")
        finally:
            try:
                ser.close()
            except Exception:
                pass

        print("waiting 1 minute for device...")
        time.sleep(60)
        return True

        '''
        # 2. machine.reset() detaches USB from the bus entirely.
        # On USB/IP passthrough (KVM) we must re-attach after reset.
        # On direct USB this script doesn't exist — no-op.
        attach_script = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "..", "..", "kvm_usb", "vm", "esp32-usbip-attach.sh",
        )
        if os.path.exists(attach_script):
            subprocess.run(["bash", attach_script], capture_output=True, timeout=10)
            time.sleep(1)

        # 3. Wait for the serial port to reappear after USB re-enumeration
        deadline = time.monotonic() + timeout
        while not os.path.exists(self.port):
            if time.monotonic() > deadline:
                raise TimeoutError(
                    "Device at {} did not reappear after reset".format(self.port)
                )
            time.sleep(0.1)

        # 4. Reconnect and wait for main.py to finish booting.
        # USB/IP ports can flap — retry up to 20 times (3s apart = ~60s window).
        # ESP32 boot takes 2-40s depending on apps and BLE init.
        # Don't use wait_for_boot() here — it sends Ctrl-C after 2s which
        # interrupts main.py mid-boot. Instead, read serial output directly
        # until the "Starting asyncio REPL..." sentinel confirms full boot.
        last_err = None
        for _ in range(20):
            if not os.path.exists(self.port):
                time.sleep(3)
                continue
            try:
                ser = _serial.Serial(
                    self.port, self.baudrate, timeout=0.5, write_timeout=2,
                )
                try:
                    t0 = time.monotonic()
                    data = b""
                    while time.monotonic() - t0 < min(timeout, 60):
                        chunk = ser.read(4096)
                        if chunk:
                            data += chunk
                            if b"Starting asyncio REPL..." in data:
                                return True
                        time.sleep(0.1)
                    time.sleep(10) # seems needed to make tests/test_adc_recording.py work?
                    return True
                finally:
                    ser.close()
            except (OSError, _serial.SerialException) as e:
                last_err = e
                time.sleep(3)
        raise RuntimeError(
            "Device at {} not reachable after reset: {}".format(self.port, last_err)
        )
        '''

    def soft_reset(self):
        """Ctrl-D soft reset via existing serial connection, wait for REPL."""
        if not self.ser:
            raise RuntimeError("Not connected — call start() first")
        self.ser.write(b"\x04")
        time.sleep(0.5)
        self.repl.wait_for_boot(timeout=20)
        return True

    def __del__(self):
        self.stop()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()

    def exec(self, code, timeout=30):
        return self.repl.exec(code, timeout=timeout)

    def exec_multiline(self, code, timeout=30):
        return self.repl.exec_multiline(code, timeout=timeout)

    def eval(self, expr):
        return self.repl.eval(expr)

    def check_free_space(self):
        raw = self.exec(
            "import os; fs=os.statvfs('/'); print(fs[0]*fs[3])"
        )
        return int(raw.strip().decode("utf-8"))

    def screenshot(self):
        free = self.check_free_space()
        needed = self._width * self._height * 3
        if free < needed:
            raise RuntimeError(
                "Insufficient free space for screenshot on device: "
                "{} bytes free, need at least {} bytes".format(free, needed)
            )
        tmp = "/_mpos_shot.raw"
        code = (
            "import lvgl as lv; "
            "from mpos.ui.testing import capture_screenshot; "
            "capture_screenshot('{}', color_format=lv.COLOR_FORMAT.RGB888)".format(tmp)
        )
        self.exec(code)
        try:
            raw = self._read_remote_file(tmp)
            return _build_bmp(self._width, self._height, raw)
        finally:
            try:
                self.exec("import os; os.remove('{}')".format(tmp))
            except Exception:
                pass

    def save_screenshot(self, path):
        """Capture a screenshot and write it to *path* (BMP format)."""
        bmp = self.screenshot()
        with open(path, "wb") as f:
            f.write(bmp)
        return path

    def screenshot_pixels(self):
        """Return (width, height, rgb888_bytes) for the current screen."""
        return _parse_bmp(self.screenshot())

    def screenshot_image(self):
        """Return the screenshot as a PIL Image (RGB)."""
        try:
            from PIL import Image
        except ImportError as e:
            raise ImportError("PIL is required for screenshot_image(); install pillow") from e
        width, height, pixels = self.screenshot_pixels()
        return Image.frombytes("RGB", (width, height), pixels)

    def _read_remote_file(self, path):
        import subprocess, tempfile, os as _os
        with tempfile.NamedTemporaryFile(suffix=".raw", delete=False) as tmp:
            tmppath = tmp.name
        subprocess.run(
            _mpremote_cmd(self.port, "cp", ":{}".format(path), tmppath),
            capture_output=True, timeout=60
        )
        with open(tmppath, "rb") as f:
            data = f.read()
        _os.unlink(tmppath)
        return data

    def write_remote_file(self, path, data):
        import subprocess, tempfile, os as _os
        with tempfile.NamedTemporaryFile(suffix=".raw", delete=False) as tmp:
            tmppath = tmp.name
        with open(tmppath, "wb") as f:
            f.write(data)
        subprocess.run(
            _mpremote_cmd(self.port, "cp", tmppath, ":{}".format(path)),
            capture_output=True, timeout=60
        )
        _os.unlink(tmppath)

    def press(self, x, y):
        self.exec(
            "from mpos.ui.testing import simulate_click, wait_for_render; "
            "simulate_click({}, {}); "
            "wait_for_render()".format(x, y)
        )

    def long_press(self, x, y, duration_ms=1000):
        self.exec(
            "from mpos.ui.testing import simulate_click, wait_for_render; "
            "simulate_click({}, {}, press_duration_ms={}); "
            "wait_for_render()".format(x, y, duration_ms)
        )

    def drag(self, x1, y1, x2, y2):
        self.exec(
            "from mpos.ui.testing import simulate_drag, wait_for_render; "
            "simulate_drag({}, {}, {}, {}); "
            "wait_for_render()".format(x1, y1, x2, y2)
        )

    def press_key(self, key):
        self.exec(
            "from mpos.ui.testing import click_button, wait_for_render; "
            "click_button('{}'); "
            "wait_for_render()".format(key)
        )

    def click_button(self, text):
        """Click the center of a button (or other clickable widget) labelled *text*."""
        tree = self.get_widget_tree()
        button = self._find_button_by_text(tree, text)
        if button is None:
            raise RuntimeError("No clickable widget with text {!r} found".format(text))
        self.press(button["center_x"], button["center_y"])

    def find_widget(self, type=None, text=None, clickable=None):
        """Return the first widget matching the given criteria, or None."""
        for widget, _parent in _find_widgets(
            self.get_widget_tree(),
            lambda w: _widget_matches(w, type=type, text=text, clickable=clickable),
        ):
            return widget
        return None

    def press_widget(self, type=None, text=None):
        """Click the center of the first widget matching *type* and/or *text*."""
        widget = self.find_widget(type=type, text=text, clickable=True)
        if widget is None:
            widget = self.find_widget(type=type, text=text)
        if widget is None:
            raise RuntimeError(
                "No widget found with type={!r}, text={!r}".format(type, text)
            )
        self.press(widget["center_x"], widget["center_y"])

    def _find_button_by_text(self, tree, text):
        """Find a clickable widget whose own text or child label text matches."""
        for widget, _parent in _find_widgets(
            tree, lambda w: _widget_matches(w, clickable=True)
        ):
            if widget.get("text") == text:
                return widget
            for child, _p in _find_widgets(
                widget.get("children", []), lambda w: w.get("text") == text
            ):
                return widget
        return None

    def wait_for_text(self, text, timeout=10, disappear=False):
        """Wait until *text* appears (or disappears) on screen. Returns True on success."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            found = self.find_text(text)
            if disappear and not found:
                return True
            if not disappear and found:
                return True
            time.sleep(0.25)
        return False

    def expect_text(self, text, timeout=10):
        """Raise RuntimeError if *text* is not visible within *timeout* seconds."""
        if not self.wait_for_text(text, timeout=timeout):
            raise RuntimeError("Expected text {!r} not found on screen".format(text))

    def get_widget_tree(self):
        # Write JSON to device file (more reliable than printing large JSON over serial)
        self.exec_multiline("""
from mpos.ui.testing import get_screen_widget_tree
import json
with open("/_mpos_tree.json", "w") as f:
    json.dump(get_screen_widget_tree(), f)
print("OK")
""")
        try:
            import subprocess, json as _json, tempfile, os as _os
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
                tmppath = tmp.name
            subprocess.run(
                _mpremote_cmd(self.port, "cp", ":/_mpos_tree.json", tmppath),
                capture_output=True, timeout=20
            )
            with open(tmppath) as f:
                return _json.load(f)
        finally:
            try:
                _os.unlink(tmppath)
            except Exception:
                pass
            try:
                self.exec("import os; os.remove('/_mpos_tree.json')")
            except Exception:
                pass

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

    def run_test_file(self, test_path, tests_dir=None, timeout=300, coverage=False, line_callback=None):
        import subprocess, re
        import threading
        code = _build_test_code(test_path, tests_dir)
        host_test_dir = os.path.dirname(os.path.abspath(test_path))
        fixture_names = set(re.findall(r"\.\./tests/([^\"]+\.(?:mpk|ttf))", code))
        for helper in re.findall(r"^from (\w+) import", code, re.M):
            helper_path = os.path.join(host_test_dir, helper + ".py")
            if os.path.exists(helper_path):
                fixture_names.add(helper + ".py")
        if fixture_names:
            subprocess.run(
                _mpremote_cmd(
                    self.port, "exec",
                    "import os\ntry:\n os.mkdir('tests')\nexcept OSError:\n pass",
                ),
                capture_output=True, timeout=20,
            )
            for name in sorted(fixture_names):
                host_fixture = os.path.join(host_test_dir, name)
                if not os.path.exists(host_fixture):
                    continue
                subprocess.run(
                    _mpremote_cmd(self.port, "cp",
                                  host_fixture, ":tests/{}".format(name)),
                    capture_output=True, timeout=60,
                )
            code = code.replace("../tests/", "tests/")
        # Base64-encode the code so multibyte UTF-8 (e.g. emoji in string
        # literals) survives the trip through mpremote's byte-at-a-time
        # raw REPL transport. The device decodes back to exact bytes before
        # compiling, so non-ASCII source arrives intact.
        import base64
        b64 = base64.b64encode(code.encode("utf-8")).decode("ascii")
        code = ("import ubinascii\n"
                "exec(ubinascii.a2b_base64({!r}))".format(b64))
        cmd = _mpremote_cmd(self.port, "exec", code)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out_parts = []

        def _read_stream(stream, parts):
            for raw_line in iter(stream.readline, b""):
                parts.append(raw_line)
                if line_callback is not None:
                    line_callback(raw_line)

        t = threading.Thread(target=_read_stream, args=(proc.stdout, out_parts))
        t.daemon = True
        t.start()

        try:
            proc.wait(timeout=timeout + 60)
        except subprocess.TimeoutExpired:
            proc.kill()
            t.join(timeout=5)
            return False, "<test timed out after {}s>\n".format(timeout).encode()

        t.join(timeout=5)
        out = b"".join(out_parts)
        out_str = out.decode("utf-8", errors="replace")
        passed = "TEST WAS A SUCCESS" in out_str
        return passed, out


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

    def exec(self, code, timeout=30):
        return self._backend.exec(code, timeout=timeout)

    def exec_multiline(self, code, timeout=30):
        return self._backend.exec_multiline(code, timeout=timeout)

    def eval(self, expr):
        return self._backend.eval(expr)

    def screenshot(self):
        return self._backend.screenshot()

    def save_screenshot(self, path):
        return self._backend.save_screenshot(path)

    def screenshot_pixels(self):
        return self._backend.screenshot_pixels()

    def screenshot_image(self):
        return self._backend.screenshot_image()

    def check_free_space(self):
        return self._backend.check_free_space()

    def startapp(self, appname, intent=None, dismiss_onboarding=True, wait_render=True):
        """Launch an installed app by package name. Returns True on success.

        *intent* is an optional dict with keys ``action``, ``data``, and/or
        ``extras`` and is forwarded to ``mpos.Intent``.
        """
        if dismiss_onboarding:
            self.dismiss_onboarding()
        if intent is None:
            code = (
                "from mpos import AppManager; "
                "print(repr(AppManager.start_app({!r})))".format(appname)
            )
        else:
            lines = ["from mpos import AppManager, Intent", "intent = Intent()"]
            if intent.get("action") is not None:
                lines.append("intent.action = {!r}".format(intent["action"]))
            if intent.get("data") is not None:
                lines.append("intent.data = {!r}".format(intent["data"]))
            if intent.get("extras") is not None:
                lines.append("intent.extras = {!r}".format(intent["extras"]))
            lines.append(
                "print(repr(AppManager.start_app({!r}, intent)))".format(appname)
            )
            code = "\n".join(lines)
        out = self.exec(code)
        if wait_render:
            time.sleep(0.5)
        text = out.decode("utf-8", errors="replace").strip()
        for line in reversed(text.splitlines()):
            line = line.strip()
            if line in ("True", "False"):
                return line == "True"
        return False

    def run_app(self, appname, boot_wait=10, wait_render=2):
        """Start the controller, boot, dismiss onboarding, and launch an app."""
        self.start()
        time.sleep(boot_wait)
        self.dismiss_onboarding()
        return self.startapp(appname, dismiss_onboarding=False, wait_render=wait_render)

    def run_app_with_file(self, appname, filename, boot_wait=10, wait_render=2):
        """Boot, dismiss onboarding, and launch *appname* with a file intent."""
        self.start()
        time.sleep(boot_wait)
        self.dismiss_onboarding()
        return self.startapp(
            appname,
            intent={"data": filename},
            dismiss_onboarding=False,
            wait_render=wait_render,
        )

    def backscreen(self):
        return self.exec("import mpos.ui ; mpos.ui.back_screen()")

    def dismiss_onboarding(self, timeout=20):
        """Close the first-run 'How to Navigate' tutorial overlay if present."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                text = self.get_visible_text()
                if "How to Navigate" in text or "Close" in text:
                    self.exec("import mpos.ui.testing as t ; t.click_button('Close')")
                    time.sleep(0.5)
                    return True
            except Exception:
                pass
            time.sleep(0.25)
        return False

    def press(self, x, y):
        self._backend.press(x, y)

    def long_press(self, x, y, duration_ms=1000):
        self._backend.long_press(x, y, duration_ms)

    def drag(self, x1, y1, x2, y2):
        self._backend.drag(x1, y1, x2, y2)

    def press_key(self, key):
        self._backend.press_key(key)

    def click_button(self, text):
        self._backend.click_button(text)

    def find_widget(self, type=None, text=None, clickable=None):
        return self._backend.find_widget(type=type, text=text, clickable=clickable)

    def press_widget(self, type=None, text=None):
        self._backend.press_widget(type=type, text=text)

    def wait_for_text(self, text, timeout=10, disappear=False):
        return self._backend.wait_for_text(text, timeout=timeout, disappear=disappear)

    def expect_text(self, text, timeout=10):
        self._backend.expect_text(text, timeout=timeout)

    def read_file(self, path):
        return self._backend._read_remote_file(path)

    def write_file(self, path, data):
        self._backend.write_remote_file(path, data)

    def get_widget_tree(self):
        return self._backend.get_widget_tree()

    def get_visible_text(self):
        return self._backend.get_visible_text()

    def find_text(self, text):
        return self._backend.find_text(text)

    def run_test_file(self, test_path, tests_dir=None, timeout=300, coverage=False, line_callback=None):
        return self._backend.run_test_file(test_path, tests_dir=tests_dir, timeout=timeout, coverage=coverage, line_callback=line_callback)

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
        help="Action: exec, eval, screenshot, startapp, freespace, backscreen, installapp, listapps, deleteapp, click, longpress, drag (default: exec)",
    )
    parser.add_argument("args", nargs="*", help="Arguments")
    parser.add_argument("--binary", help="Path to lvgl_micropy_unix binary")
    parser.add_argument("--heapsize", default="32M")
    parser.add_argument(
        "--serial-port", help="Serial port for device (e.g. /dev/ttyACM0)"
    )
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument(
        "--no-reset", action="store_true",
        help="Skip DTR/RTS reset on serial connect (device already running)"
    )
    args = parser.parse_args()

    if args.serial_port:
        ctrl = MPOSController(
            backend="serial", port=args.serial_port,
            baudrate=args.baudrate, reset=not args.no_reset
        )
    else:
        ctrl = MPOSController(binary=args.binary, heapsize=args.heapsize)

    if args.action == "exec":
        if args.args:
            code = " ".join(args.args)
        elif not sys.stdin.isatty():
            code = sys.stdin.read()
        else:
            code = "print('ready')"
        with ctrl:
            out = ctrl.exec(code)
            sys.stdout.buffer.write(out)
            sys.stdout.buffer.write(b"\n")
    elif args.action == "eval":
        if args.args:
            expr = " ".join(args.args)
        elif not sys.stdin.isatty():
            expr = sys.stdin.read()
        else:
            expr = "None"
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
    elif args.action == "startapp":
        if not args.args:
            print("error: app name required", file=sys.stderr)
            return 1
        appname = args.args[0]
        with ctrl:
            out = ctrl.exec("from mpos import AppManager ; AppManager.start_app({!r})".format(appname))
            sys.stdout.buffer.write(out)
            sys.stdout.buffer.write(b"\n")
    elif args.action == "freespace":
        with ctrl:
            free = ctrl.check_free_space()
            needed = ctrl.display_size[0] * ctrl.display_size[1] * 3
            print("Free: {} bytes, need for screenshot: {} bytes".format(free, needed))
            if free < needed:
                print("WARNING: not enough space for a screenshot!")
            else:
                print("OK")
    elif args.action == "backscreen":
        with ctrl:
            out = ctrl.backscreen()
            sys.stdout.buffer.write(out)
            sys.stdout.buffer.write(b"\n")
    elif args.action == "installapp":
        if not args.args:
            print("error: app path required", file=sys.stderr)
            return 1
        apppath = args.args[0]
        import subprocess, os
        if not args.serial_port:
            device_count = _count_usb_serial_devices()
            if device_count is None:
                print(
                    "warning: pyserial is not available here, so the number of "
                    "USB serial devices is unknown.\n"
                    "         mpremote selects the first device. Give "
                    "--serial-port to select a device.",
                    file=sys.stderr,
                )
            elif device_count > 1:
                print(
                    "error: the host has more than one USB serial device and "
                    "you gave no --serial-port.\n"
                    "       mpremote would select the first device, which can "
                    "be the incorrect one.\n"
                    "       Run 'mpremote connect list' and give --serial-port.",
                    file=sys.stderr,
                )
                return 1
        print("Installing to {}".format(args.serial_port or "the first device"))
        subprocess.run(
            _mpremote_cmd(args.serial_port, "mkdir", ":/apps"), capture_output=True
        )
        result = subprocess.run(
            _mpremote_cmd(args.serial_port, "fs", "cp", "-r", apppath, ":/apps/"),
            capture_output=True, timeout=600
        )
        if result.returncode != 0:
            print("error:", result.stderr.decode().strip(), file=sys.stderr)
            return 1
        print(f"Installed {os.path.basename(apppath)}")
        with ctrl:
            ctrl.exec("from mpos import AppManager ; AppManager.refresh_apps()")
    elif args.action == "listapps":
        with ctrl:
            out = ctrl.exec("""
from mpos import AppManager
for a in AppManager.get_app_list():
    print(a.fullname)
""")
            sys.stdout.buffer.write(out)
    elif args.action == "deleteapp":
        if not args.args:
            print("error: app name required", file=sys.stderr)
            return 1
        appname = args.args[0]
        with ctrl:
            out = ctrl.exec(
                "from mpos import AppManager; "
                "AppManager.uninstall_app({!r})".format(appname)
            )
            sys.stdout.buffer.write(out)
            sys.stdout.buffer.write(b"\n")
    elif args.action == "click":
        if len(args.args) < 2:
            print("error: X Y required", file=sys.stderr)
            return 1
        x, y = int(args.args[0]), int(args.args[1])
        with ctrl:
            ctrl.press(x, y)
            print("Clicked ({}, {})".format(x, y))
    elif args.action == "longpress":
        if len(args.args) < 2:
            print("error: X Y required", file=sys.stderr)
            return 1
        x, y = int(args.args[0]), int(args.args[1])
        with ctrl:
            ctrl.long_press(x, y)
            print("Long-pressed ({}, {})".format(x, y))
    elif args.action == "drag":
        if len(args.args) < 4:
            print("error: X1 Y1 X2 Y2 required", file=sys.stderr)
            return 1
        x1, y1, x2, y2 = (int(args.args[i]) for i in range(4))
        with ctrl:
            ctrl.drag(x1, y1, x2, y2)
            print("Dragged ({},{}) -> ({},{})".format(x1, y1, x2, y2))
    else:
        parser.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
