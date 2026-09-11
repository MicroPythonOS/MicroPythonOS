c_mpos/usb_display: MicroPython binding for Pico_USB_Disp (USB display adapters).

ESP32-only: DisplayLink DL-1xx via the in-tree IDF usb_host stack.
Build with: ./scripts/build_mpos.sh esp32s3 --usbdisplay
Python driver: internal_filesystem/lib/drivers/display/usb_disp/
Shared board helper: internal_filesystem/lib/mpos/board/usb_display.py
Boot hook: internal_filesystem/lib/mpos/main.py (arm_usb_display())

upstream/ holds a vendored snapshot (see upstream/VERSION). Only the
ESP32-relevant sources are used (upstream/CMakeLists.txt ESP-IDF branch):
usb_disp.cpp, usb_disp.h, usb_disp_hal.h, usb_disp_hal_esp32.cpp,
usb_disp_prot.h, usb_disp_prot_dl-1xx.cpp, usb_disp_model.h.
Deliberately excluded: hal_pico/hal_teensy/hal_libusb, lgfx/, pio/.
usb_disp_prot_t6.cpp / usb_disp_prot_ms91xx.cpp (+ jpeg header) are vendored
but only compiled on ESP32-P4 (they need USB High-Speed; empty stubs
elsewhere) to save flash.
To update: re-copy those files from a new upstream checkout, refresh
upstream/VERSION, keep upstream/LICENSE.Pico_USB_Disp, rebuild.

Note: the vendored sources are used UNMODIFIED. Every adaptation lives
outside upstream/: this binding, micropython.cmake, the IDF settle patch
(patches/usb_ext_port_settle.patch), and the Python side. If an upstream
fix is needed, prefer updating the snapshot over forking files.

=====================================================================
What it took to get hotplug / hot-unplug working, per level
=====================================================================

--- USB level (adapter, hubs, monitor) ---
- Only DisplayLink DL-1xx works on ESP32-S3 (Full-Speed OTG). DL-165/DL-195
  recommended. T6/MS91xx need High-Speed = ESP32-P4 only.
- The adapter holds the framebuffer; the MCU streams span updates. Pixel
  data is copied synchronously into the bulk ring, so LVGL buffers can be
  reused the moment the flush call returns.
- IDF usb_host has NO external-hub support by default: without
  CONFIG_USB_HOST_HUBS_SUPPORTED (+ MULTI_LEVEL for cascaded hubs),
  downstream devices never enumerate (the hub itself is seen, nothing
  behind it). Enabled in --usbdisplay builds only.
- Hotplug race (the big one): a DL chip boots its own firmware for 1-2s
  after power-on, but the stack resets a new port within ~300ms. An early
  reset wedges the adapter's EP0 until its next POWER cut (USB resets and
  root-port power cycles do not recover it behind externally powered
  hubs). Fixes, both in --usbdisplay builds only:
  - patches/usb_ext_port_settle.patch: 2s settle before a hub port's
    first reset, compiled to a no-op without -DMPOS_USB_PORT_SETTLE_MS
    (same repo patch-file convention as the other .patch files).
  - CONFIG_USB_HOST_DEBOUNCE_DELAY_MS=2000 covers root-port-direct
    adapters (hub downstream ports are NOT covered by debounce).
  - More reset attempts are NOT available: EXT_PORT_RESET_ATTEMPTS is
    locked behind IDF_EXPERIMENTAL_FEATURES, and retries are spaced ~30ms
    apart anyway (never spans a 1-2s boot). The enum-filter callback runs
    after the descriptor read, so it cannot defer the fatal first reset.
- Monitor floor: HDMI/DVI needs >= 25 MHz pixel clock, so 640x480@60
  (25.175 MHz) is the smallest syncable mode. Anything smaller (e.g.
  320x240 @ 7.3 MHz) programs fine on the chip but no monitor locks it.
  The helper defaults to 640x480 and documents the floor.
- Broken hub ports fail exactly like a wedged adapter (EP0
  CHECK_SHORT_DEV_DESC, port disabled after the single attempt). Each
  failed attempt consumes a stack device address. When stuck, suspect the
  port/cable before the firmware, and power-cut the ADAPTER (not the
  board) to unwedge.
- usb_disp_force_reenum() (root-port power cycle) recovers missed events
  but NOT a wedged adapter behind externally powered hubs.

--- FreeRTOS level (host stack, tasks, coexistence) ---
- Upstream spawns usbd_daemon + usbd_client tasks; enumeration is
  event-driven, but the app must still poll: usb_disp_poll() drives
  WAIT -> MODE_SETUP -> READY (and reconnect/re-enumeration).
- MicroPython's TinyUSB *device* stack owns the single OTG peripheral at
  boot, so --usbdisplay builds compile it out (MICROPY_HW_ENABLE_USBDEV=0).
  There is no runtime device<->host handover: mp_usbd_deinit() only
  soft-disconnects, the driver/PHY stay resident. Console remains over
  UART REPL; USB-Serial-JTAG shares the OTG pins so it is unreachable
  only while the adapter is plugged (WebREPL over WiFi still works).
- Upstream has no remove API and one slot on ESP32, so the binding reuses
  usb_disp_at(0) once added: REPL retries, repeated constructions, and
  the Settings-toggle path all share the handle (original resolution
  config is kept; use set_mode() to change it).
- CFLAGS_EXTRA reaches IDF component compiles (verified in flags) — that
  is how -DESP_PLATFORM and -DMPOS_USB_PORT_SETTLE_MS get to usb_host
  code while staying scoped to --usbdisplay builds.

--- LVGL level (displays, rendering, input, topmenu) ---
- The Python driver subclasses DisplayDriver behind a fake bus shim
  (bytearray buffers, tx_color -> update_565 + flush, synchronous
  flush_ready like the SDL bus). PARTIAL mode, RGB565, rotation fixed _0
  (adapter limitation, enforced by raising on anything else).
- Multiple displays coexist; the Ulrichscreen always keeps a loaded blank
  screen: refreshing a screenless display wedges the port hard (proven by
  bisection, no traceback). Never leave a display without a screen while
  anything can tick.
- Touch: LVGL transforms driver points from the physical frame itself, so
  the helper composes instead of configuring: it shadows each pointer
  indev's _calc_coords with panel_mapping -> portrait-to-landscape
  affine, reusing the panel's proven (possibly user-calibrated) mapping.
  No touch-native ranges or per-board tables; only boards failing the
  drag test get a one-line direction/mirror exception. Switch-back deletes
  the shadow (del restores the class method); nothing is persisted.
- Topmenu moves, never recreates: bar/drawer are reparented across
  displays (legal per lv_obj_set_parent source) with geometry recomputed,
  because recreating would leak singleton timers bound to old labels and
  crash when they fire. Focus entries only join groups while open, so the
  move is group-safe; drawer lands closed; brightness slider is a no-op
  on USB.
- Drawer-close by swipe-up broke on big displays: it was detected via
  scroll events, which only fire when content overflows the viewport (true
  on 288px panels, false on 432px USB). Now press/release net movement
  closes with the same threshold; the scroll path stays alongside.
  The drawer needed FLAG.CLICKABLE for empty areas to report presses.
- InputManager populations vary: fri3d registers a raw lv_indev_t keypad
  next to driver wrappers, so the re-point path uses getattr with the raw
  object as fallback instead of assuming wrappers.

--- MPOS level (boot, tasks, UI lifecycle) ---
- TaskHandler pumps LVGL via machine.Timer + micropython.schedule ON THE
  MAIN THREAD (there is no LVGL thread). Pump callbacks interleave
  teardown bytecodes, so the swap suspends the pump first (idempotent
  flag, resumed in finally blocks) — a hard freeze with dead Ctrl-C was
  the symptom before this.
- No board-file changes: mpos.main calls arm_usb_display() (construct +
  start + poll timer, ~1ms, never blocks boot); the existing 1s poll
  timer is the whole event system (no asyncio watcher needed — the stack
  is event-driven and poll() just advances the state machine). On a READY
  transition with the panel active it auto-switches; on disconnect with
  USB active it auto-reverts. Event-gated, so failed switches can't
  retry-storm. _auto_switch is the seam for the future Settings toggle.
- Swap order (all validated on hardware): disable pump -> disable indevs
  -> remove_and_stop_all_activities() -> blank old display -> blank handled
  -> set_default + reassign main_display -> repoint indevs (+ touch wrap)
  -> DisplayMetrics -> move topmenu -> recreate gesture zones -> start
  launcher -> re-enable. The panel object is never deleted (switch-back
  needs no board re-init); the USB object is deleted on switch-back to
  free its buffers.
- Backlight restore must go through set_backlight, never trust
  get_backlight: fri3d overrides set_backlight with an expander lambda
  while get_backlight reads a nonexistent pin (-1), which silently skipped
  the restore and left the panel dark. Fall back to the
  display_brightness setting (default 100), the same source the drawer
  slider persists.
- Flash budget is structural: 3.5 MiB app partition, hard size check.
  Room came from skipping the frozen usb-device framework in host builds
  (MPOS_NO_USBDEV, ~6.3 KiB, nothing imports it) and P4-gating the HS
  protocols — not from shaving. Real headroom needs partition or
  build-system work, not more trimming.

--- Debugging notes ---
- bus_devices() (stack address list) separates "nothing sensed"
  (cable/power/stack) from "hubs only" (adapter missing/wedged) from
  "adapter present, failing" in one call.
- Dead Ctrl-C + dead UART + alive USB tasks = main thread wedged in C;
  bisect with refr_now() per display (screenless refresh was the killer).
- The full swap runs clean on the desktop unix build between two SDL
  displays (tmp/run_swap_repro.py via mpos-controller) — use it to
  separate pure-LVGL bugs (gdb-speed) from device-specific ones.

Build lessons (do not regress):
- Do NOT target_link_libraries() idf:: component aliases here. usermod.cmake
  recurses INTERFACE_LINK_LIBRARIES into MICROPY_INC_USERMOD, which drags
  every transitive IDF include dir (including relative ones) into main's
  idf_component_register and breaks configure. Include dirs are propagated
  lcd_bus-style via idf_component_get_property instead.
- ESP_PLATFORM must be an INTERFACE compile definition, not just a
  CFLAGS_EXTRA flag: the esp32 port also compiles usermod sources into the
  top-level micropython.elf target (verified in the link map), which
  ignores MICROPY_CPP_FLAGS. Per-source -Os matters for the same reason.
