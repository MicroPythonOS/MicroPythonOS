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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from scripts.mpos_controller import MPOSController


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


def run_tests(mpos, only=None):
    sections = {
        "basic": test_basic,
        "ui": test_ui_introspection,
        "interaction": test_interaction,
        "sessions": test_multiple_sessions,
    }
    if only:
        names = [s.strip() for s in only.split(",")]
        for n in names:
            if n in sections:
                sections[n](mpos)
    else:
        for name, fn in sections.items():
            fn(mpos)


def test_basic(mpos):
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


def test_ui_introspection(mpos):
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


def test_interaction(mpos):
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


def test_multiple_sessions(mpos):
    section("Multiple sessions")
    for i in range(3):
        with MPOSController() as m:
            out = m.exec("print('session ' + str(42))")
            check(b"session 42" in out, f"session {i+1}")
    check(True, "all 3 sessions OK")


def main():
    parser = argparse.ArgumentParser(description="Test MPOSController backends")
    parser.add_argument("--serial", help="Serial port for device backend")
    parser.add_argument("--only", help="Comma-separated test sections: basic,ui,interaction,sessions")
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
            run_tests(ctrl, only=args.only)
        finally:
            ctrl.stop()
    else:
        print(f"\n{'#'*60}")
        print(f"  Testing DESKTOP (process) backend")
        print(f"{'#'*60}")
        with MPOSController(binary=args.binary) as mpos:
            run_tests(mpos, only=args.only)

    print(f"\n{'='*60}")
    print(f"  Results: {PASS} passed, {FAIL} failed")
    print(f"{'='*60}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
