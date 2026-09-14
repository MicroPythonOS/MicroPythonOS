c_mpos/usb_display: MicroPython binding for Pico_USB_Disp (USB display adapters)
plus a minimal USB HID host transport (boot-protocol mice + keyboards).

ESP32-only: DisplayLink DL-1xx via the in-tree IDF usb_host stack.
Build with: ./scripts/build_mpos.sh esp32s3 --usbdisplay
Python driver: internal_filesystem/lib/drivers/display/usb_disp/
HID Python driver: internal_filesystem/lib/drivers/indev/usb_hid.py
Shared board helper: internal_filesystem/lib/mpos/board/usb_display.py
Boot hook: internal_filesystem/lib/mpos/main.py (arm_usb_display(), arm_usb_hid())

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

Note: upstream/ is a vendored snapshot, but NOT untouched in practice:
the hub-port watchdog, lsusb(), and a held-handle hook for streaming HID
devices all live in upstream/usb_disp_hal_esp32.cpp (see git log for that
file), alongside the IDF settle patch (patches/usb_ext_port_settle.patch)
and this binding. Rationale: the alternative (reimplementing hub
recovery/inspection around an unmodified HAL) would duplicate far more
code than the surgical hooks. Rule of thumb: keep MPOS adaptations
clearly commented and separable; if upstream ever gains the same feature,
prefer re-vendoring over keeping the fork. New standalone features
(e.g. src/usb_hid.c) still go outside upstream/.

=====================================================================
REPL API reference (all on `import usb_disp`, --usbdisplay builds only)
=====================================================================

USBDisp(port=0, width=0, height=0, ignore_edid=False) - adapter handle.
Single slot on ESP32: repeated constructions reuse usb_disp_at(0)
(original resolution kept; use set_mode() to change it).
- start() - start the USB host for all registered ports (call once).
- poll() -> bool - drive WAIT -> MODE_SETUP -> READY; True on
  READY/disconnect/mode change (the 1s LVGL timer calls this).
- ready() -> bool, width() -> int, height() -> int, chip_name().
- update_565(x, y, w, h, buf) / fill(x, y, w, h, color) / flush(timeout_ms=100).
- set_mode(width, height) - resolution change at 60Hz (redraw required).
- force_reenum() - root-port power cycle: virtual replug of the whole
  subtree. Recovers wedged adapters and stack-disabled ports, NOT a
  wedged adapter behind externally powered hubs (power-cut the ADAPTER).

Module-level inspection (read-only, safe any time):
- bus_devices() -> [addr] - stack address list + held display/HID
  addresses re-added (claimed devices leave the idle list).
- lsusb() -> str - "Bus 001 Device 002: ID 17e9:028f DisplayLink ..."
  Bus is always 001 (single OTG controller), no root-hub line.
  Streaming HID devices are read through their held handles (never
  reopened mid-stream); held addresses the HAL pass skipped get a
  generic `HID mouse`/`HID keyboard` fallback line, deduped by address.
- hub_ports() -> [(hub_addr, port, connected, enabled, high_speed)].
  (connected=True, enabled=False) = stack gave up on this port.
- reset_port(hub_addr, port[, power_cycle[, force]]) - re-enumerate one
  port, rest of chain untouched. High-speed (uplink) targets refused
  unless force=True (resetting one drops the subtree and aborts the
  IDF enumerator - proven crash). Never reset a parked HID's port
  (see HCD channels section).
- set_watchdog(on) (default on), auto_reset_idle([on]) (default on;
  bare call reads back). See the watchdog section below.

HID (same module, same build):
- hid_start() -> bool - register the HID client; False while the host
  is down (retried automatically by the poll timer).
- hid_poll() -> bool - pump setups/health; True on device-set change.
- hid_drain() -> [(addr, subclass, protocol, bytes)] - raw boot
  reports since last call (consumed by drivers/indev/usb_hid.py).
- hid_state() -> [(addr, kind, vid, pid, speed)] - streaming devices
  only. kind is "mouse" or "keyboard"; speed is 0=low, 1=full,
  2=high (low-speed devices behind a hub need split transactions -
  decisive for TT-overload theories, so it is captured at stage time
  and exposed here).
- hid_claimed_addrs() -> [addr] - held-open addresses (watchdog
  exclusion + bus_devices/lsusb re-add).
- hid_parked() -> [(vid, pid, kind, fails)] - parked (fails=255) or
  cooling-down devices. Non-empty + "No more HCD channels" = channel
  exhaustion, not a wedged device.
- hid_retry() - clear parked/cooldown and rescan now (plug/unplug
  re-arms automatically).
- hid_poll_stats() - [(addr, kind, polls, ch_fails)] for live
  transiently-polled keyboards (see polling note above).
- hid_verbose([on]) - per-tick debug flag, off by default (bare call
  reads it back). When on, each transient tick logs [HID][V]
  claim/submit/wait outcomes. Opt-in only: at ~20 ticks/s it would
  drown the REPL (and any file transfer) otherwise.
- hid_loop_lag() - ms since the HID client task last pumped stack
  events. Reads ~100 in steady state; seconds indicate event delivery
  (completions, teardowns, rescans) is stalled - e.g. app-thread
  control traffic (watchdog sweep, lsusb opens, setup ctrls) with
  multi-second timeouts serializing shared stack locks. If teardown
  ever lags a flagged error by seconds, read this first: it separates
  a stalled event loop from a wedged bus.
- hid_set_kbd_transient([on]) - keyboard transport experiment switch.
  Default persistent (False): keyboards claim a standing interrupt
  pipe like mice, exactly pre-Phase-A behavior. True selects
  transient per-tick polling (needed under display channel pressure).
  Bare call reads back. Live keyboards re-stage on flip, so both modes
  are A/B-testable on one firmware without reflashing.

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
- Slow-boot race, part 2 (replugged adapters, some hub ports): even with
  the settle patch, a port read while the chip is still booting fails the
  single CHECK_SHORT_DEV_DESC attempt and the port stays DISABLED forever
  (IDF's own recycle path cannot recover pre-enumeration failures:
  "Ext hub port recycle error: ESP_ERR_INVALID_ARG"). Linux xHCI retries
  transparently, which is why the same hub+adapter works on a PC. Fix in
  the HAL (usb_disp_hal_esp32.cpp, --usbdisplay builds only): a hub-port
  watchdog sweeps every external hub with read-only GET_PORT_STATUS while
  no display is attached and recovers ports stuck connected-but-
  unenumerated: up to 3 targeted SET_FEATURE(PORT_RESET)s with growing
  backoff (~4s/~12s/~28s stuck time), then one PORT_POWER off/on cycle,
  then silence until the connection flaps. Episodes close as "enumerated"
  only on bus-address-count growth after episode-open — never on the
  enabled bit alone, which can read set on an unaddressed port when the
  stack wedges mid-enumeration. Enabled ports are never touched;
  change bits are never cleared (that would steal the connect
  event from IDF's hub driver). Every transition and action is logged
  ([HUB] lines) with per-port counters: "connected, waiting" opens an
  episode, "reset N/3 (stuck Ns)" / "power cycle (stuck Ns, N resets
  done)" narrate recovery, "enumerated/unplugged, episode over (stuck
  Ns, N resets[+power])" closes it. A dead-silent hub (EP0 unresponsive,
  first breaker trip) plus stuck ports escalates to an automatic root
  power cycle (max 3 per boot, logged loudly) — proven to revive hubs
  nothing else touches; fresh addresses reset all watchdog state
  naturally. A port that reads enabled with no
  episode gets one neutral pointer line naming its reset_port() call —
  and, with auto_reset_idle (default on, usb_disp.auto_reset_idle()
  toggles it, bare call reads it back), one automatic PORT_RESET after
  a 15s grace, but only if that port is not marked preexisting: marks
  go onto idle ports at boot, hub plug, and display-unplug snapshots
  (uplinks are always idle then), and any observed disconnect clears
  them — so tracking works even when the unplug itself happens mid
  display, with no dependence on catching the transient. One shot per
  mark cycle; healthy devices address first and close the episode.
  (An earlier blind version fired on any idle port
  and deafened hubs, because an unchirped hub reads full-speed just
  like a stuck adapter.) Episodes open on disabled ports only (fresh
  flaps wait for the stack to attempt first); dues defer while the bus
  is growing or the hub is younger than 10s, so resets never collide
  with in-flight enumerations. High-speed ports are never auto-reset:
  they carry cascaded hubs, and resetting one drops the whole subtree,
  which aborts the IDF enumerator (control_request_string default arm)
  and reboots the board — proven by four identical crash dumps. A hub
  whose EP0 stays dead gets 30s/60s/120s backoffs, then a quiet 120s
  probe rhythm instead of log spam. Manual equivalents for the REPL:
  usb_disp.hub_ports() lists (hub_addr, port, connected, enabled, high_speed) and
  usb_disp.reset_port(hub_addr, port[, power_cycle[, force]]) re-enumerates
  one port without disturbing the rest of the chain (unlike force_reenum's
  root-port power cycle); high-speed targets are refused unless
  force=True (never use it on an uplink mid-enumeration).
  usb_disp.set_watchdog(False) opts out.
- Wait guidance (measured against a DL-195 that needs 1-2s to boot,
  longer when browned-out by rapid VBUS cycling): judge a plug only
  after ~5s hands-off (the watchdog heals slow boots by itself);
  leave ~2-3s between unplug and replug (VBUS drain + disconnect
  processing; instant replugs risk the stack's "gone during reset"
  path). Rapid port-hopping always looks broken — every replug
  cold-boots the adapter, so it is time, not the port, that heals.
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
  USB active it auto-reverts. Event-gated with a bounded level retry
  (every ~5s, max 6 per episode, budget reset by any bus event), so a
  switch that fails transiently mid-boot still lands without a
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

--- USB HID level (boot-protocol mice + keyboards) ---
- Transport is minimal on purpose (no espressif/usb_host_hid managed
  component: ~51 KB flash + a managed `usb` override that would shadow
  the in-tree component our settle patch targets). src/usb_hid.c owns a
  second usb_host client + task on the shared stack (one device may be
  opened by both clients at once). One upstream hook: lsusb reuses our
  held handle for streaming HID devices instead of reopening them
  mid-stream (same reason the display HAL keeps its own handle).
- Two-stage setup avoids a deadlock: the client task only opens/stages
  candidates; blocking SET_PROTOCOL/SET_IDLE run in hid_poll() on the
  app thread (same pending_probe pattern as the display). Interrupt
  callbacks only memcpy into a 64-entry SPSC ring and resubmit.
- Parsing is Python-side (drivers/indev/usb_hid.py parser registry +
  HIDHub demux: mouse events queue, keyboard keeps the latest 8-byte
  report), so new device kinds never need C changes. USBHIDKeyboard
  subclasses Fri3dCommunicatorKeyboard unchanged (same HID->LVGL table,
  repeat logic, ESC/arrows nav hooks); USBMouse + keyboard share one
  hub, armed together by arm_usb_hid(), enabled per-kind from
  hid_state() (kind-aware _sync_usb_hid).
- Transient keyboard polling (Phase A experiment): keyboards hold NO
  persistent interrupt pipe. A poll task ticks each keyboard at a calm
  50ms floor (bInterval above that is respected up to 100ms): claim ->
  submit one IN transfer -> wait (30ms timeout) -> copy any report to
  the ring -> free -> release, then   sleep. The 10ms original ticked
  claim/CLEAR_FEATURE/submit/halt/flush/release 100x/sec and knocked
  cheap hub TTs off the bus (whole-hub re-enumeration every few
  seconds, taking mouse+keyboard down together); 50ms keeps typing
  responsive while staying an order of magnitude quieter. Toggle
  resync (CLEAR_FEATURE: fresh pipes start DATA0 while the device
  kept its sequence) runs on every tick - without it only the first
  report after each resync lands and releases are lost, freezing the
  Python key state at the last press (endless typematic repeat), so
  per-tick resync is load-bearing, not hygiene. Steady state holds hub + display + mouse
  pipes only, so the full combo fits the S3 budget with margin to
  spare. Boot reports are level-state, so tick-rate sampling loses
  nothing vs native polling (only a press+release inside one tick is
  invisible - same as hardware bInterval sampling). Mice keep
  persistent pipes for now (Phase B would move them too).
  Teardown choreography per tick (the hard-learned part): a halted
  transfer must be reaped (halt -> flush -> bounded wait for the
  CANCELED completion -> clear) BEFORE its memory is freed and the
  interface released. Freeing early strands the endpoint object in the
  stack ("EP already allocated" on the next claim, every ~10ms
  forever) and risks use-after-free when the late completion fires -
  exactly the failure the first Phase A firmware showed. A slow answer
  arriving between timeout and halt is kept, not dropped.
  A wait that expires with no data is NEUTRAL (idle keyboard NAKs),
  never a failure: reap, free, next tick. Only genuine errors feed
  backoff/parking, and a completed tick (with or without data) resets
  the consecutive-failure count. Rationale for the short 30ms bound:
  responsiveness comes from the tick rate, not the pend length - a
  keypress just after a timeout is caught by the next tick - while a
  long pend would hold a channel doing nothing, defeating the point.
  Lifecycle lines (the only polling logs by default):
  "keyboard polling started (addr=N, every Mms)" on first keyboard,
  "keyboard polling stopped (N polls performed, M channel-fails)" when
  the last one goes away. Per-tick failures are silent counters;
  usb_disp.hid_poll_stats() returns [(addr, kind, polls, ch_fails)]
  per live keyboard - sample twice and diff polls for the effective
  rate. 50 consecutive channel failures parks (see below); other
  tick failures use the normal transient backoff.
- Watchdog coexistence: a healthy/enumerated HID reads exactly like a
  wedged adapter (connected + enabled, no bus growth), which the idle
  auto-reset would PORT_RESET ~15s after plug/park. While any HID is
  claimed OR parked, board code suppresses auto_reset_idle (restoring
  the prior value afterwards, so a manual user setting is never forced
  back on). The disabled-port episode path is unaffected.
- LVGL: USBMouse subclasses PointerDriver with identity _calc_coords
  (absolute positions, no TouchCalData side effects) and
  __usb_absolute__ so the panel->USB touch wrap skips it. Cursor is an
  lv.image set via indev.set_cursor (LVGL reparents it to the sys
  layer); reparented + re-set on display swaps via the generic
  _on_display_changed hook in _repoint_indevs. Wheel scrolls the
  object under the cursor best-effort. Cursor tint follows the theme
  (black on light, white on dark) via image-recolor, re-synced on
  every indev read.
- lsusb() prints the descriptive string-descriptor line whenever the
  HAL pass covers the address and appends a generic `HID mouse` /
  `HID keyboard` line only for held addresses the HAL pass skipped
  (dedup by address; never double-prints).

--- Mouse+keyboard collapse experiment (revert-test) ---
- Observation driving it: keyboard transient alone is perfect, mouse +
  display is perfect, keyboard + display is perfect - only mouse
  (persistent pipe, standing resubmits) + keyboard (transient aborts
  every tick) collapses the hub within seconds, mouse URB erroring
  first every time. Power ruled out (lightest combo fails, heaviest
  holds); channels ruled out (0 fails, ~6 pipes, no display).
- Hypothesis under test: the standing-periodic + transient-abort
  coexistence disturbs shared TT/scheduler state (both HIDs are
  low-speed: every transfer is a split transaction). Neither party is
  guilty alone, which is why every single-device cell is green.
- Experiment shape: keyboards persistent by default (this switch);
  flip live with hid_set_kbd_transient(True) to re-enable transient
  without reflashing. If hub+mouse+kbd-persistent holds, the abort
  interaction is convicted; if it still collapses, look at hub TT
  hardware (different hub) - more polling won't fix a two-periodic
  silicon issue. Phase B (mouse transient too) stays parked until
  this resolves: it doubles the suspect operation class.
- End-state note: persistent keyboards cannot serve the required
  display+mouse+keyboard combo in a 7-usable world (8 pipes), so a
  stable revert-test result argues for pressure-adaptive transport
  (persistent when channels allow, transient+parking under display
  pressure), not for deleting the transient path.

--- Safe teardown (the StoreProhibited lesson) ---
- hid_teardown() used to free transfer structs and close the device
  with no regard for in-flight URBs. That is safe for dead devices
  (the stack cancels everything promptly) but use-after-free for a
  LIVE streaming slot: completions landing after free() corrupt the
  heap, and the crash surfaces seconds later in unrelated code
  (decoded once: StoreProhibited in TLSF malloc from a touch read,
  ~5s after toggling a healthy 10ms keyboard into teardown).
- Rule since: no transfer memory is freed while a completion for it
  can still arrive. Live teardowns go through retire +
  HID_SLOT_CLOSING, owned solely by the app thread: stop new submits
  first (state flip), wait boundedly for in-flight count + tick pass
  to drain (completions keep pumping on the client task - waiting
  there would deadlock), then halt/flush/clear, free, release, close.
  Wedged transfers that never complete are leaked deliberately, never
  freed (a late completion into leaked memory is harmless; into freed
  memory is a crash). Per-slot in-flight accounting (increment on
  submit, decrement in callback) is what makes the wait decidable.
- Ownership split, lock-free by design: client task only tears down
  dead (gone/errored, non-retiring) slots and skips retiring ones;
  the tick only touches POLLED non-retired slots; setup only touches
  STAGED; health-check skips retiring. The retire path is the only
  one that blocks, and only on the app thread.

--- HCD channels (the hard silicon limit, ESP32-S3) ---
- The S3 DWC_OTG core has 8 host channels (~7 usable; one is reserved
  per the HCD's own test). One channel is consumed per USB *pipe* and
  held for the pipe's lifetime - transfers (URBs) multiplex on their
  pipe's channel, so URB counts do not matter. Official doc:
  esp-usb "USB Host" -> "Downstream Port Configuration" ->
  "Host Channels" ("Supported amount of channels for ESP32-S3 is 8 ...
  When there are no more free Host channels available, the device could
  not be enumerated and its interface cannot be claimed").
  (The "more than 4" page sometimes cited is the *Device* stack -
  ESP32-as-peripheral endpoints. Different mode, unrelated limit.)
- Pipe budget per setup: 1 default pipe (EP0) per enumerated device
  (stack-held) + 1 interrupt pipe per external hub (hub driver) + 1 per
  claimed endpoint (display bulk, HID interrupts). So hub + display +
  keyboard + mouse = 4 + 1 + 1 + 2 = 8 pipes > ~7 channels: the full
  combo can NEVER fit on S3, with zero leaks required. Whoever claims
  last loses (E (xxx) HCD DWC: No more HCD channels available ->
  EP Alloc error -> Claiming interface error).
- S3 policy (src/usb_hid.c): claim in priority order, display >
  mouse > keyboard (the display claims through its own client and
  always wins; among staged HIDs, mice set up before keyboards). A
  claim failing with ESP_ERR_NOT_SUPPORTED (the channel-exhaustion
  signature) parks immediately with one explanatory line; transient
  failures back off 4s/12s/28s, then park. Parked devices stay silent
  until a bus topology change (plug/unplug/reenum, checked every
  hid_poll) or usb_disp.hid_retry(). Unplug clears the device's
  failure history. usb_disp.hid_parked() lists [(vid, pid, kind,
  fails)] with fails=255 for parked.
- Phase A changes the math: keyboards hold no persistent pipe (see
  polling note above), so steady state is 4 defaults + hub + bulk +
  mouse = 7 pipes, +1 transiently during each keyboard tick. The full
  combo now fits whenever a free channel exists at tick time; a tick
  that finds none just skips (counted, silent) and parks after 50
  consecutive misses. If transient polling proves out, Phase B moves
  mice to the same scheme (steady state 6).
- Persistent interrupt errors log the URB status code:
  `[HID] addr=N intr status=S actual=A` with S: 0=completed, 1=error
  (no response/CRC - TT/split faults land here), 2=timed-out,
  3=canceled, 4=stall, 5=overflow, 6=skipped, 7=no-device (surprise
  removal). Status=7 arriving on a standing pipe seconds-to-a-minute
  before a hub renumber is an early warning of the coming drop, not
  noise. A mouse whose standing transfer errors first every collapse
  while a second periodic pipe is being aborted next to it points at
  scheduler/TT interaction, not at either device.
- Debugging channel pressure: hid_parked() non-empty with fails=255
  plus the "No more HCD channels" lines = exhausted, not wedged. Do NOT reset_port()
  parked devices (they are healthy and enumerated; a reset just burns
  a bus address and re-parks). Unplug something, or hid_retry() after
  freeing a device.

--- Debugging notes ---
- bus_devices() (stack address list) separates "nothing sensed"
  (cable/power/stack) from "hubs only" (adapter missing/wedged) from
  "adapter present, failing" in one call. print(usb_disp.lsusb()) shows
  the same bus Linux-style with VID:PID and product strings.
- Zombie devices (address persists with dead EP0 long after unplug,
  `Unknown device` in lsusb): suspect a dropped DEV_GONE in a burst —
  our client queue is 32 deep for that reason. Discriminator: unplug,
  hands off 60 s; vanishes = was live, persists = leaked (hub replug
  clears it). hub_ports() goes one deeper:
  a (connected=True, enabled=False) port is one the stack gave up on —
  reset_port() it, or wait ~5s for the watchdog's [HUB] lines.
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
