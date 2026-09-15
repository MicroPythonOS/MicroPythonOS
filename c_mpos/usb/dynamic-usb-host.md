# Dynamic USB host activation / CDC restore plan

**Status: implemented (P1).** Spike probes replaced by
`usb.activate_host()` / `usb.deactivate_host()` + `usb_hid_stop()` +
`usb_disp_hal_stop()`; `USBManager.activate()` / `deactivate()` with
persisted `host_mode` pref; boot honors the flag with BOOTSEL escape;
Settings → "USB Host Mode" toggle; host harness lifecycle tests.
Remaining: device matrix verification (P2 in the original plan numbering).

## Problem

With `--usb`, the build used to pass `-DMICROPY_HW_ENABLE_USBDEV=0`, which
compiled out TinyUSB device mode entirely. This freed the OTG peripheral for
the IDF `usb_host` stack, but on boards where the only exposed serial port is
USB-CDC (no UART on GPIO43/44) the REPL disappeared after flashing and users
could not access the device.

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
- Settings → "USB Host Mode" (`On` persisted, `On until reboot` one-shot,
  `Off`): the framework persists the choice into the same
  `com.micropythonos.settings` / `usb_host_mode` key USBManager boots from,
  so UI, REPL and boot share one source of truth; the callback only
  switches modes via `USBManager.activate(persist=False)` /
  `deactivate(persist=False)`.
  - Stops TinyUSB CDC.
  - Starts IDF USB host.
  - Arms display + HID as today.
  - The `activate(persist=True)` default writes `"on"` to the shared key.
  - CDC gone until deactivated. UART/WebREPL still work if configured.
- Toggle OFF: calls `USBManager.deactivate(persist=True)` (writes `"off"`).
  - Stops host (HID client, display client, `usb_host_uninstall`).
  - Reinitializes TinyUSB PHY and `mp_usbd_init()`.
  - CDC returns; REPL rejoins automatically (`mphalport.c` polls/writes CDC
    dynamically).
- Persisted boot: `mpos/main.py` boots into host mode only when the shared
  key reads `"on"`. BOOT held forces CDC regardless of the stored value.

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

## P0 — spike (RESULTS, 2026-09-15)

**Verdict: the runtime transition is proven feasible, full stack included.**

With clean bench power, `usb._spike_host()` (`tud_deinit` + `usb_phy_deinit`
+ `usb_disp_init`/`hal_add`/`hal_start` + `usb_hid_start`) enumerates the
whole bench through the transition: hub + mouse staged + DisplayLink
descriptor walk + `bulk OUT configured`, `bus_devices()` = `[2, 3, 1]`,
`hub_ports()` correct. No crash, no hang.

Earlier failures in this session were environmental, not code:
- OTG backfeed power (externally powered hub feeding VBUS back) browned
  out the board on replugs: serial vanishing, reboots, phantom single-shot
  `hcd_port_command(RESET)` failures, 50 s silences that were reboot
  windows. Removing OTG external power fixed all of it.
- The console `/dev/ttyUSB0` is a CH340 **USB VM forward**: it can vanish
  independently of the board. If lost: halt and ask the user to reconnect,
  do not thrash.
- The `usbh_devs_addr_list_fill` LoadProhibited was a spike bug
  (`hal_start` with `s_nhal == 0` early-returns, leaving the stack
  uninstalled), not a transition bug.

**CDC restore: root-caused, fix designed (P1).** The naive
`usb_host_uninstall()` + `usb_phy_init()` + `mp_usbd_init()` crashes in
TinyUSB re-init: `dwc2_int_set` → `esp_intr_free` on a stale handle →
`esp_intr_disable` LoadProhibited (+0x20). TinyUSB's DCD frees its ISR
handle on deinit without NULLing it, so re-init double-frees. Fix: 4-line
patch NULL-guarding both `usb_ih` statics (dcd_esp32sx.c single +
dwc2_esp32.h array), plus proper teardown order in our path (deregister
clients, stop daemon/client/HID tasks, then uninstall) — the spike skipped
all teardown, which also contributed.

**Submodule note:** `usb_phy_deinit()` lives in `patches/usb_phy_deinit.patch`
(applied by `build_mpos.sh`, same convention as the other usb patches), not
as a submodule edit.

## Known P0 issues → P1 tasks

1. ~~Hub enumeration~~ CLOSED (environmental, proven working).
2. **CDC restore** — tinyusb ISR-handle patch + proper client/task teardown
   order (`usb_hid_stop()`, `usb_disp_hal_stop()`), then re-verify the
   round-trip.
3. ~~Display HAL init~~ CLOSED (spike bug, `hal_add` before `hal_start`).

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
