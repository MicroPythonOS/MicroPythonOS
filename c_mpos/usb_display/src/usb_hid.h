// Minimal USB HID host transport (boot-protocol mice + keyboards).
// Public interface for the MicroPython binding (usb_disp_mpy.c).
// Transport-only: report parsing lives in Python (drivers/indev/usb_hid.py),
// so swapping this for the official hid_host component later only touches
// this file, not the module API or the Python side.

#ifndef USB_HID_H_
#define USB_HID_H_

#include <stdbool.h>
#include <stdint.h>

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
} usb_hid_state_t;

// Register our own usb_host client + task. False when the host stack is
// not up yet (arm_usb_display() runs first in main.py); idempotent.
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

#ifdef __cplusplus
}
#endif

#endif // USB_HID_H_
