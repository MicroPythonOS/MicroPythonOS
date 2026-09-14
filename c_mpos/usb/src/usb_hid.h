// Minimal USB HID host transport (boot-protocol mice + keyboards).
// Public interface for the MicroPython binding (usb_mpy.c).
// Transport-only: report parsing lives in Python (drivers/indev/usb_hid.py),
// so swapping this for the official hid_host component later only touches
// this file, not the module API or the Python side.

#ifndef USB_HID_H_
#define USB_HID_H_

#include <stdbool.h>
#include <stdint.h>

#include "usb/usb_host.h" // usb_device_handle_t for held-handle sharing

#ifdef __cplusplus
extern "C" {
#endif

// One drained input report. data holds up to 8 raw report bytes
// (boot mouse reports are 3-4 bytes, boot keyboard 8).
typedef struct {
    uint8_t addr;
    uint8_t subclass;
    uint8_t protocol;
    uint8_t len;
    uint8_t data[8];
} usb_hid_event_t;

// One streaming HID device.
typedef struct {
    uint8_t addr;
    uint8_t protocol; // 1 = keyboard, 2 = mouse (boot protocol numbers)
    uint16_t vid;
    uint16_t pid;
    uint8_t speed; // usb_speed_t: 0=low, 1=full, 2=high, 0xFF=unknown
} usb_hid_state_t;

// Register our own usb_host client + task. False when the host stack is
// not up yet (USBManager.arm_display() runs first in main.py); idempotent.
bool usb_hid_start(void);

// App-thread pump: completes staged setups, health-checks claims.
// True when the device set changed (connect/disconnect).
bool usb_hid_poll(void);

// Device addresses currently held open (never empty while held).
// bus_devices()/lsusb re-add these: claimed devices leave the stack's
// idle list, like the held display device.
uint8_t usb_hid_claimed_addrs(uint8_t *out, uint8_t max);

// Streaming devices (for hid_state() and lsusb lines).
uint8_t usb_hid_state(usb_hid_state_t *out, uint8_t max);

// Drain pending input reports (up to max). Single consumer only.
uint8_t usb_hid_drain(usb_hid_event_t *out, uint8_t max);

// Monotonic generation counter, bumped on every claim/teardown.
uint32_t usb_hid_change_gen(void);

// One parked (or cooling-down) device: setup keeps failing, so retries
// are deferred instead of spamming the log at full rate.
typedef struct {
    uint16_t vid;
    uint16_t pid;
    uint8_t protocol; // 1 = keyboard, 2 = mouse
    uint8_t fails;    // consecutive setup failures (255 = parked)
} usb_hid_parked_t;

// Parked/cooldown list for REPL introspection (usb.hid_parked()).
uint8_t usb_hid_parked(usb_hid_parked_t *out, uint8_t max);

// Clear the parked/cooldown list and rescan now (usb.hid_retry()).
// Topology changes (plug/unplug) re-arms automatically; this is the
// manual equivalent.
void usb_hid_retry(void);

// One transiently-polled keyboard: cumulative counters for REPL frequency
// checks (usb.hid_poll_stats()). Per-slot counters reset on
// teardown (unplug/replug); sample twice and diff for polls/sec.
typedef struct {
    uint8_t addr;
    uint8_t protocol; // 1 = keyboard (only keyboards are polled)
    uint32_t polls;   // transient polls performed
    uint16_t ch_fails; // cumulative transient channel failures
} usb_hid_poll_stat_t;

// Live polled keyboards (for usb.hid_poll_stats()).
uint8_t usb_hid_poll_stats(usb_hid_poll_stat_t *out, uint8_t max);

// Keyboard transport mode experiment (usb.hid_set_kbd_transient()):
// false (default) = persistent interrupt pipe like mice; true =
// transient per-tick polling. Live keyboards re-stage on flip.
void usb_hid_set_kbd_transient(bool on);
bool usb_hid_kbd_transient(void);

// ms since the client task last pumped events (usb.hid_loop_lag()).
// ~100ms in steady state; seconds mean event delivery - completions,
// teardowns, rescans - is stalled. Wrap-safe subtraction.
uint32_t usb_hid_loop_lag_ms(void);

// Per-tick debug logging, off by default (usb.hid_verbose()).
// Gated [HID][V] lines: claim/submit/wait outcomes per tick. Opt-in
// only - at ~100 ticks/s it would drown the REPL otherwise.
void usb_hid_set_verbose(bool on);
bool usb_hid_verbose(void);

// Open handle of a STREAMING device, if any (NULL otherwise). Lets
// lsusb-style inspection reuse the held handle instead of reopening a
// live device by address mid-stream (same reason the display HAL keeps
// its own handle for lsusb).
usb_device_handle_t usb_hid_held_handle(uint8_t addr);

#ifdef __cplusplus
}
#endif

#endif // USB_HID_H_
