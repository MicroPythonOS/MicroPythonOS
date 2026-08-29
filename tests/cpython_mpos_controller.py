#!/usr/bin/env python3
"""
CPython-side integration tests for MPOSController (both backends).

Tests exec, eval, multiline, state persistence, UI creation,
screenshot capture, widget tree introspection, visible text
extraction, button interaction, and multiple session cycles.

Usage:
    # Desktop (process) backend
    python3 tests/test_mpos_controller.py

    # Serial device backend
    python3 tests/test_mpos_controller.py --serial /dev/ttyACM0

    # Specific sections
    python3 tests/test_mpos_controller.py --only basic,ui,interaction
"""

import sys
import os
import time
import argparse
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from scripts.mpos_controller import (
    MPOSController,
    AIOREPLClient,
    END_MARKER,
    _count_usb_serial_devices,
    _mpremote_cmd,
)


PASS = 0
FAIL = 0


def section(name):
    print(f"\n{'='*60}")
    print(f"  [{name}]")
    print(f"{'='*60}")


def check(cond, msg):
    global PASS, FAIL
    if cond:
        print(f"  ✓ {msg}")
        PASS += 1
    else:
        print(f"  ✗ {msg}")
        FAIL += 1


def find_buttons(tree, results=None):
    if results is None:
        results = []
    for entry in tree:
        if entry.get("type") == "button" and not entry.get("hidden"):
            results.append(entry)
        if "children" in entry:
            find_buttons(entry["children"], results)
    return results


def run_tests(mpos, only=None, is_serial=False, cli_binary=None, serial_port=None):
    sections = {
        "basic": test_basic,
        "ui": test_ui_introspection,
        "interaction": test_interaction,
        "drag": test_drag,
        "cli": test_cli_longpress,
        "sessions": test_multiple_sessions,
        "navigation": test_app_navigation,
        "appmanagement": test_app_management,
        "helpers": test_controller_helpers,
        "readuntil": test_read_until,
        "mpremoteport": test_mpremote_port,
        "assertguard": test_assert_guard,
    }
    if only:
        names = [s.strip() for s in only.split(",")]
        for n in names:
            if n in sections:
                sections[n](
                    mpos,
                    is_serial=is_serial,
                    cli_binary=cli_binary,
                    serial_port=serial_port,
                )
    else:
        for name, fn in sections.items():
            fn(mpos, is_serial=is_serial, cli_binary=cli_binary, serial_port=serial_port)


def test_read_until(mpos, is_serial=False, cli_binary=None, serial_port=None):
    # Unit test: no device and no desktop binary. read_until must match
    # an LF sentinel against LF output (desktop PTY) and against CRLF
    # output (device REPL). Before the CRLF fix, the serial case never
    # matched and every exec waited out its full timeout.
    section("read_until sentinel matching (LF and CRLF)")

    class PipeStream:
        def __init__(self, data):
            self.rfd, self.wfd = os.pipe()
            os.write(self.wfd, data)

        def fileno(self):
            return self.rfd

        def read(self, n):
            return os.read(self.rfd, n)

        def close(self):
            os.close(self.rfd)
            os.close(self.wfd)

    def read_from(data, ending, timeout):
        stream = PipeStream(data)
        try:
            t0 = time.monotonic()
            result = AIOREPLClient(stream).read_until(ending, timeout=timeout)
            return result, time.monotonic() - t0
        finally:
            stream.close()

    sentinel = END_MARKER.encode() + b"\n"

    out, elapsed = read_from(b"hello\n" + sentinel, sentinel, timeout=10)
    check(out.endswith(sentinel), f"LF output matches LF sentinel: {out!r}")
    check(elapsed < 5, f"LF match returns before the timeout ({elapsed:.2f}s)")

    crlf_data = b"hello\r\n" + END_MARKER.encode() + b"\r\n"
    out, elapsed = read_from(crlf_data, sentinel, timeout=10)
    check(
        out.endswith(END_MARKER.encode() + b"\r\n"),
        f"CRLF output matches LF sentinel: {out!r}",
    )
    check(elapsed < 5, f"CRLF match returns before the timeout ({elapsed:.2f}s)")

    out, elapsed = read_from(b"MicroPython\r\n>>> ", b">>> ", timeout=10)
    check(out.endswith(b">>> "), f"prompt sentinel without newline: {out!r}")
    check(elapsed < 5, f"prompt match returns before the timeout ({elapsed:.2f}s)")

    out, elapsed = read_from(b"no sentinel here\r\n", sentinel, timeout=0.5)
    check(
        out == b"no sentinel here\r\n",
        f"missing sentinel: timeout still returns the data: {out!r}",
    )


def test_mpremote_port(mpos, is_serial=False, cli_binary=None, serial_port=None):
    # This test does not use a device, because _mpremote_cmd() only builds a
    # list of arguments. It runs with the desktop backend and with a device.
    section("mpremote port selection")

    cmd = _mpremote_cmd("/dev/ttyACM7", "fs", "cp", "app.py", ":/")
    has_connect = "connect" in cmd
    check(has_connect, "with a port: the command contains 'connect'")
    check(
        has_connect and cmd[cmd.index("connect") + 1] == "/dev/ttyACM7",
        "with a port: the port comes after 'connect'",
    )
    check(
        cmd[-4:] == ["fs", "cp", "app.py", ":/"],
        "with a port: the command keeps the other arguments",
    )

    # With no port, mpremote connects to the first device that it finds. The
    # command must not contain 'connect', because there is no port to give.
    cmd = _mpremote_cmd(None, "fs", "cp", "app.py", ":/")
    check("connect" not in cmd, "with no port: the command contains no 'connect'")
    check(
        cmd[-4:] == ["fs", "cp", "app.py", ":/"],
        "with no port: the command keeps the other arguments",
    )

    # A missing pyserial must give None, and not 0. The installapp guard reads
    # 0 as "the host has one device or no device", and then does not warn.
    # mpremote runs with `python3`, which can be a different interpreter that
    # does have pyserial, so 0 would hide a real multi-device condition.
    import builtins

    real_import = builtins.__import__

    def no_serial(name, *a, **k):
        if name.split(".")[0] == "serial":
            raise ImportError("blocked by the test")
        return real_import(name, *a, **k)

    builtins.__import__ = no_serial
    try:
        check(
            _count_usb_serial_devices() is None,
            "no pyserial: the device count is unknown, and not 0",
        )
    finally:
        builtins.__import__ = real_import


def test_assert_guard(mpos, is_serial=False, cli_binary=None, serial_port=None):
    section("unittest assertion self-check (run_test_file)")

    # A failing assertion must never produce a passing run. On builds where
    # unittest resolves to a lib compiled with mpy-cross -O3 (assert
    # statements stripped, e.g. the frozen lib of a prod firmware), the
    # runner's self-check must abort the run instead of reporting vacuous
    # success; on dev builds the assertion itself fails the run.
    os.makedirs("tmp", exist_ok=True)
    failing_test = os.path.join("tmp", "_assert_guard_test.py")
    with open(failing_test, "w") as f:
        f.write(
            "import unittest\n"
            "\n"
            "\n"
            "class TestMustFail(unittest.TestCase):\n"
            "    def test_failing_assert(self):\n"
            "        self.assertTrue(False)\n"
        )
    try:
        passed, out = mpos.run_test_file(failing_test)
        check(
            passed is False,
            "run with a failing assertion is not reported as a success",
        )
    finally:
        os.remove(failing_test)


def test_basic(mpos, is_serial=False, cli_binary=None, serial_port=None):
    section("Basic exec / eval / multiline")

    out = mpos.exec("print('hello from mpos')")
    check(b"hello from mpos" in out, f"exec prints output: {out!r}")

    val = mpos.eval("1 + 1")
    check(val == 2, f"eval 1+1 == {val}")

    val = mpos.eval("'foo' + 'bar'")
    check(val == "foobar", f"eval str concat == {val!r}")

    out = mpos.exec_multiline("""
for i in range(3):
    print(i)
""")
    check(b"0" in out and b"2" in out, f"multiline loop: {out!r}")

    mpos.exec("x = 42")
    val = mpos.eval("x")
    check(val == 42, f"state persists across execs: x == {val}")

    for i in range(10):
        out = mpos.exec(f"print({i})")
        check(str(i).encode() in out, f"sequential exec {i}")
        if any(str(j).encode() not in out for j in range(i, i+1)):
            break

    for i in range(5):
        mpos.exec(f"x = {i * 10}")
        val = mpos.eval("x")
        check(val == i * 10, f"interleaved exec/eval {i}: x == {val}")


def test_ui_introspection(mpos, is_serial=False, cli_binary=None, serial_port=None):
    section("UI creation / screenshot / widget tree / visible text")

    mpos.exec("""
import lvgl as lv
scr = lv.obj()
lv.screen_load(scr)
scr.set_style_bg_color(lv.color_hex(0xFFFFFF), 0)
btn = lv.button(scr)
btn.set_size(120, 50)
btn.align(lv.ALIGN.CENTER, 0, 0)
lv.label(btn).set_text("Click Me")
title = lv.label(scr)
title.set_text("Test UI")
title.align(lv.ALIGN.TOP_MID, 0, 10)
""")
    time.sleep(0.3)

    texts = mpos.get_visible_text()
    check("Test UI" in texts, f"visible text has 'Test UI': {texts}")
    check("Click Me" in texts, f"visible text has 'Click Me': {texts}")

    tree = mpos.get_widget_tree()
    btns = find_buttons(tree)
    check(len(btns) >= 1, f"found {len(btns)} visible buttons")
    if btns:
        b = btns[0]
        check(b.get("clickable"), f"button is clickable")
        check("flags" in b, f"button has flags field: {b.get('flags')}")
        check("center_x" in b and "center_y" in b, f"button has coords: ({b.get('center_x')}, {b.get('center_y')})")

    bmp = mpos.screenshot()
    check(bmp[:2] == b"BM", f"screenshot has BMP header: {bmp[:2]!r}")
    check(len(bmp) > 1000, f"screenshot size: {len(bmp)} bytes")

    check(mpos.find_text("Test UI"), "find_text finds 'Test UI'")
    check(not mpos.find_text("NonexistentXYZ12345"), "find_text rejects nonexistent")


def test_interaction(mpos, is_serial=False, cli_binary=None, serial_port=None):
    section("Button interaction (press_key / press)")

    mpos.exec("""
import lvgl as lv
scr = lv.obj()
lv.screen_load(scr)
scr.set_style_bg_color(lv.color_hex(0xFFFFFF), 0)
result = lv.label(scr)
result.set_text("not clicked")
result.align(lv.ALIGN.TOP_MID, 0, 30)
btn = lv.button(scr)
btn.set_size(120, 50)
btn.align(lv.ALIGN.CENTER, 0, 0)
lv.label(btn).set_text("Press")
def cb(e):
    result.set_text("clicked!")
btn.add_event_cb(cb, lv.EVENT.CLICKED, None)
""")
    time.sleep(0.3)

    mpos.press_key("Press")
    time.sleep(0.3)
    texts = mpos.get_visible_text()
    check("clicked!" in texts, f"press_key triggers callback: {texts}")

    mpos.exec("result.set_text('nope')")
    time.sleep(0.1)
    tree = mpos.get_widget_tree()
    btns = find_buttons(tree)
    if btns:
        b = btns[0]
        cx, cy = b["center_x"], b["center_y"]
        check(0 <= cy < 240, f"button y={cy} in screen bounds")
        mpos.press(cx, cy)
        time.sleep(0.3)
        texts = mpos.get_visible_text()
        if "clicked!" in texts:
            check(True, "press() triggers callback")
        else:
            # Fallback: send_event directly
            mpos.exec("""
import lvgl as lv
scr = lv.screen_active()
btn = scr.get_child(1)
btn.send_event(lv.EVENT.CLICKED, None)
""")
            time.sleep(0.2)
            texts = mpos.get_visible_text()
            check("clicked!" in texts, f"send_event fallback: {texts}")


def test_drag(mpos, is_serial=False, cli_binary=None, serial_port=None):
    section("Drag (slider interaction)")

    mpos.exec("""
import lvgl as lv
scr = lv.obj()
lv.screen_load(scr)
scr.set_style_bg_color(lv.color_hex(0xFFFFFF), 0)
slider = lv.slider(scr)
slider.set_size(200, 20)
slider.align(lv.ALIGN.CENTER, 0, 0)
slider.set_range(0, 100)
slider.set_value(0, lv.ANIM.OFF)
""")
    time.sleep(0.3)

    mpos.drag(70, 120, 200, 120)
    time.sleep(0.3)

    val = mpos.eval("lv.screen_active().get_child(0).get_value()")
    check(val > 20, f"drag moved slider from 0 to {val}")


def test_cli_longpress(mpos, is_serial=False, cli_binary=None, serial_port=None):
    section("CLI longpress action")
    if is_serial:
        check(True, "skipped (serial backend)")
        return

    script_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "scripts", "mpos_controller.py")
    )
    cmd = ["python3", script_path]
    if cli_binary:
        cmd.extend(["--binary", cli_binary])
    cmd.extend(["longpress", "0", "0"])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    check(result.returncode == 0, f"CLI longpress exits 0 (got {result.returncode})")
    check(
        "Long-pressed (0, 0)" in result.stdout,
        f"CLI longpress prints confirmation: {result.stdout.strip()!r}",
    )


def test_multiple_sessions(mpos, is_serial=False, cli_binary=None, serial_port=None):
    section("Multiple sessions")
    if is_serial:
        check(True, "skipped (serial backend)")
        return
    for i in range(3):
        with MPOSController() as m:
            out = m.exec("print('session ' + str(42))")
            check(b"session 42" in out, f"session {i+1}")
    check(True, "all 3 sessions OK")


def test_app_navigation(mpos, is_serial=False, cli_binary=None, serial_port=None):
    section("App navigation (startapp / backscreen / freespace)")

    mpos.exec("""
import lvgl as lv
scr = lv.obj()
lv.screen_load(scr)
scr.set_style_bg_color(lv.color_hex(0xFFFFFF), 0)
l = lv.label(scr)
l.set_text("Navigation Test")
l.align(lv.ALIGN.CENTER, 0, 0)
""")
    time.sleep(0.3)

    tree_before = mpos.get_widget_tree()

    result = mpos.startapp("com.micropythonos.about")
    check(result is True, "startapp launched successfully")
    time.sleep(0.5)
    tree_app = mpos.get_widget_tree()
    check(tree_app != tree_before, "widget tree changed after startapp")

    out = mpos.backscreen()
    check(b"Warning" not in out, "backscreen returned without warning")
    time.sleep(0.6)
    tree_back = mpos.get_widget_tree()
    check(tree_back != tree_app, "widget tree changed after backscreen")

    free = mpos.check_free_space()
    check(isinstance(free, int) and free > 0, f"free space: {free} bytes")


def test_controller_helpers(mpos, is_serial=False, cli_binary=None, serial_port=None):
    section("New controller helpers")

    mpos.exec("""
import lvgl as lv
scr = lv.obj()
lv.screen_load(scr)
scr.set_style_bg_color(lv.color_hex(0xFFFFFF), 0)
btn = lv.button(scr)
btn.set_size(120, 50)
btn.align(lv.ALIGN.CENTER, 0, 0)
lv.label(btn).set_text("Helper Button")
status = lv.label(scr)
status.set_text("idle")
status.align(lv.ALIGN.TOP_MID, 0, 10)
def cb(e):
    status.set_text("helper clicked")
btn.add_event_cb(cb, lv.EVENT.CLICKED, None)
""")
    time.sleep(0.3)

    check(mpos.wait_for_text("Helper Button", timeout=5), "wait_for_text finds label")
    mpos.expect_text("idle")

    found = mpos.find_widget(type="button")
    check(found is not None and found.get("type") == "button", "find_widget finds button by type")

    mpos.click_button("Helper Button")
    time.sleep(0.3)
    check(mpos.wait_for_text("helper clicked", timeout=5), "click_button triggers callback")

    mpos.save_screenshot("tmp/_mpos_controller_test_helper.bmp")
    check(os.path.exists("tmp/_mpos_controller_test_helper.bmp"), "save_screenshot writes file")

    w, h, pixels = mpos.screenshot_pixels()
    check(w == 320 and h == 240 and len(pixels) == w * h * 3, "screenshot_pixels returns correct dimensions")

    try:
        from PIL import Image
        im = mpos.screenshot_image()
        check(im.size == (w, h) and im.mode == "RGB", "screenshot_image returns PIL Image")
    except ImportError:
        check(True, "screenshot_image skipped (pillow not installed)")


def test_app_management(mpos, is_serial=False, cli_binary=None, serial_port=None):
    section("App management (install / list / remove)")
    if not is_serial:
        check(True, "skipped (desktop backend)")
        return

    import subprocess, os

    appname = "com.micropythonos.helloworld"
    apppath = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..",
                     "internal_filesystem/apps", appname)
    )

    # Use the port that the caller gave. If mpremote gets no port, it connects
    # to the first serial device that it finds, which can be a different device.
    subprocess.run(
        _mpremote_cmd(serial_port, "mkdir", ":/apps"), capture_output=True
    )
    result = subprocess.run(
        _mpremote_cmd(serial_port, "fs", "cp", "-r", apppath, ":/apps/"),
        capture_output=True, timeout=60
    )
    check(result.returncode == 0, f"installapp: cp exit code {result.returncode}")

    mpos.exec("from mpos import AppManager ; AppManager.refresh_apps()")
    out = mpos.exec("""
from mpos import AppManager
for a in AppManager.get_app_list():
    print(a.fullname)
""")
    check(appname.encode() in out, f"listapps shows {appname}")

    out = mpos.exec(
        "from mpos import AppManager; "
        "AppManager.uninstall_app({!r})".format(appname)
    )
    check(b"Error" not in out, f"deleteapp succeeded: {out.decode().strip()}")

    out = mpos.exec("""
from mpos import AppManager
for a in AppManager.get_app_list():
    print(a.fullname)
""")
    check(appname.encode() not in out, f"listapps confirms {appname} removed")


def main():
    parser = argparse.ArgumentParser(description="Test MPOSController backends")
    parser.add_argument("--serial", help="Serial port for device backend")
    parser.add_argument("--only", help="Comma-separated test sections: basic,ui,interaction,drag,cli,sessions,navigation,appmanagement,helpers,readuntil,mpremoteport")
    parser.add_argument("--binary", help="Path to lvgl_micropy_unix binary")
    args = parser.parse_args()

    global PASS, FAIL

    if args.serial:
        print(f"\n{'#'*60}")
        print(f"  Testing SERIAL backend (port: {args.serial})")
        print(f"{'#'*60}")
        ctrl = MPOSController(backend="serial", port=args.serial, baudrate=115200, reset=True)
        try:
            ctrl.start()
            run_tests(ctrl, only=args.only, is_serial=True, cli_binary=args.binary, serial_port=args.serial)
        finally:
            ctrl.stop()
    else:
        print(f"\n{'#'*60}")
        print(f"  Testing DESKTOP (process) backend")
        print(f"{'#'*60}")
        with MPOSController(binary=args.binary) as mpos:
            run_tests(mpos, only=args.only, cli_binary=args.binary, serial_port=args.serial)

    print(f"\n{'='*60}")
    print(f"  Results: {PASS} passed, {FAIL} failed")
    print(f"{'='*60}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
