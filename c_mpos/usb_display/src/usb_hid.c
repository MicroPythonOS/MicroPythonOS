// Minimal USB HID host transport (boot-protocol mice + keyboards).
// ESP32-only, rides the --usbdisplay build: shares the already-installed
// IDF usb_host stack (daemon task, hub support, settle patch, watchdog)
// but registers its OWN client + task, so no upstream/ file is touched.
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

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "usb/usb_host.h"

#include "usb_hid.h"

// usb_disp_log() lives in usb_disp_mpy.c (routes to UART REPL).
void usb_disp_log(const char *fmt, ...);

#define USB_HID_MAX_DEV 4
#define USB_HID_XFER_PER_DEV 2
#define USB_HID_XFER_SIZE 64
#define USB_HID_CTRL_TIMEOUT_MS 1500
#define USB_HID_RING_MASK 63 // ring size 64, power of two

typedef enum {
    HID_SLOT_EMPTY = 0,
    HID_SLOT_STAGED, // opened by client task, setup pending in hid_poll
    HID_SLOT_STREAMING,
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
    uint16_t vid;
    uint16_t pid;
    volatile bool gone;
    volatile bool xfer_err;
    usb_transfer_t *xfer[USB_HID_XFER_PER_DEV];
} hid_slot_t;

static hid_slot_t s_slots[USB_HID_MAX_DEV];
static usb_hid_event_t s_ring[USB_HID_RING_MASK + 1];
static volatile uint8_t s_ring_head = 0; // producer (client task) only
static volatile uint8_t s_ring_tail = 0; // consumer (hid_drain) only
static volatile uint32_t s_dropped = 0;

static usb_host_client_handle_t s_hid_client = NULL;
static bool s_hid_started = false;
static volatile bool s_scan_needed = false;
static SemaphoreHandle_t s_hid_ctrl_mutex = NULL;
static SemaphoreHandle_t s_hid_ctrl_done = NULL;
static volatile uint32_t s_change_gen = 0;

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
    if (xfer->status == USB_TRANSFER_STATUS_COMPLETED) {
        uint8_t n = xfer->actual_num_bytes > 255 ? 255 : (uint8_t)xfer->actual_num_bytes;
        if (n > 0) {
            hid_ring_push(slot->addr, slot->subclass, slot->protocol,
                          xfer->data_buffer, n);
        }
        if (slot->state == HID_SLOT_STREAMING && !slot->gone) {
            xfer->num_bytes = slot->mps;
            if (usb_host_transfer_submit(xfer) != ESP_OK) {
                slot->xfer_err = true;
            }
        }
    } else if (xfer->status != USB_TRANSFER_STATUS_CANCELED) {
        slot->xfer_err = true;
    }
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
                                uint16_t *mps) {
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
        if (usb_host_device_open(s_hid_client, addr, &dev) != ESP_OK) {
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
        uint8_t iface = 0, subclass = 0, protocol = 0, ep_in = 0;
        uint16_t mps = 0;
        if (!hid_find_boot_iface((const uint8_t *)cdesc, cdesc->wTotalLength, &iface,
                                 &subclass, &protocol, &ep_in, &mps)) {
            usb_host_device_close(s_hid_client, dev);
            continue;
        }
        hid_slot_t *slot = &s_slots[free_idx];
        memset(slot, 0, sizeof(*slot));
        slot->state = HID_SLOT_STAGED;
        slot->dev = dev;
        slot->addr = addr;
        slot->iface = iface;
        slot->subclass = subclass;
        slot->protocol = protocol;
        slot->ep_in = ep_in;
        slot->mps = mps;
        slot->vid = ddesc->idVendor;
        slot->pid = ddesc->idProduct;
        usb_disp_log("[HID] staged %s addr=%u if=%u ep=%02X mps=%u %04X:%04X",
                     hid_kind_str(protocol), addr, iface, ep_in, mps, slot->vid,
                     slot->pid);
    }
}

static void hid_teardown(hid_slot_t *slot, const char *why) {
    usb_disp_log("[HID] addr=%u %s", slot->addr, why);
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
    s_change_gen++;
    s_scan_needed = true;
}

// Stage 2 (app thread via hid_poll): blocking setup of staged candidates.
static void hid_setup_staged(void) {
    for (uint8_t i = 0; i < USB_HID_MAX_DEV; i++) {
        hid_slot_t *slot = &s_slots[i];
        if (slot->state != HID_SLOT_STAGED || slot->dev == NULL || slot->gone) {
            if (slot->state == HID_SLOT_STAGED && (slot->dev == NULL || slot->gone)) {
                hid_teardown(slot, "staged device gone before setup");
            }
            continue;
        }
        if (!hid_ctrl(slot, 0x21, 0x0B, 0x0000, slot->iface)) {
            usb_disp_log("[HID] addr=%u SET_PROTOCOL failed, continuing anyway",
                         slot->addr);
        }
        hid_ctrl(slot, 0x21, 0x0A, 0x0000, slot->iface); // SET_IDLE, best effort
        if (usb_host_interface_claim(s_hid_client, slot->dev, slot->iface, 0) != ESP_OK) {
            hid_teardown(slot, "interface_claim failed");
            continue;
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
            hid_teardown(slot, "transfer alloc failed");
            continue;
        }
        slot->state = HID_SLOT_STREAMING;
        for (uint8_t k = 0; k < USB_HID_XFER_PER_DEV; k++) {
            if (usb_host_transfer_submit(slot->xfer[k]) != ESP_OK) {
                slot->xfer_err = true;
            }
        }
        if (slot->xfer_err) {
            hid_teardown(slot, "initial submit failed");
            continue;
        }
        usb_disp_log("[HID] %s addr=%u streaming", hid_kind_str(slot->protocol),
                     slot->addr);
        s_change_gen++;
    }
}

static void hid_client_task(void *arg) {
    (void)arg;
    while (true) {
        usb_host_client_handle_events(s_hid_client, pdMS_TO_TICKS(100));
        // Streaming slots only: staged slots are owned by hid_poll()
        // (app thread), so a replug racing setup is torn down there.
        // Splitting ownership avoids double-close of the device handle.
        for (uint8_t i = 0; i < USB_HID_MAX_DEV; i++) {
            hid_slot_t *slot = &s_slots[i];
            if (slot->state == HID_SLOT_STREAMING && (slot->gone || slot->xfer_err)) {
                // Give errored transfers a moment to complete as CANCELED.
                vTaskDelay(pdMS_TO_TICKS(50));
                hid_teardown(slot, slot->gone ? "disconnected" : "transfer error");
            }
        }
        if (s_scan_needed) {
            s_scan_needed = false;
            hid_scan();
        }
    }
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
    if (s_hid_ctrl_mutex == NULL || s_hid_ctrl_done == NULL) {
        usb_host_client_deregister(s_hid_client);
        s_hid_client = NULL;
        return false;
    }
    s_hid_started = true;
    s_scan_needed = true;
    xTaskCreate(hid_client_task, "usbhid_client", 4096, NULL, 5, NULL);
    usb_disp_log("[HID] client started");
    return true;
}

bool usb_hid_poll(void) {
    if (!s_hid_started) {
        return false;
    }
    uint32_t before = s_change_gen;
    hid_setup_staged();
    // Health-check streaming claims; a dead handle means a missed DEV_GONE.
    for (uint8_t i = 0; i < USB_HID_MAX_DEV; i++) {
        hid_slot_t *slot = &s_slots[i];
        if (slot->state == HID_SLOT_STREAMING && slot->dev != NULL && !slot->gone) {
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
        if (slot->state != HID_SLOT_STREAMING || slot->dev == NULL) {
            continue;
        }
        out[n].addr = slot->addr;
        out[n].protocol = slot->protocol;
        out[n].vid = slot->vid;
        out[n].pid = slot->pid;
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
