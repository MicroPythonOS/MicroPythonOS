# Why HID presence disables the hub-watchdog idle auto-reset

## The problem

The watchdog's idle auto-reset heals ports that read **connected + enabled
but never produce a device** (slow-booting DisplayLink adapters, ~15s grace,
one `PORT_RESET`). A healthy, enumerated HID mouse or keyboard reads
**exactly the same way**: connected + enabled, no bus growth (it created its
address long ago and makes no new ones). Port status alone cannot tell
"wedged adapter, idle" apart from "healthy mouse, idle".

Without suppression, ~15s after plugging a mouse the watchdog would
`PORT_RESET` the mouse's own port: yanking a healthy device off the bus,
forcing re-enumeration, dropping input — and on ganged-power hubs browning
out the siblings. The mouse re-enumerates, reads idle again, and eats
another reset on the next mark cycle. The watchdog would DDoS our own input
devices. Parked keyboards are the same signature (enumerated but silent);
resetting one burns a bus address and re-parks it, since it can never claim
until something unplugs anyway.

## The rule

Port status cannot discriminate, so the watchdog defers to the one layer
that knows: the HID layer's claimed/parked lists. While any HID is claimed
OR parked, `USBManager._poll_hid()` (via `_update_hid_watchdog_exclusion`)
forces `auto_reset_idle` off and restores the prior value afterwards, so a
manual user setting is never forced back on.

Explicitly NOT suppressed: the disabled-port episode path (targeted resets,
backoff, VBUS power cycle). Only the *enabled*-idle quiet healer yields.
The judgment call: resetting a healthy mouse on a loop is worse than a
stuck adapter needing a manual `reset_port()` while HID is present.

## The cost (observed 2026-09-14)

The worst case stacks three independent things: (1) a hub port genuinely
failing descriptor reads (same-port replug never heals, different-port
heals in ~10s — hardware, suspect port/cable first), (2) a mouse plugged
in, suppressing the quiet healer, (3) a `switched to panel` event marking
the idle port preexisting. Any one alone, the system heals. All three, and
the log shows `enabled but idle` pointer lines with no auto-switch, forever.
This was misread as a refactor regression; normalized diffs of the
Python move (`board/usb_display.py` -> `mpos/usb/usbmanager.py`) and the C
split (`usb_disp_mpy.c` -> `usb_mpy.c` + `usb_display_mpy.c`) show zero
logic changes (3c32b029).

## Discriminators (live REPL, 30 seconds)

```python
import usb
from mpos import USBManager
usb.auto_reset_idle()          # bare call reads the toggle: False = suppressed or disabled
USBManager._hid_idle_prev      # non-None = suppression currently active (holds the saved value)
usb.hid_claimed_addrs()        # non-empty = a HID is holding suppression on
usb.hid_parked()               # non-empty = a parked device is holding suppression on
```

`_hid_idle_prev is not None` with something claimed/parked = suppression
working as designed. Toggle `False` with `_hid_idle_prev is None` and
nothing claimed/parked = real bug (toggle stuck off). Toggle `True`,
nothing claimed/parked, port unmarked, still never fires = episode-path
bug.

## Options (all P1-or-later, none needed for the exoneration)

- Narrow suppression to HID-owned ports only: skip auto-reset just for the
  port(s) the mouse/keyboard sits on, keep healing the rest. Caveat: the C
  layer knows claimed *addresses*, not which (hub, port) they hang off;
  that mapping needs hub-driver introspection that may not exist. Spike
  first, promise later.
- Class-aware skip: before auto-resetting an idle port, check whether its
  device is HID-class and skip only those. The `lsusb` HAL pass already
  opens idle devices, so the descriptor fetch is proven cheap there — but
  it is still more C work, and more EP0 traffic next to sick ports.
- Visibility line (recommended regardless): put the suppression reason in
  the pointer line, e.g. `[HUB] addr=1 port=3 enabled but idle
  (auto-reset suppressed: HID claimed; reset_port(1,3) if stuck)`. Zero
  behavior change; the confusion above becomes self-explaining in the log.
