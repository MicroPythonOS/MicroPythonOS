"""Manual desktop drag-event demo using MPOSController.

This starts a desktop MicroPythonOS process via MPOSController, installs an
event callback on lv.screen_active(), and streams pointer-related events to
this terminal while you interact with the SDL window.

Run:
    python3 tests/manual_test_pointer_drag_events_controller.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scripts.mpos_controller import MPOSController


SETUP_CODE = """
import lvgl as lv

_drag_demo_events = []

def _drag_demo_name(code):
    if code == lv.EVENT.PRESSED:
        return "PRESSED"
    if code == lv.EVENT.PRESSING:
        return "PRESSING"
    if code == lv.EVENT.RELEASED:
        return "RELEASED"
    if code == lv.EVENT.CLICKED:
        return "CLICKED"
    if code == lv.EVENT.PRESS_LOST:
        return "PRESS_LOST"
    return None

def _drag_demo_cb(event):
    code = event.get_code()
    name = _drag_demo_name(code)
    if name is not None:
        _drag_demo_events.append(name)

screen = lv.screen_active()
screen.add_flag(lv.obj.FLAG.CLICKABLE)
screen.remove_flag(lv.obj.FLAG.SCROLLABLE)

title = lv.label(screen)
title.set_text("Drag anywhere and watch terminal output")
title.align(lv.ALIGN.TOP_MID, 0, 20)

hint = lv.label(screen)
hint.set_text("Expect: PRESSED -> PRESSING... -> RELEASED")
hint.align_to(title, lv.ALIGN.OUT_BOTTOM_MID, 0, 10)

screen.add_event_cb(_drag_demo_cb, lv.EVENT.ALL, None)
"""


def main():
    print("Starting desktop MPOS via MPOSController...")
    print("Interact with the SDL window. Press Ctrl-C here to stop.\n")

    with MPOSController() as mpos:
        mpos.exec_multiline(SETUP_CODE)
        print("Callback installed. Waiting for events...\n")
        while True:
            try:
                raw = mpos.exec_multiline(
                    """
import json
events = _drag_demo_events[:]
_drag_demo_events[:] = []
print(json.dumps(events))
"""
                )
            except OSError as err:
                print("Controller connection closed:", err)
                break
            text = raw.decode("utf-8", "replace").strip()
            if text:
                events = json.loads(text)
                for name in events:
                    print("event:", name)
            time.sleep(0.2)


if __name__ == "__main__":
    main()
