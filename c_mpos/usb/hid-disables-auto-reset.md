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

## The rule (v2: port-exact skip)

Port status cannot discriminate, so the layer that knows the HID ports
tells the watchdog. Two mechanisms, split by resolvability:

- **Claimed devices (open handle): port-exact skip in C.**
  `usb_hid_owns_idle_port(hub, port)` resolves any open HID handle to its
  (hub, port) via the `device_info()` parent chain (cached reads, no EP0
  traffic). The sweep skips the quiet auto-reset exactly on HID-owned
  idle ports and logs the reason inline:
  `[HUB] addr=1 port=3 HID device, auto-reset skipped`. Other ports keep
  healing. A recheck at fire time closes the claimed-during-grace race.
  Any non-empty slot counts (streaming, polled, staged, closing).
- **Parked devices (no handle): global suppression in Python.**
  `USBManager` forces `auto_reset_idle` off while the parked list is
  non-empty and restores the prior value after (a manual user setting is
  never forced back on). Parked ports are unresolvable, so this stays
  global. Previously claimed devices also forced it off; they no longer
  need to.

Explicitly NOT suppressed either way: the disabled-port episode path
(targeted resets, backoff, VBUS power cycle). Only the *enabled*-idle
quiet healer yields. The judgment call stands: resetting a healthy mouse
on a loop is worse than a stuck adapter needing a manual `reset_port()`
while a parked HID is present.

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

- ~~Narrow suppression to HID-owned ports only~~ DONE (v2 above):
  the feared hub-driver introspection was unnecessary, the
  `device_info()` parent chain resolves it. No spike was needed.
- ~~Class-aware skip~~ DROPPED: needs the same port resolution *plus*
  descriptor fetches on potentially-sick ports (the observed
  `CHECK_SHORT_DEV_DESC` failure mode) *plus* interface walks (mice are
  class-0 at device level). All risk for a win the port-exact skip
  already delivers, without teaching new device classes.
- ~~Visibility line~~ DONE (v2 above): the skip reason prints inline at
  the sweep site, so the log explains itself.
