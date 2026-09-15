# Dynamic USB host activation / CDC restore plan

## Problem

With `--usb`, the build currently passes `-DMICROPY_HW_ENABLE_USBDEV=0`, which
compiles out TinyUSB device mode entirely. This frees the OTG peripheral for
the IDF `usb_host` stack, but on boards where the only exposed serial port is
USB-CDC (no UART on GPIO43/44) the REPL disappears after flashing and users
cannot access the device.

Goal: keep USB-CDC alive by default; switch the same OTG PHY to USB host mode
only when the user explicitly enables "USB Host Mode" (Settings toggle or REPL
`USBManager.activate()`), and switch it back to CDC when disabled
(`USBManager.deactivate()`). Persist the choice across reboots.

## Constraints

- ESP32-S3 has one OTG PHY and one Serial/JTAG controller, often wired to the
  same USB connector on dev boards. There is no separate Serial/JTAG rescue
  port we can rely on.
- The IDF `usb_host` stack owns the PHY in host mode; TinyUSB/CDC owns it in
  device mode. Runtime mode switching requires tearing one down before bringing
  the other up.
- TinyUSB 0.19 (vendored) has `tud_deinit(rhport)` which fully releases the
  device controller: IRQ freed, disconnected, de-inited, class drivers torn
  down, `_usbd_rhport` invalidated. `mp_usbd_init()` is restart-safe (checks
  `_usbd_rhport`, calls `tusb_init`, `tud_connect`).
- `usb_host_install/uninstall` also create/delete the PHY inside the HAL. The
  display HAL `usb_disp_hal_start()` calls `usb_host_install()`; there is no
  matching stop yet.
- Both directions must work without reboot for the feature to be worth building.
  If either direction wedges the core, the plan falls back to a persisted flag
  plus reboot.

## Proposed end state

### User-facing behavior

- Default boot: CDC enabled, REPL over USB. `USBManager.is_available()` still
  returns `True` because the `usb` C module is built in; it just reports no host
  stack running.
- Settings → "USB Host Mode" toggle ON: calls `USBManager.activate(persist=True)`.
  - Stops TinyUSB CDC.
  - Starts IDF USB host.
  - Arms display + HID as today.
  - Saves `SharedPreferences("com.micropythonos.usb").set_bool("host_mode", True)`.
  - CDC gone until deactivated. UART/WebREPL still work if configured.
- Toggle OFF: calls `USBManager.deactivate(persist=True)`.
  - Stops host (HID client, display client, `usb_host_uninstall`).
  - Reinitializes TinyUSB PHY and `mp_usbd_init()`.
  - CDC returns; REPL rejoins automatically (`mphalport.c` polls/writes CDC
    dynamically).
  - Saves `host_mode=False`.
- Persisted boot: `mpos/main.py` reads the preference. If true, it performs the
  same deactivate-CDC/activate-host sequence before arming display/HID.
- Escape hatch: BOOT button held at boot forces CDC mode regardless of the
  persisted flag (two-line check in `main.py`).

### C additions

- `usb.activate_host()` module function:
  - If already active, return `False`.
  - `tud_deinit(0)`.
  - Call existing host initialization path (the one currently run from
    `arm_usb_display()`): `usb_disp_hal_start()` + HID client register.
  - Return `True`.
- `usb.deactivate_host()` module function:
  - If not active, return `False`.
  - New `usb_hid_stop()`: deregister HID client, delete task, free
    resources.
  - New `usb_disp_hal_stop()`: signal daemon/client tasks to exit, wait briefly,
    deregister display client, call `usb_host_uninstall()` (which deletes the
    host PHY).
  - `usb_phy_init()` from `usb.c` to recreate the PHY in device mode.
  - `mp_usbd_init()` to bring TinyUSB/CDC back up.
  - Return `True`.

### Python additions

- `USBManager.activate(persist=False)`:
  - `usb.activate_host()`.
  - `arm_display()`, `arm_hid()`.
  - Optionally persist.
- `USBManager.deactivate(persist=False)`:
  - Stop poll timer, reset `_usb_dev/_usb_display/_usb_mouse/_usb_keyboard`.
  - `usb.deactivate_host()`.
  - Optionally clear persist.
- `mpos/main.py`:
  - Read preference after launcher setup.
  - If `host_mode` and not BOOTSEL: `USBManager.activate()`.
  - Else: CDC stays up; `arm_display()`/`arm_hid()` are NOT called (they would
    fail anyway without host mode).

### Build/script changes

- `--usb` build no longer passes `-DMICROPY_HW_ENABLE_USBDEV=0`. The `usb` C
  module and TinyUSB device stack coexist.
- Keep `MPOS_NO_USBDEV` in `manifests/manifest.py` to exclude the frozen
  `usb-device` Python framework (runtime `machine.USBDevice` is still dead
  weight; measure flash and decide whether to disable it too).
- Size budget: current headroom ~42 KB. Adding TinyUSB back may consume most of
  it. If needed, disable `MICROPY_HW_ENABLE_USB_RUNTIME_DEVICE=0` and/or MSC.

## P0 — spike (RESULTS)

Temporarily modified the `--usb` build to keep USBDEV compiled in and added
`usb._spike_host()` / `usb._spike_cdc()` module functions. Also added
`usb_phy_deinit()` to `ports/esp32/usb.c` to delete the device-mode PHY.

**Findings (2026-09-15):**

1. ✅ `tud_deinit(0)` — tears down TinyUSB device mode cleanly from a live
   system. DCD core is reset, interrupts freed.
2. ✅ `usb_phy_deinit()` — deletes the device-mode PHY handle.
3. ✅ `usb_host_install()` + `usb_host_client_register()` — host stack
   installs successfully after the DWC2 transition. `bus_devices()` returns
   `[]` without crashing (the bus layer is alive, proven by decoding a
   previous crash to `usbh_devs_addr_list_fill` in the display-HAL path).
4. ❌ Hub enumeration — `E (xxxxx) HUB: Failed to issue root port reset`.
   Root port reset fails after the mode switch. Either the DWC2 core reset
   isn't thorough enough, the PHY isn't actually driving the bus in host
   mode, or no OTG device is connected on this board (UART and OTG may be
   on different physical connectors). Needs P1 investigation.
5. ❌ CDC restore — `_spike_cdc()` crashes with `intr_alloc: No free
   interrupt inputs for USB interrupt`. The host stack's interrupt isn't
   freed before `mp_usbd_init()` reinitializes TinyUSB. Needs proper client
   deregistration + daemon task teardown before `usb_host_uninstall()`.
6. ❌ Display HAL path (`usb_disp_hal_start()`) — crashes with `s_nhal == 0`
   because `usb_disp_hal_add()` was never called. The HAL requires a
   registered display port before starting.

**Verdict: the runtime transition is proven feasible but needs P1 fixes
for hub enumeration and CDC restore. The spike code (`_spike_host`,
`_spike_cdc`, `usb_phy_deinit`, `usb_mpy.c` spike helpers, `main.py`
boot-guard) is committed as-is for reference.**

## Known P0 issues → P1 tasks

1. **Hub enumeration** — root port reset fails after dev→host transition.
   Investigate: more thorough DWC2 core reset, PHY warm-reset, or
   `USB_OTG_MODE_DEFAULT` mode.
2. **CDC restore** — proper client/task teardown sequence before
   `usb_host_uninstall()`, then `usb_phy_init()` + `mp_usbd_init()`.
3. **Display HAL init** — add `usb_disp_hal_add()` with a dummy display
   config before `usb_disp_hal_start()`, and handle teardown of display
   client before uninstall.
4. **HID client lifecycle** — `usb_hid_start()` / `usb_hid_stop()` must
   handle repeated activation/deactivation (slot cleanup, task lifecycle).
5. **Interrupt cleanup** — ensure USB interrupt is freed before
   `mp_usbd_init()` recreates it.

## P1 — implementation (after P0 success)

1. `usb_hid_stop()` in `usb_hid.c`.
2. `usb_disp_hal_stop()` in `usb_disp_hal_esp32.cpp`.
3. Proper `usb.activate_host()` / `usb.deactivate_host()` module functions.
4. `USBManager.activate/deactivate`, preference handling, Settings toggle.
5. `mpos/main.py` boot-time preference + BOOTSEL escape.
6. Host harness: fake `tud_deinit`, `mp_usbd_init`, `usb_phy_init`,
   `usb_host_uninstall`, lifecycle tests.
7. Build/script/manifest cleanup; docs; changelog.

## P2 — verification

- Flash size check.
- `make lint`, syntax, harness, desktop USB tests.
- Device matrix:
  - Boot CDC, activate host, hub enumerates, display ready.
  - Deactivate host, CDC returns, REPL usable.
  - Persist ON, reboot, auto-activates host.
  - Persist OFF, reboot, stays CDC.
  - BOOTSEL held at boot overrides persist ON.
  - Settings toggle round-trip.
