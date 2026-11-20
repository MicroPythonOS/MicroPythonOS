"""Manual two-finger check for an FT6x36 touch panel.

Run this on the device, put two fingers on the screen (one on the left half,
one on the right), and read the lines it prints. It reads the controller's raw
registers, not the driver's parsed output, so a panel that only reports one
point can be told apart from a driver bug. The register map is the FT6x36's
(0x02 status, 0x03 point 1, 6 bytes per point); on another controller the raw
part is meaningless, though the ``driver`` lines still show what
``get_touches()`` returns.

    >>> exec(open('tests/manual_test_multitouch.py').read())

or from the host:

    python3 scripts/test_runner.py tests/manual_test_multitouch.py --ondevice

What to look for:

* ``status`` is the number of points the controller says it sees. Two fingers
  must show ``2``.
* each point prints the event flag (0 press, 1 lift, 2 contact, 3 no event),
  the ``id`` field from Bits 7:4 of Pn_YH, and the decoded coordinates.
* ``driver`` is what ``get_touches()`` makes of the same report, already turned
  into logical panel points.

The summary at the end tells you the most points seen and how many reports had
two. A panel that never reports ``2`` cannot do two-thumb input no matter what
the driver does.
"""

import time

import mpos
from mpos.ui.input_manager import InputManager
from mpos.ui.multitouch import read_touches

STATUS_REG = 0x02
POINT_1_REG = 0x03
POINT_SIZE = 6
MAX_POINTS = 2
SECONDS = getattr(mpos, "MULTITOUCH_SECONDS", 25)
EVENTS = ("press", "lift", "contact", "no-event")


def _indev():
    for indev in InputManager.list_indevs():
        if hasattr(indev, "get_touches"):
            return indev
    return None


def _read(device, register, count):
    tx = bytearray(1)
    tx[0] = register
    rx = bytearray(count)
    device.write_readinto(tx, rx)
    return rx


def _decode(buf, count):
    points = []
    for index in range(count):
        offset = 1 + index * POINT_SIZE
        event = buf[offset] >> 6
        x = ((buf[offset] & 0x0F) << 8) | buf[offset + 1]
        y = ((buf[offset + 2] & 0x0F) << 8) | buf[offset + 3]
        point_id = buf[offset + 2] >> 4
        points.append((index, EVENTS[event], point_id, x, y))
    return points


indev = _indev()
if indev is None:
    print("no panel with get_touches(); this board cannot report two fingers")
else:
    device = indev._device
    print("panel:", type(indev).__name__)
    print("polling for %d s - put two fingers down now" % SECONDS)
    seen = 0
    two = 0
    last = None
    end = time.ticks_add(time.ticks_ms(), SECONDS * 1000)
    while time.ticks_diff(end, time.ticks_ms()) > 0:
        raw = _read(device, STATUS_REG, 1 + MAX_POINTS * POINT_SIZE)
        status = raw[0] & 0x0F
        points = _decode(raw, min(status, MAX_POINTS))
        # Read through the driver as well, so a parsing problem shows up.
        indev._get_coords()
        logical = read_touches(indev)
        line = (status, tuple(points), tuple(logical))
        if line != last:
            print("status", status, "raw", points, "driver", logical)
            last = line
        if status:
            seen += 1
            if status >= 2:
                two += 1
        time.sleep_ms(50)
    print("reports with touch:", seen, "of which two points:", two)
    print("chip id:", _read(device, 0xA3, 1)[0],
          "gesture mode 0xD0:", _read(device, 0xD0, 1)[0])
