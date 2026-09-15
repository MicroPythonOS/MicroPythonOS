// Minimal USB HID host transport (boot-protocol mice + keyboards).
// ESP32-only, rides the --usbdisplay build: shares the already-installed
// IDF usb_host stack (daemon task, hub support, settle patch, watchdog)
// but registers its OWN client + task. One small upstream hook exists:
// lsusb reuses our held handle for streaming devices (see usb_hid_held_handle).
//
// Design notes:
// - Two-stage setup avoids a deadlock: the client task (which owns event
//   delivery) only opens devices and stages candidates; the blocking
//   SET_PROTOCOL/SET_IDLE control transfers run from hid_poll(), i.e. the
//   app thread behind Python's 1s poll timer (same pattern as the
//   display HAL's pending_probe).
// - Interrupt completions arrive in the client task; the callback only
//   memcpys into a lock-free SPSC ring and resubmits. Python drains it.
// - Only boot-subclass (1) mouse (proto 2) / keyboard (proto 1)
//   interfaces are claimed. Anything else is closed untouched, so the
//   display claim path and lsusb-style inspection never conflict: one
//   device may be opened by both clients at once (different interfaces).
// - S3 HCD channel budget (verified: 8 in silicon, ~7 usable, 1 pipe =
//   1 channel, held for the pipe's lifetime): hub + display + keyboard +
//   mouse need 4 (default pipes) + 1 (hub status) + 1 (display bulk) + 2
//   (HID interrupt) = 8 pipes, so the full combo can NOT fit. Policy:
//   claim in priority order (display is external, mice before keyboards),
//   and park losers silently with backoff instead of retry-spamming:
//   ESP_ERR_NOT_SUPPORTED from interface_claim parks immediately (that
//   is the channel-exhaustion signature), transient failures cool down
//   4s/12s/28s then park. Parking clears on bus topology change or
//   hid_retry(). See README "HCD channels" section.

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "usb/usb_host.h"

#include "usb_hid.h"

// usb_disp_log() lives in usb_mpy.c (routes to UART REPL).
void usb_disp_log(const char *fmt, ...);

#define USB_HID_MAX_DEV 4
#define USB_HID_XFER_PER_DEV 2
#define USB_HID_XFER_SIZE 64
#define USB_HID_CTRL_TIMEOUT_MS 1500
#define USB_HID_RING_MASK 63 // ring size 64, power of two

typedef enum {
    HID_SLOT_EMPTY = 0,
    HID_SLOT_STAGED, // opened by client task, setup pending in hid_poll
    HID_SLOT_STREAMING, // persistent interrupt pipe (mice)
    HID_SLOT_POLLED, // Phase A: keyboard, interrupt pipe allocated per tick
    HID_SLOT_CLOSING, // quiescing for a safe teardown (app thread owns it)
} hid_slot_state_t;

typedef struct {
    hid_slot_state_t state;
    usb_device_handle_t dev;
    uint8_t addr;
    uint8_t iface;
    uint8_t subclass;
    uint8_t protocol;
    uint8_t ep_in;
    uint16_t mps;
    uint8_t speed; // usb_speed_t: 0=low, 1=full, 2=high (decides TT involvement)
    uint8_t interval_ms; // poll cadence, from bInterval, clamped
    uint32_t poll_next_ms; // next transient tick due
    uint32_t polls; // cumulative transient polls performed
    uint16_t ch_total; // cumulative transient channel failures
    uint8_t ch_consec; // consecutive transient channel failures
    volatile bool retire; // live teardown requested: quiesce, then free.
        // Set from any thread; only the app thread acts on it (see
        // hid_retire_teardown). While set, no new submits may start.
    volatile int inflight; // transfers submitted but not yet completed.
        // Incremented on submit, decremented in the completion callback;
        // the retire path waits for zero so no completion ever fires
        // into freed memory (StoreProhibited crash, proven on hardware).
    uint16_t vid;
    uint16_t pid;
    volatile bool gone;
    volatile bool xfer_err;
    usb_transfer_t *xfer[USB_HID_XFER_PER_DEV];
} hid_slot_t;

// Transient keyboard polling (Phase A experiment): after this many
// consecutive per-tick channel failures, park instead of spinning.
// ~2.5s at the 50ms tick: long enough to ride out someone else's
// enumeration burst, short enough to go quiet fast on real exhaustion.
#define HID_KBD_PARK_AFTER 50
// Completion wait for one transient poll (submit is async even here).
// Deliberately short: responsiveness comes from the 10ms tick rate, not
// the pend length - a keypress just after a timeout is caught by the
// next tick. A short bound also limits wasted channel-hold time per
// tick, which is the whole point of transient polling. Expiry with no
// data is NEUTRAL (idle keyboard), never a failure.
#define HID_KBD_TICK_TIMEOUT_MS 30
// Bounded wait to reap a halted transient transfer (CANCELED completion)
// before its memory may be freed and the interface released. Freeing
// early strands the endpoint object in the stack ("EP already allocated"
// on the next claim) and risks use-after-free when the late completion
// fires. Uses the same done semaphore; the client task keeps pumping.
#define HID_KBD_REAP_TIMEOUT_MS 50

static hid_slot_t s_slots[USB_HID_MAX_DEV];
static usb_hid_event_t s_ring[USB_HID_RING_MASK + 1];
static volatile uint8_t s_ring_head = 0; // producer (client task) only
static volatile uint8_t s_ring_tail = 0; // consumer (hid_drain) only
static volatile uint32_t s_dropped = 0;

static usb_host_client_handle_t s_hid_client = NULL;
static bool s_hid_verbose = false;

#define HID_VLOG(...) do { if (s_hid_verbose) usb_disp_log(__VA_ARGS__); } while (0)

// Experiment switch (revert-test for the mouse+keyboard collapse):
// false = keyboards claim a PERSISTENT interrupt pipe like mice
// (pre-Phase-A behavior, zero abort churn); true = transient polling.
// Default persistent: the collapse under test never happens without
// transient aborts next to a standing pipe, and channels fit
// persistently everywhere except display-attached pressure (where the
// park policy still applies). Flippable live via hid_set_kbd_transient
// (applies to newly staged devices; live keyboards re-stage).
static bool s_kbd_transient = false;

static bool s_hid_started = false;
static volatile bool s_scan_needed = false;
// Stop flags for host-mode exit (usb_hid_stop, app thread): the client
// task's loop and the kbd poll loop check these and self-delete. Cleared
// in usb_hid_start (NOT at the end of stop): a task waking late must still
// see the flag set and exit, never revive. Done flags let stop join
// instead of hoping a fixed delay suffices.
static volatile bool s_client_stop = false;
static volatile bool s_kbd_stop = false;
static volatile bool s_client_task_done = false;
static volatile bool s_kbd_task_done = false;
static SemaphoreHandle_t s_hid_ctrl_mutex = NULL;
static SemaphoreHandle_t s_hid_ctrl_done = NULL;
static SemaphoreHandle_t s_kbd_done = NULL;
static TaskHandle_t s_kbd_poll_task = NULL;
static volatile bool s_kbd_tick_active = false;
static volatile uint32_t s_change_gen = 0;

// Retry deferral: per-device setup-failure accounting so a device that
// can never be claimed (no HCD channels left) parks silently instead of
// failing loudly at ~1 Hz forever. Keyed by VID:PID:protocol so it
// survives slot teardown; cleared on disconnect and on bus topology
// change. Shared client-task/app-thread without a lock (same as the
// other volatile flags here): fields are single-byte/short, ops are
// idempotent, worst case is one early or late retry.
#define HID_DEFER_MAX 4
#define HID_DEFER_PARKED_FAILS 255
typedef struct {
    bool used;
    uint16_t vid;
    uint16_t pid;
    uint8_t protocol;
    volatile uint8_t fails;
    volatile uint32_t next_due_ms;
    volatile bool parked;
} hid_defer_t;

static hid_defer_t s_defer[HID_DEFER_MAX];

// Last-seen bus topology (sorted addr snapshot). Any change re-arms
// parked retries: a replug may have freed channels or reordered claims.
static uint8_t s_topo_addrs[16];
static int s_topo_n = -1;

static uint32_t hid_now_ms(void) {
    return (uint32_t)(esp_timer_get_time() / 1000);
}

static hid_defer_t *hid_defer_lookup(uint16_t vid, uint16_t pid, uint8_t protocol,
                                     bool create) {
    for (uint8_t i = 0; i < HID_DEFER_MAX; i++) {
        if (s_defer[i].used && s_defer[i].vid == vid && s_defer[i].pid == pid &&
            s_defer[i].protocol == protocol) {
            return &s_defer[i];
        }
    }
    if (!create) {
        return NULL;
    }
    for (uint8_t i = 0; i < HID_DEFER_MAX; i++) {
        if (!s_defer[i].used) {
            memset(&s_defer[i], 0, sizeof(s_defer[i]));
            s_defer[i].used = true;
            s_defer[i].vid = vid;
            s_defer[i].pid = pid;
            s_defer[i].protocol = protocol;
            return &s_defer[i];
        }
    }
    return NULL;
}

static void hid_defer_clear_entry(hid_defer_t *d) {
    if (d != NULL) {
        memset(d, 0, sizeof(*d));
    }
}

static bool hid_defer_table_empty(void) {
    for (uint8_t i = 0; i < HID_DEFER_MAX; i++) {
        if (s_defer[i].used) {
            return false;
        }
    }
    return true;
}

static void hid_defer_clear_all(bool log_it) {
    bool had = !hid_defer_table_empty();
    memset(s_defer, 0, sizeof(s_defer));
    if (log_it && had) {
        usb_disp_log("[HID] bus topology changed, parked retries re-armed");
    }
}

// Record one setup failure. no_channels (ESP_ERR_NOT_SUPPORTED from
// interface_claim) parks immediately with the budget math; transient
// failures back off 4s/12s/28s, then park until replug/hid_retry().
static void hid_defer_fail(hid_defer_t *d, uint16_t vid, uint16_t pid, uint8_t protocol,
                           uint8_t addr, bool no_channels, uint32_t now_ms) {
    static const uint16_t backoff_ms[3] = {4000, 12000, 28000};
    if (d == NULL) {
        return;
    }
    if (no_channels) {
        d->fails = HID_DEFER_PARKED_FAILS;
        d->parked = true;
        usb_disp_log("[HID] %s %04X:%04X parked: no HCD channels free "
                     "(S3 fits ~7 pipes; hub+display+kbd+mouse need 8). "
                     "Unplug something or hid_retry().",
                     protocol == 2 ? "mouse" : "keyboard", vid, pid);
        (void)addr;
        return;
    }
    if (d->fails < 250) {
        d->fails++;
    }
    if (d->fails > 3) {
        d->parked = true;
        usb_disp_log("[HID] %s addr=%u giving up after %u setup failures "
                     "(until replug/hid_retry)",
                     protocol == 2 ? "mouse" : "keyboard", addr, d->fails);
    } else {
        d->next_due_ms = now_ms + backoff_ms[d->fails - 1];
        usb_disp_log("[HID] %s addr=%u setup failed (%u/3), retry in %us",
                     protocol == 2 ? "mouse" : "keyboard", addr, d->fails,
                     backoff_ms[d->fails - 1] / 1000);
    }
}

static const char *hid_kind_str(uint8_t protocol) {
    return protocol == 2 ? "mouse" : "keyboard";
}

static void hid_ring_push(uint8_t addr, uint8_t subclass, uint8_t protocol,
                          const uint8_t *data, uint8_t len) {
    uint8_t head = s_ring_head;
    uint8_t next = (uint8_t)((head + 1) & USB_HID_RING_MASK);
    if (next == s_ring_tail) {
        s_dropped++;
        return;
    }
    usb_hid_event_t *e = &s_ring[head];
    e->addr = addr;
    e->subclass = subclass;
    e->protocol = protocol;
    e->len = len > 8 ? 8 : len;
    memcpy(e->data, data, e->len);
    s_ring_head = next;
}

static void hid_intr_cb(usb_transfer_t *xfer) {
    hid_slot_t *slot = (hid_slot_t *)xfer->context;
    if (slot->inflight > 0) {
        slot->inflight--;
    }
    if (slot->retire || slot->state == HID_SLOT_CLOSING) {
        // Slot is being quiesced: drop the completion silently. The
        // retire path waits for inflight to reach zero before freeing.
        return;
    }
    if (xfer->status == USB_TRANSFER_STATUS_COMPLETED) {
        uint8_t n = xfer->actual_num_bytes > 255 ? 255 : (uint8_t)xfer->actual_num_bytes;
        if (n > 0) {
            hid_ring_push(slot->addr, slot->subclass, slot->protocol,
                          xfer->data_buffer, n);
        }
        if (slot->state == HID_SLOT_STREAMING && !slot->gone && !slot->retire) {
            xfer->num_bytes = slot->mps;
            if (usb_host_transfer_submit(xfer) != ESP_OK) {
                slot->xfer_err = true;
            } else {
                slot->inflight++;
            }
        }
    } else if (xfer->status != USB_TRANSFER_STATUS_CANCELED) {
        // Visible by design (not verbose): persistent-transfer errors are
        // rare, and the status code discriminates TT/split faults (ERROR)
        // from surprise removal (NO_DEVICE) from stalls/overflows.
        // Full list: 0=completed 1=error 2=timed-out 3=canceled
        // 4=stall 5=overflow 6=skipped 7=no-device.
        usb_disp_log("[HID] addr=%u intr status=%d actual=%d", slot->addr,
                     (int)xfer->status, xfer->actual_num_bytes);
        slot->xfer_err = true;
    }
}

// Quiesced teardown for LIVE slots (retire flag), app thread only.
// Blocked waits are safe here: completions keep pumping on the client
// task. Never call from the client task itself (it owns the pump the
// reap below depends on). Bound for one retire quiesce; expiry logs
// loudly and proceeds (tearing down blind still beats leaking, and
// matches the pre-existing fast path's risk profile, minus the race).
#define HID_RETIRE_WAIT_MS 3000
static void hid_retire_teardown(hid_slot_t *slot) {
    uint8_t addr = slot->addr;
    slot->state = HID_SLOT_CLOSING; // stop all new submits first of all
    // Halt BEFORE the drain-wait: standing URBs never complete on their
    // own, so waiting first always burns the full bound on healthy idle
    // slots. Halting forces in-flight transfers to complete as CANCELED,
    // and the bounded wait below reaps those completions promptly. (This
    // used to run after the wait: same outcome, always 3s slower.)
    usb_host_endpoint_halt(slot->dev, slot->ep_in);
    usb_host_endpoint_flush(slot->dev, slot->ep_in);
    uint32_t waited = 0;
    while ((s_kbd_tick_active || slot->inflight > 0) &&
           waited < HID_RETIRE_WAIT_MS) {
        vTaskDelay(pdMS_TO_TICKS(10));
        waited += 10;
    }
    if (s_kbd_tick_active || slot->inflight > 0) {
        usb_disp_log("[HID] addr=%u retire forced with work in flight", addr);
    }
    // Drain completions once more before anything below is freed.
    vTaskDelay(pdMS_TO_TICKS(50));
    usb_host_endpoint_clear(slot->dev, slot->ep_in);
    for (uint8_t i = 0; i < USB_HID_XFER_PER_DEV; i++) {
        if (slot->xfer[i] != NULL) {
            usb_host_transfer_free(slot->xfer[i]);
            slot->xfer[i] = NULL;
        }
    }
    if (slot->dev != NULL) {
        usb_host_interface_release(s_hid_client, slot->dev, slot->iface);
        usb_host_device_close(s_hid_client, slot->dev);
        slot->dev = NULL;
    }
    usb_disp_log("[HID] addr=%u retired", addr);
    memset(slot, 0, sizeof(*slot));
    s_change_gen++;
    s_scan_needed = true;
}

static void hid_client_event_cb(const usb_host_client_event_msg_t *msg, void *arg) {
    (void)arg;
    if (msg->event == USB_HOST_CLIENT_EVENT_NEW_DEV) {
        s_scan_needed = true;
    } else if (msg->event == USB_HOST_CLIENT_EVENT_DEV_GONE) {
        for (uint8_t i = 0; i < USB_HID_MAX_DEV; i++) {
            if (s_slots[i].state != HID_SLOT_EMPTY && s_slots[i].dev != NULL &&
                s_slots[i].dev == msg->dev_gone.dev_hdl) {
                s_slots[i].gone = true;
            }
        }
    }
}

// Blocking control transfer on a held device handle. App-thread only
// (completion events are pumped by our client task).
static void hid_ctrl_done_cb(usb_transfer_t *xfer);

static bool hid_ctrl(hid_slot_t *slot, uint8_t bmRequestType, uint8_t bRequest,
                     uint16_t wValue, uint16_t wIndex) {
    if (s_hid_client == NULL || s_hid_ctrl_mutex == NULL || s_hid_ctrl_done == NULL ||
        slot->dev == NULL) {
        return false;
    }
    if (xSemaphoreTake(s_hid_ctrl_mutex, pdMS_TO_TICKS(3000)) != pdTRUE) {
        return false;
    }
    bool ok = false;
    usb_transfer_t *x = NULL;
    if (usb_host_transfer_alloc(8 + 64, 0, &x) != ESP_OK) {
        goto out;
    }
    uint8_t *b = x->data_buffer;
    b[0] = bmRequestType;
    b[1] = bRequest;
    b[2] = (uint8_t)wValue;
    b[3] = (uint8_t)(wValue >> 8);
    b[4] = (uint8_t)wIndex;
    b[5] = (uint8_t)(wIndex >> 8);
    b[6] = 0;
    b[7] = 0;
    x->num_bytes = 8;
    x->device_handle = slot->dev;
    x->bEndpointAddress = 0;
    x->callback = hid_ctrl_done_cb;
    x->context = NULL;
    xSemaphoreTake(s_hid_ctrl_done, 0);
    if (usb_host_transfer_submit_control(s_hid_client, x) != ESP_OK) {
        goto out;
    }
    if (xSemaphoreTake(s_hid_ctrl_done, pdMS_TO_TICKS(USB_HID_CTRL_TIMEOUT_MS)) != pdTRUE) {
        goto out;
    }
    ok = (x->status == USB_TRANSFER_STATUS_COMPLETED);
out:
    if (x) {
        usb_host_transfer_free(x);
    }
    xSemaphoreGive(s_hid_ctrl_mutex);
    return ok;
}

static void hid_ctrl_done_cb(usb_transfer_t *xfer) {
    if (s_hid_ctrl_done != NULL) {
        xSemaphoreGive(s_hid_ctrl_done);
    }
    (void)xfer;
}

static bool hid_slot_addr_known(uint8_t addr) {
    for (uint8_t i = 0; i < USB_HID_MAX_DEV; i++) {
        if (s_slots[i].state != HID_SLOT_EMPTY && s_slots[i].addr == addr) {
            return true;
        }
    }
    return false;
}

// Walk the active config: find a boot-HID interface and its interrupt-IN EP.
// Client-task context, non-blocking (descriptor reads are cached).
static bool hid_find_boot_iface(const uint8_t *blob, uint16_t len, uint8_t *iface,
                                uint8_t *subclass, uint8_t *protocol, uint8_t *ep_in,
                                uint16_t *mps, uint8_t *interval_ms) {
    const uint8_t *p = blob;
    const uint8_t *end = blob + len;
    uint8_t cur_iface = 0, cur_alt = 0, cur_class = 0, cur_sub = 0, cur_proto = 0;
    bool cur_boot_hid = false;
    while (p + 1 < end && p[0] >= 2 && p + p[0] <= end) {
        uint8_t dlen = p[0], dtype = p[1];
        if (dtype == 0x04 && dlen >= 9) {
            cur_iface = p[2];
            cur_alt = p[3];
            cur_class = p[5];
            cur_sub = p[6];
            cur_proto = p[7];
            cur_boot_hid = (cur_class == 0x03 && cur_sub == 0x01 &&
                            (cur_proto == 0x01 || cur_proto == 0x02));
        } else if (dtype == 0x05 && dlen >= 7) {
            uint8_t ep = p[2];
            uint8_t attr = p[3] & 0x03;
            if (cur_boot_hid && cur_alt == 0 && attr == 0x03 && (ep & 0x80)) {
                *iface = cur_iface;
                *subclass = cur_sub;
                *protocol = cur_proto;
                *ep_in = ep;
                *mps = (uint16_t)(p[4] | (p[5] << 8));
                if (*mps == 0 || *mps > USB_HID_XFER_SIZE) {
                    *mps = USB_HID_XFER_SIZE;
                }
                // Poll cadence for transient mode (Phase A): deliberately
                // calm (50ms floor). The per-tick claim/CLEAR_FEATURE/
                // submit/halt/flush/release churn every 10ms was knocking
                // cheap hub TTs off the bus, so keyboards trade latency
                // (fine for typing/REPL) for bus quiet. bInterval is ms
                // for low-speed, 2^(n-1) frames for full-speed; anything
                // below the floor becomes 50ms, above 100ms stays capped.
                uint8_t iv = p[6];
                if (iv < 50) {
                    iv = 50;
                } else if (iv > 100) {
                    iv = 100;
                }
                *interval_ms = iv;
                return true;
            }
        }
        p += dlen;
    }
    return false;
}

// Stage 1 (client task): open unknown devices, keep boot-HID candidates.
static void hid_scan(void) {
    uint8_t addrs[16];
    int n = 0;
    if (usb_host_device_addr_list_fill((int)sizeof(addrs), addrs, &n) != ESP_OK) {
        return;
    }
    for (int i = 0; i < n; i++) {
        uint8_t addr = addrs[i];
        if (hid_slot_addr_known(addr)) {
            continue;
        }
        uint8_t free_idx = USB_HID_MAX_DEV;
        for (uint8_t s = 0; s < USB_HID_MAX_DEV; s++) {
            if (s_slots[s].state == HID_SLOT_EMPTY) {
                free_idx = s;
                break;
            }
        }
        if (free_idx == USB_HID_MAX_DEV) {
            return;
        }
        usb_device_handle_t dev = NULL;
        esp_err_t open_err = usb_host_device_open(s_hid_client, addr, &dev);
        if (open_err != ESP_OK) {
            // ESP_ERR_INVALID_STATE = still enumerating / going away; the
            // next NEW_DEV or poll rescan picks it up. Logged (not silent)
            // because a stuck-open device never becomes a staged HID.
            usb_disp_log("[HID] device_open failed addr=%u err=0x%X", addr,
                         (unsigned)open_err);
            continue;
        }
        const usb_device_desc_t *ddesc = NULL;
        const usb_config_desc_t *cdesc = NULL;
        if (usb_host_get_device_descriptor(dev, &ddesc) != ESP_OK || ddesc == NULL ||
            usb_host_get_active_config_descriptor(dev, &cdesc) != ESP_OK || cdesc == NULL) {
            usb_host_device_close(s_hid_client, dev);
            continue;
        }
        if (ddesc->bDeviceClass == 0x09) {
            usb_host_device_close(s_hid_client, dev); // hub: stack handles
            continue;
        }
        uint8_t iface = 0, subclass = 0, protocol = 0, ep_in = 0, interval_ms = 10;
        uint16_t mps = 0;
        if (!hid_find_boot_iface((const uint8_t *)cdesc, cdesc->wTotalLength, &iface,
                                 &subclass, &protocol, &ep_in, &mps, &interval_ms)) {
            usb_host_device_close(s_hid_client, dev);
            continue;
        }
        hid_slot_t *slot = &s_slots[free_idx];
        memset(slot, 0, sizeof(*slot));
        slot->state = HID_SLOT_STAGED;
        {
            // Speed decides TT involvement (low-speed devices behind the
            // hub need split transactions; full-speed do not). Cached
            // here for hid_state(); descriptor reads above are cached
            // so this stays non-blocking in the client task.
            usb_device_info_t dinfo;
            slot->speed = 0xFF; // unknown
            if (usb_host_device_info(dev, &dinfo) == ESP_OK) {
                slot->speed = (uint8_t)dinfo.speed;
            }
        }
        slot->dev = dev;
        slot->addr = addr;
        slot->iface = iface;
        slot->subclass = subclass;
        slot->protocol = protocol;
        slot->ep_in = ep_in;
        slot->mps = mps;
        slot->interval_ms = interval_ms;
        slot->vid = ddesc->idVendor;
        slot->pid = ddesc->idProduct;
        usb_disp_log("[HID] staged %s addr=%u if=%u ep=%02X mps=%u %04X:%04X",
                     hid_kind_str(protocol), addr, iface, ep_in, mps, slot->vid,
                     slot->pid);
    }
}

static void hid_teardown(hid_slot_t *slot, const char *why, bool dev_gone) {
    usb_disp_log("[HID] addr=%u %s", slot->addr, why);
    uint16_t vid = slot->vid, pid = slot->pid;
    uint8_t protocol = slot->protocol;
    for (uint8_t i = 0; i < USB_HID_XFER_PER_DEV; i++) {
        if (slot->xfer[i] != NULL) {
            usb_host_transfer_free(slot->xfer[i]);
            slot->xfer[i] = NULL;
        }
    }
    if (slot->dev != NULL) {
        // Release before close; ignore errors (device may be gone).
        usb_host_interface_release(s_hid_client, slot->dev, slot->iface);
        usb_host_device_close(s_hid_client, slot->dev);
        slot->dev = NULL;
    }
    memset(slot, 0, sizeof(*slot));
    if (dev_gone && (vid != 0 || pid != 0)) {
        // Physical unplug: forget failure history so a replug starts
        // fresh (topology tracking re-arms the rest anyway).
        hid_defer_clear_entry(hid_defer_lookup(vid, pid, protocol, false));
    }
    s_change_gen++;
    s_scan_needed = true;
}

static void hid_kbd_task_ensure(void);

// Stage 2 (app thread via hid_poll): blocking setup of one staged slot.
// Parked/cooling devices are skipped silently; failures feed the defer
// table instead of retrying hot (see hid_defer_fail).
static void hid_setup_slot(hid_slot_t *slot) {
    uint32_t now_ms = hid_now_ms();
    hid_defer_t *defer =
        hid_defer_lookup(slot->vid, slot->pid, slot->protocol, true);
    if (defer != NULL) {
        if (defer->parked) {
            return;
        }
        if ((int32_t)(now_ms - defer->next_due_ms) < 0 && defer->fails > 0) {
            return;
        }
    }
    if (!hid_ctrl(slot, 0x21, 0x0B, 0x0000, slot->iface)) {
        usb_disp_log("[HID] addr=%u SET_PROTOCOL failed, continuing anyway",
                     slot->addr);
    }
    hid_ctrl(slot, 0x21, 0x0A, 0x0000, slot->iface); // SET_IDLE, best effort
    if (slot->protocol == 1 && s_kbd_transient) {
        // Phase A: keyboards hold NO persistent interrupt pipe. They go
        // POLLED (transient claim/submit/release per tick from the poll
        // task below) so hub + display + mouse + keyboard fit the S3
        // channel budget. Mice keep the persistent path for now.
        // (Toggle resync is per-tick in hid_kbd_poll_once, not here: a
        // once-per-episode resync leaves every later tick mismatched.)
        hid_defer_clear_entry(defer);
        slot->state = HID_SLOT_POLLED;
        slot->poll_next_ms = now_ms + slot->interval_ms;
        slot->polls = 0;
        slot->ch_total = 0;
        slot->ch_consec = 0;
        usb_disp_log("[HID] keyboard addr=%u polled every %ums", slot->addr,
                     slot->interval_ms);
        hid_kbd_task_ensure();
        s_change_gen++;
        return;
    }
    esp_err_t claim_err =
        usb_host_interface_claim(s_hid_client, slot->dev, slot->iface, 0);
    if (claim_err != ESP_OK) {
        usb_disp_log("[HID] addr=%u interface_claim err=0x%X", slot->addr,
                     (unsigned)claim_err);
        hid_defer_fail(defer, slot->vid, slot->pid, slot->protocol, slot->addr,
                       claim_err == ESP_ERR_NOT_SUPPORTED, now_ms);
        hid_teardown(slot, "interface_claim failed", false);
        return;
    }
    bool xfers_ok = true;
    for (uint8_t k = 0; k < USB_HID_XFER_PER_DEV; k++) {
        if (usb_host_transfer_alloc(slot->mps, 0, &slot->xfer[k]) != ESP_OK) {
            xfers_ok = false;
            break;
        }
        slot->xfer[k]->device_handle = slot->dev;
        slot->xfer[k]->bEndpointAddress = slot->ep_in;
        slot->xfer[k]->callback = hid_intr_cb;
        slot->xfer[k]->context = slot;
        slot->xfer[k]->num_bytes = slot->mps;
    }
    if (!xfers_ok) {
        hid_defer_fail(defer, slot->vid, slot->pid, slot->protocol, slot->addr,
                       false, now_ms);
        hid_teardown(slot, "transfer alloc failed", false);
        return;
    }
    slot->state = HID_SLOT_STREAMING;
    for (uint8_t k = 0; k < USB_HID_XFER_PER_DEV; k++) {
        if (usb_host_transfer_submit(slot->xfer[k]) != ESP_OK) {
            slot->xfer_err = true;
        } else {
            slot->inflight++;
        }
    }
    if (slot->xfer_err) {
        hid_defer_fail(defer, slot->vid, slot->pid, slot->protocol, slot->addr,
                       false, now_ms);
        hid_teardown(slot, "initial submit failed", false);
        return;
    }
    hid_defer_clear_entry(defer);
    usb_disp_log("[HID] %s addr=%u streaming", hid_kind_str(slot->protocol),
                 slot->addr);
    s_change_gen++;
}

// Stage 2 driver (app thread via hid_poll): two passes so mice win over
// keyboards when HCD channels are scarce (S3 policy: display > mouse >
// keyboard; the display claims through its own client and always wins).
static void hid_setup_staged(void) {
    for (uint8_t pass = 0; pass < 2; pass++) {
        uint8_t want_protocol = (pass == 0) ? 2 : 1;
        for (uint8_t i = 0; i < USB_HID_MAX_DEV; i++) {
            hid_slot_t *slot = &s_slots[i];
            if (slot->state != HID_SLOT_STAGED || slot->protocol != want_protocol) {
                continue;
            }
            if (slot->dev == NULL || slot->gone) {
                hid_teardown(slot, "staged device gone before setup", true);
                continue;
            }
            hid_setup_slot(slot);
        }
    }
}

// ---- Transient keyboard polling (Phase A experiment) ----
//
// A POLLED keyboard holds its open handle but no interrupt pipe. Each
// tick allocates the pipe (claim), submits one IN transfer, waits,
// copies any report into the ring, and frees everything again. Steady
// state holds hub + display + mouse pipes only, so the full combo fits
// the S3 budget with margin to spare. Boot reports are level-state, so
// tick-rate sampling loses nothing vs native bInterval polling (only a
// press+release inside one tick window is invisible - same as hardware).
// All per-tick failures are silent counters; transitions log lines.

typedef enum {
    KBD_OK = 0,
    KBD_EMPTY,     // wait expired, no data (idle keyboard: neutral)
    KBD_CH_FAIL,   // no channel (claim/alloc failed with NOT_SUPPORTED)
    KBD_OTHER_FAIL, // anything else (submit/status)
    KBD_GONE,      // device went away
} kbd_poll_res_t;

static volatile uint32_t s_kbd_total_polls = 0;
static volatile uint32_t s_kbd_total_ch = 0;

static void hid_kbd_done_cb(usb_transfer_t *xfer) {
    if (s_kbd_done != NULL) {
        xSemaphoreGive(s_kbd_done);
    }
    (void)xfer;
}

typedef enum {
    REAP_CLEAN = 0, // reaped, no data
    REAP_DATA,      // reaped, and a slow answer arrived: kept
    REAP_WEDGED,    // reap itself timed out
} reap_res_t;

static reap_res_t hid_kbd_reap(hid_slot_t *slot, usb_transfer_t *x);

static kbd_poll_res_t hid_kbd_poll_once(hid_slot_t *slot) {
    if (slot->dev == NULL || slot->gone) {
        return KBD_GONE;
    }
    esp_err_t cerr =
        usb_host_interface_claim(s_hid_client, slot->dev, slot->iface, 0);
    if (cerr != ESP_OK) {
        HID_VLOG("[HID][V] addr=%u tick claim err=0x%X", slot->addr,
                 (unsigned)cerr);
        return (cerr == ESP_ERR_NOT_SUPPORTED) ? KBD_CH_FAIL : KBD_OTHER_FAIL;
    }
    // Toggle resync, every tick: a fresh pipe starts at DATA0 while the
    // device kept advancing its sequence across our free/realloc cycles,
    // so without this only the first report after each resync lands and
    // releases are lost (stuck keys). CLEAR_FEATURE(ENDPOINT_HALT)
    // resets the device side to DATA0 to match. Best effort: a failure
    // here must not kill the tick, the submit below will report back
    // if the endpoint is really broken. Kept at the calm 50ms cadence,
    // not the 10ms one that collapsed hubs.
    if (!hid_ctrl(slot, 0x02, 0x01, 0x0000, slot->ep_in)) {
        HID_VLOG("[HID][V] addr=%u tick resync failed, continuing", slot->addr);
    }
    kbd_poll_res_t res = KBD_OTHER_FAIL;
    usb_transfer_t *x = NULL;
    if (usb_host_transfer_alloc(slot->mps, 0, &x) == ESP_OK) {
        x->device_handle = slot->dev;
        x->bEndpointAddress = slot->ep_in;
        x->callback = hid_kbd_done_cb;
        x->context = slot;
        x->num_bytes = slot->mps;
        xSemaphoreTake(s_kbd_done, 0);
        if (usb_host_transfer_submit(x) != ESP_OK) {
            HID_VLOG("[HID][V] addr=%u tick submit failed", slot->addr);
        } else {
            // Paired with the reap/wait below: exactly one completion
            // (data, error, or CANCELED-from-reap) settles this transfer.
            // The counter lets retire-teardown wait out in-flight work
            // instead of freeing under it (StoreProhibited, proven).
            slot->inflight++;
            // drop: deliberately leak instead of freeing. Set only when
            // the transfer may still complete later (reap timed out): the
            // stack would then write into freed heap. A wedged pipe is
            // rare; its late completion only signals the done semaphore.
            bool drop = false;
            if (xSemaphoreTake(s_kbd_done, pdMS_TO_TICKS(HID_KBD_TICK_TIMEOUT_MS)) !=
                pdTRUE) {
                // Idle keyboard (NAKs, no data): neutral, not a failure.
                // Reap synchronously, then the next tick catches any
                // keypress that starts right after this.
                HID_VLOG("[HID][V] addr=%u tick wait timeout (idle)", slot->addr);
                reap_res_t rr = hid_kbd_reap(slot, x);
                slot->inflight--;
                if (rr == REAP_WEDGED) {
                    usb_disp_log("[HID] addr=%u wedged transfer dropped (not freed)",
                                 slot->addr);
                    drop = true;
                } else {
                    slot->polls++;
                    s_kbd_total_polls++;
                    res = (rr == REAP_DATA) ? KBD_OK : KBD_EMPTY;
                }
            } else if (x->status != USB_TRANSFER_STATUS_COMPLETED) {
                HID_VLOG("[HID][V] addr=%u tick status=%d actual=%d", slot->addr,
                         (int)x->status, x->actual_num_bytes);
                // A completed-but-errored transfer is genuinely suspicious
                // (unlike an idle timeout): reap for hygiene, but keep the
                // backoff verdict so a persistently erroring endpoint parks
                // loudly instead of spinning silently.
                reap_res_t rr = hid_kbd_reap(slot, x);
                slot->inflight--;
                if (rr == REAP_WEDGED) {
                    usb_disp_log("[HID] addr=%u wedged transfer dropped (not freed)",
                                 slot->addr);
                    drop = true;
                }
            } else {
                if (x->actual_num_bytes > 0) {
                    uint8_t n =
                        x->actual_num_bytes > 255 ? 255 : (uint8_t)x->actual_num_bytes;
                    hid_ring_push(slot->addr, slot->subclass, slot->protocol,
                                  x->data_buffer, n);
                    HID_VLOG("[HID][V] addr=%u tick ok bytes=%d", slot->addr,
                             x->actual_num_bytes);
                }
                slot->polls++;
                s_kbd_total_polls++;
                slot->inflight--;
                res = KBD_OK;
            }
            if (!drop) {
                usb_host_transfer_free(x);
            }
        }
    }
    usb_host_interface_release(s_hid_client, slot->dev, slot->iface);
    return res;
}

// Reap a halted transient transfer so its memory may be freed and the
// interface released: halt + flush, then wait (bounded) for the CANCELED
// (or late-OK) completion, then clear. Follows the display HAL's
// bulk_ep_recover choreography (halt->flush->clear). REAP_WEDGED means
// even the reap timed out: the pipe is wedged beyond a tick-level retry.
static reap_res_t hid_kbd_reap(hid_slot_t *slot, usb_transfer_t *x) {
    usb_host_endpoint_halt(slot->dev, slot->ep_in);
    usb_host_endpoint_flush(slot->dev, slot->ep_in);
    if (xSemaphoreTake(s_kbd_done, pdMS_TO_TICKS(HID_KBD_REAP_TIMEOUT_MS)) !=
        pdTRUE) {
        HID_VLOG("[HID][V] addr=%u reap timeout (pipe wedged)", slot->addr);
        return REAP_WEDGED;
    }
    if (x->status == USB_TRANSFER_STATUS_COMPLETED && x->actual_num_bytes > 0) {
        // Slow device answered between our timeout and the halt: keep
        // the report instead of dropping it on the floor.
        uint8_t n =
            x->actual_num_bytes > 255 ? 255 : (uint8_t)x->actual_num_bytes;
        hid_ring_push(slot->addr, slot->subclass, slot->protocol,
                      x->data_buffer, n);
        HID_VLOG("[HID][V] addr=%u late data kept bytes=%d", slot->addr,
                 x->actual_num_bytes);
        usb_host_endpoint_clear(slot->dev, slot->ep_in);
        return REAP_DATA;
    }
    usb_host_endpoint_clear(slot->dev, slot->ep_in);
    return REAP_CLEAN;
}

// One scheduler pass over POLLED keyboards. Testable directly (the task
// wrapper below is a thin loop around this).
static void hid_kbd_tick(uint32_t now_ms) {
    for (uint8_t i = 0; i < USB_HID_MAX_DEV; i++) {
        hid_slot_t *slot = &s_slots[i];
        if (slot->state != HID_SLOT_POLLED) {
            continue;
        }
        if (slot->retire) {
            // Owned by hid_retire_teardown (app thread) now.
            continue;
        }
        if (slot->dev == NULL || slot->gone) {
            hid_teardown(slot, "disconnected", true);
            continue;
        }
        if ((int32_t)(now_ms - slot->poll_next_ms) < 0) {
            continue;
        }
        slot->poll_next_ms = now_ms + slot->interval_ms;
        kbd_poll_res_t r = hid_kbd_poll_once(slot);
        if (r == KBD_OK || r == KBD_EMPTY) {
            // A completed tick (with or without data) proves the whole
            // device + stack path works end to end.
            slot->ch_consec = 0;
        } else if (r == KBD_CH_FAIL) {
            slot->ch_total++;
            s_kbd_total_ch++;
            slot->ch_consec++;
            if (slot->ch_consec >= HID_KBD_PARK_AFTER) {
                hid_defer_t *d = hid_defer_lookup(slot->vid, slot->pid,
                                                  slot->protocol, true);
                hid_defer_fail(d, slot->vid, slot->pid, slot->protocol,
                               slot->addr, true, now_ms);
                hid_teardown(slot, "parking: no channels for transient poll", false);
            }
        } else if (r == KBD_OTHER_FAIL) {
            hid_defer_t *d = hid_defer_lookup(slot->vid, slot->pid,
                                              slot->protocol, true);
            hid_defer_fail(d, slot->vid, slot->pid, slot->protocol, slot->addr,
                           false, now_ms);
            hid_teardown(slot, "transient poll failed", false);
        } else {
            hid_teardown(slot, "disconnected", true);
        }
    }
}

static bool hid_kbd_any_polled(void) {
    for (uint8_t i = 0; i < USB_HID_MAX_DEV; i++) {
        if (s_slots[i].state == HID_SLOT_POLLED) {
            return true;
        }
    }
    return false;
}

// Start the poll task on first POLLED keyboard (idempotent). Logs the
// started line here so it is unit-testable; the stopped line lives in
// the task itself.
static void hid_kbd_poll_task(void *arg);

static void hid_kbd_task_ensure(void) {
    if (s_kbd_poll_task != NULL) {
        return;
    }
    for (uint8_t i = 0; i < USB_HID_MAX_DEV; i++) {
        hid_slot_t *slot = &s_slots[i];
        if (slot->state == HID_SLOT_POLLED && slot->dev != NULL) {
            usb_disp_log("[HID] keyboard polling started (addr=%u, every %ums)",
                         slot->addr, slot->interval_ms);
            break;
        }
    }
    if (!hid_kbd_any_polled()) {
        return;
    }
    s_kbd_task_done = false;
    if (xTaskCreate(hid_kbd_poll_task, "usbhid_kbdpoll", 4096, NULL, 5,
                    &s_kbd_poll_task) != pdPASS) {
        s_kbd_poll_task = NULL;
    }
}

static void hid_kbd_poll_task(void *arg) {
    (void)arg;
    uint32_t base_polls = s_kbd_total_polls;
    uint32_t base_ch = s_kbd_total_ch;
    while (!s_kbd_stop && hid_kbd_any_polled()) {
        hid_kbd_tick(hid_now_ms());
        vTaskDelay(pdMS_TO_TICKS(5));
    }
    usb_disp_log("[HID] keyboard polling stopped (%lu polls performed, %lu channel-fails)",
                 (unsigned long)(s_kbd_total_polls - base_polls),
                 (unsigned long)(s_kbd_total_ch - base_ch));
    s_kbd_poll_task = NULL;
    s_kbd_task_done = true;
    vTaskDelete(NULL);
}

static volatile uint32_t s_client_last_pump_ms = 0;

// One client-task pass over a single slot. Split out for unit tests;
// the live loop below just iterates it.
static void hid_client_task_slot(hid_slot_t *slot) {
    // Retiring slots belong to the app thread (hid_retire_teardown):
    // touching them here would double-free against it.
    if (slot->retire) {
        return;
    }
    if (slot->state == HID_SLOT_STREAMING && (slot->gone || slot->xfer_err)) {
        // Give errored transfers a moment to complete as CANCELED.
        vTaskDelay(pdMS_TO_TICKS(50));
        bool gone = slot->gone;
        hid_teardown(slot, gone ? "disconnected" : "transfer error", gone);
    }
}

static void hid_client_task(void *arg) {
    (void)arg;
    while (!s_client_stop) {
        // Heartbeat for event-delivery-stall detection (see
        // usb_hid_loop_lag_ms): if this stops advancing while the device
        // is alive, completions/teardowns/rescans all freeze with it.
        s_client_last_pump_ms = hid_now_ms();
        usb_host_client_handle_events(s_hid_client, pdMS_TO_TICKS(100));
        // Streaming slots only: staged slots are owned by hid_poll()
        // (app thread), so a replug racing setup is torn down there.
        // Splitting ownership avoids double-close of the device handle.
        for (uint8_t i = 0; i < USB_HID_MAX_DEV; i++) {
            hid_client_task_slot(&s_slots[i]);
        }
        if (s_scan_needed) {
            s_scan_needed = false;
            hid_scan();
        }
    }
    s_client_task_done = true;
    vTaskDelete(NULL);
}

bool usb_hid_start(void) {
    if (s_hid_started) {
        return true;
    }
    memset(s_slots, 0, sizeof(s_slots));
    const usb_host_client_config_t client_cfg = {
        .is_synchronous = false,
        .max_num_event_msg = 8,
        .async =
            {
                .client_event_callback = hid_client_event_cb,
                .callback_arg = NULL,
            },
    };
    if (usb_host_client_register(&client_cfg, &s_hid_client) != ESP_OK) {
        return false; // host stack not up yet (display start runs first)
    }
    s_hid_ctrl_mutex = xSemaphoreCreateMutex();
    s_hid_ctrl_done = xSemaphoreCreateBinary();
    s_kbd_done = xSemaphoreCreateBinary();
    if (s_hid_ctrl_mutex == NULL || s_hid_ctrl_done == NULL || s_kbd_done == NULL) {
        usb_host_client_deregister(s_hid_client);
        s_hid_client = NULL;
        return false;
    }
    s_hid_started = true;
    s_scan_needed = true;
    s_client_stop = false;
    s_kbd_stop = false;
    s_client_task_done = false;
    s_kbd_task_done = false;
    s_client_last_pump_ms = hid_now_ms();
    xTaskCreate(hid_client_task, "usbhid_client", 4096, NULL, 5, NULL);
    usb_disp_log("[HID] client started (S3 channel policy: display > mouse > keyboard)");
    return true;
}

// Tear down the HID client for host-mode exit (deactivate path).
// App thread only. Stops the client + kbd tasks, frees every slot
// WITHOUT retire-waiting (no completions can arrive once the tasks stop
// and the host uninstalls; waiting would burn 3s per live slot), deletes
// the semaphores, deregisters the client, resets all state.
// usb_hid_start() works again afterwards. Every public accessor stays
// safe to call while stopped (empty state, s_hid_started gate).
void usb_hid_stop(void) {
    if (!s_hid_started) {
        return;
    }
    s_hid_started = false;
    // 1. Stop the kbd poll task first: an in-flight tick could submit new
    // transfers at any moment (bounded by tick timeouts, ~100ms worst).
    s_kbd_stop = true;
    vTaskDelay(pdMS_TO_TICKS(150));
    // 2. Quiesce every endpoint while the client task still pumps: halted
    // transfers complete as CANCELED, and CANCELED never resubmits, so no
    // URB outlives this function. Skipping this leaves submitted URBs in
    // the stack and client deregister fails (proven on hardware).
    for (uint8_t i = 0; i < USB_HID_MAX_DEV; i++) {
        hid_slot_t *slot = &s_slots[i];
        if (slot->dev != NULL) {
            usb_host_endpoint_halt(slot->dev, slot->ep_in);
            usb_host_endpoint_flush(slot->dev, slot->ep_in);
        }
    }
    vTaskDelay(pdMS_TO_TICKS(100));
    // 3. Stop the client task and join (bounded, see flags above).
    s_client_stop = true;
    if (s_hid_client != NULL) {
        usb_host_client_unblock(s_hid_client);
    }
    // Join on the done flags (bounded). The kbd task only exists while a
    // transient keyboard is polled; a stale done=true from a normally
    // exited task is fine (nothing to wait for), and task_ensure clears
    // it whenever a new poll task starts.
    bool need_kbd = (s_kbd_poll_task != NULL);
    uint32_t waited = 0;
    while ((!s_client_task_done || (need_kbd && !s_kbd_task_done)) && waited < 1000) {
        vTaskDelay(pdMS_TO_TICKS(10));
        waited += 10;
    }
    if (!s_client_task_done || (need_kbd && !s_kbd_task_done)) {
        usb_disp_log("[HID] stop: task join timed out, proceeding anyway");
    }
    for (uint8_t i = 0; i < USB_HID_MAX_DEV; i++) {
        hid_slot_t *slot = &s_slots[i];
        for (uint8_t k = 0; k < USB_HID_XFER_PER_DEV; k++) {
            if (slot->xfer[k] != NULL) {
                usb_host_transfer_free(slot->xfer[k]);
                slot->xfer[k] = NULL;
            }
        }
        if (slot->dev != NULL) {
            usb_host_interface_release(s_hid_client, slot->dev, slot->iface);
            usb_host_device_close(s_hid_client, slot->dev);
            slot->dev = NULL;
        }
    }
    memset(s_slots, 0, sizeof(s_slots));
    memset(s_defer, 0, sizeof(s_defer));
    s_ring_head = 0;
    s_ring_tail = 0;
    s_dropped = 0;
    s_topo_n = -1;
    s_scan_needed = false;
    s_kbd_total_polls = 0;
    s_kbd_total_ch = 0;
    if (s_hid_ctrl_mutex != NULL) {
        vSemaphoreDelete(s_hid_ctrl_mutex);
        s_hid_ctrl_mutex = NULL;
    }
    if (s_hid_ctrl_done != NULL) {
        vSemaphoreDelete(s_hid_ctrl_done);
        s_hid_ctrl_done = NULL;
    }
    if (s_kbd_done != NULL) {
        vSemaphoreDelete(s_kbd_done);
        s_kbd_done = NULL;
    }
    s_kbd_poll_task = NULL;
    if (s_hid_client != NULL) {
        if (usb_host_client_deregister(s_hid_client) != ESP_OK) {
            usb_disp_log("[HID] stop: client deregister failed");
        }
        s_hid_client = NULL;
    }
    s_change_gen++;
    usb_disp_log("[HID] client stopped");
    // Note: a kbd tick in flight across the reset above can recreate one
    // defer entry (harmless phantom in hid_parked until the next topology
    // change or hid_retry; 50ms race window, no crash: teardown on a
    // zeroed slot is a no-op plus a generation bump).
}

// Bus topology snapshot: any addr-list change (plug/unplug/reenum at a
// new address, or a missed NEW_DEV/DEV_GONE) re-arms parked retries and
// rescans. Runs on the app thread from hid_poll().
static void hid_topology_check(void) {
    uint8_t addrs[16];
    int n = 0;
    if (usb_host_device_addr_list_fill((int)sizeof(addrs), addrs, &n) != ESP_OK) {
        return;
    }
    bool same = (n == s_topo_n);
    if (same) {
        for (int i = 0; i < n && same; i++) {
            bool found = false;
            for (int k = 0; k < s_topo_n; k++) {
                if (s_topo_addrs[k] == addrs[i]) {
                    found = true;
                    break;
                }
            }
            same = found;
        }
    }
    if (same) {
        return;
    }
    if (n < (int)sizeof(s_topo_addrs)) {
        memcpy(s_topo_addrs, addrs, (size_t)n);
    }
    s_topo_n = n;
    hid_defer_clear_all(true);
    s_scan_needed = true;
}

bool usb_hid_poll(void) {
    if (!s_hid_started) {
        return false;
    }
    uint32_t before = s_change_gen;
    hid_topology_check();
    // Retire-flagged live slots first: quiesced teardown (may block),
    // so their restage follows in a later poll, never mid-teardown.
    for (uint8_t i = 0; i < USB_HID_MAX_DEV; i++) {
        hid_slot_t *slot = &s_slots[i];
        if (slot->retire && slot->state != HID_SLOT_EMPTY &&
            slot->state != HID_SLOT_CLOSING && slot->dev != NULL) {
            hid_retire_teardown(slot);
        }
    }
    hid_setup_staged();
    hid_kbd_task_ensure();
    // Health-check live claims; a dead handle means a missed DEV_GONE.
    // Retiring slots are skipped: the retire path owns them already.
    for (uint8_t i = 0; i < USB_HID_MAX_DEV; i++) {
        hid_slot_t *slot = &s_slots[i];
        if ((slot->state == HID_SLOT_STREAMING || slot->state == HID_SLOT_POLLED) &&
            slot->dev != NULL && !slot->gone && !slot->retire) {
            usb_device_info_t info;
            if (usb_host_device_info(slot->dev, &info) != ESP_OK) {
                slot->gone = true;
            }
        }
    }
    return s_change_gen != before;
}

uint8_t usb_hid_claimed_addrs(uint8_t *out, uint8_t max) {
    uint8_t n = 0;
    if (out == NULL || max == 0) {
        return 0;
    }
    for (uint8_t i = 0; i < USB_HID_MAX_DEV && n < max; i++) {
        if (s_slots[i].state != HID_SLOT_EMPTY && s_slots[i].dev != NULL) {
            out[n++] = s_slots[i].addr;
        }
    }
    return n;
}

uint8_t usb_hid_state(usb_hid_state_t *out, uint8_t max) {
    uint8_t n = 0;
    if (out == NULL || max == 0) {
        return 0;
    }
    for (uint8_t i = 0; i < USB_HID_MAX_DEV && n < max; i++) {
        hid_slot_t *slot = &s_slots[i];
        if ((slot->state != HID_SLOT_STREAMING && slot->state != HID_SLOT_POLLED) ||
            slot->dev == NULL) {
            continue;
        }
        out[n].addr = slot->addr;
        out[n].protocol = slot->protocol;
        out[n].vid = slot->vid;
        out[n].pid = slot->pid;
        out[n].speed = slot->speed;
        n++;
    }
    return n;
}

uint8_t usb_hid_drain(usb_hid_event_t *out, uint8_t max) {
    uint8_t n = 0;
    if (out == NULL || max == 0) {
        return 0;
    }
    while (n < max && s_ring_tail != s_ring_head) {
        usb_hid_event_t *e = &s_ring[s_ring_tail];
        out[n].addr = e->addr;
        out[n].subclass = e->subclass;
        out[n].protocol = e->protocol;
        out[n].len = e->len;
        memcpy(out[n].data, e->data, e->len);
        s_ring_tail = (uint8_t)((s_ring_tail + 1) & USB_HID_RING_MASK);
        n++;
    }
    if (s_dropped != 0) {
        usb_disp_log("[HID] dropped %lu reports (ring full)", (unsigned long)s_dropped);
        s_dropped = 0;
    }
    return n;
}

uint32_t usb_hid_change_gen(void) {
    return s_change_gen;
}

usb_device_handle_t usb_hid_held_handle(uint8_t addr) {
    for (uint8_t i = 0; i < USB_HID_MAX_DEV; i++) {
        hid_slot_t *slot = &s_slots[i];
        if ((slot->state == HID_SLOT_STREAMING || slot->state == HID_SLOT_POLLED) &&
            slot->dev != NULL && slot->addr == addr) {
            return slot->dev;
        }
    }
    return NULL;
}

// Does one of our HID slots hold the device on (hub_addr, port)? Lets the
// hub watchdog skip its quiet auto-reset exactly on HID-owned ports
// instead of suppressing globally. device_info() resolves any open handle
// to (parent hub handle, port), and the parent's own info gives the hub
// address: pure cached stack reads, no EP0 traffic, safe from any thread.
// Any non-empty slot counts (streaming, polled, staged, closing):
// anything with an open handle is ours, including a device mid-setup or
// mid-teardown. Racy by design (a slot can tear down mid-read): the worst
// outcome is one skipped quiet reset, never a wrong reset, since this
// only ever suppresses.
bool usb_hid_owns_idle_port(uint8_t hub_addr, uint8_t port) {
    for (uint8_t i = 0; i < USB_HID_MAX_DEV; i++) {
        hid_slot_t *slot = &s_slots[i];
        usb_device_handle_t dev = slot->dev;
        if (slot->state == HID_SLOT_EMPTY || dev == NULL) {
            continue;
        }
        usb_device_info_t info;
        if (usb_host_device_info(dev, &info) != ESP_OK) {
            continue;
        }
        if (info.parent.port_num != port) {
            continue;
        }
        usb_device_info_t hub_info;
        if (usb_host_device_info(info.parent.dev_hdl, &hub_info) != ESP_OK) {
            continue;
        }
        if (hub_info.dev_addr == hub_addr) {
            return true;
        }
    }
    return false;
}

uint8_t usb_hid_poll_stats(usb_hid_poll_stat_t *out, uint8_t max) {
    uint8_t n = 0;
    if (out == NULL || max == 0) {
        return 0;
    }
    for (uint8_t i = 0; i < USB_HID_MAX_DEV && n < max; i++) {
        hid_slot_t *slot = &s_slots[i];
        if (slot->state != HID_SLOT_POLLED || slot->dev == NULL) {
            continue;
        }
        out[n].addr = slot->addr;
        out[n].protocol = slot->protocol;
        out[n].polls = slot->polls;
        out[n].ch_fails = slot->ch_total;
        n++;
    }
    return n;
}

uint8_t usb_hid_parked(usb_hid_parked_t *out, uint8_t max) {
    uint8_t n = 0;
    if (out == NULL || max == 0) {
        return 0;
    }
    for (uint8_t i = 0; i < HID_DEFER_MAX && n < max; i++) {
        if (!s_defer[i].used || (!s_defer[i].parked && s_defer[i].fails == 0)) {
            continue;
        }
        out[n].vid = s_defer[i].vid;
        out[n].pid = s_defer[i].pid;
        out[n].protocol = s_defer[i].protocol;
        out[n].fails = s_defer[i].fails;
        n++;
    }
    return n;
}

void usb_hid_retry(void) {
    hid_defer_clear_all(false);
    s_scan_needed = true;
    usb_disp_log("[HID] manual retry re-armed");
}

void usb_hid_set_kbd_transient(bool on) {
    if (s_kbd_transient == on) {
        return;
    }
    s_kbd_transient = on;
    // Live keyboards re-stage under the new mode via the retire path
    // below (NOT via gone: tearing down a live streaming slot with
    // in-flight URBs use-after-frees the heap - StoreProhibited,
    // proven on hardware). Streaming and POLLED slots converge alike.
    for (uint8_t i = 0; i < USB_HID_MAX_DEV; i++) {
        hid_slot_t *slot = &s_slots[i];
        if ((slot->state == HID_SLOT_STREAMING || slot->state == HID_SLOT_POLLED) &&
            slot->protocol == 1 && slot->dev != NULL) {
            slot->retire = true;
        }
    }
    usb_disp_log("[HID] keyboard mode: %s (live keyboards re-stage)",
                 on ? "transient" : "persistent");
}

bool usb_hid_kbd_transient(void) {
    return s_kbd_transient;
}

uint32_t usb_hid_loop_lag_ms(void) {
    // Unsigned wrap-safe: how long ago the client task last pumped
    // events. ~100ms steady state; seconds mean event delivery (and
    // with it completions, teardowns, rescans) is stalled.
    return hid_now_ms() - s_client_last_pump_ms;
}

void usb_hid_set_verbose(bool on) {
    s_hid_verbose = on;
}

bool usb_hid_verbose(void) {
    return s_hid_verbose;
}
