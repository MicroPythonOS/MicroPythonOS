// Scriptable fake IDF usb_host + FreeRTOS for host-testing the real
// src/usb_hid.c (compiled in via #include from test_hid_host.c).
// Single-threaded: tasks never run, vTaskDelay advances a fake clock, so
// tests never sleep. Interrupt-transfer completion is scripted:
// auto-complete inline, stay pending for fake_complete(), or wedge.
#ifndef FAKE_USB_HOST_H
#define FAKE_USB_HOST_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "esp_err.h"
#include "usb/usb_host.h"

extern int64_t fake_now_us;

void fake_reset(void);
void fake_advance_ms(uint32_t ms);

// Virtual devices. cfg_blob is the raw config descriptor bytes starting
// at the config header (hid_find_boot_iface walks from cdesc).
void fake_plug(uint8_t addr, uint16_t vid, uint16_t pid, uint8_t dev_class,
               int speed, const uint8_t *cfg_blob, uint16_t cfg_len);
void fake_unplug(uint8_t addr);
// Topology: which (hub addr, port) a device hangs off (for device_info
// parent resolution). Defaults to hub 0 / port 0 = matches nothing.
void fake_set_parent(uint8_t addr, uint8_t hub_addr, uint8_t port);
void fake_set_open_err(uint8_t addr, esp_err_t err);
void fake_set_claim_err(uint8_t addr, esp_err_t err);
void fake_set_info_err(uint8_t addr, esp_err_t err);
void fake_set_submit_err(esp_err_t err);
void fake_set_autocomplete(bool on);
void fake_set_autocomplete_data(const uint8_t *data, uint8_t len);
void fake_set_control_status(usb_transfer_status_t st);
void fake_set_submit_control_err(esp_err_t err);
// When true, halt/flush complete nothing (wedged pipe): reaps time out.
void fake_set_nowedge(bool on);
// One-shot: the next halt-completed transfer lands COMPLETED with this
// data (slow answer between timeout and halt: REAP_DATA path).
void fake_set_reap_data(const uint8_t *data, uint8_t len);
void fake_set_register_err(esp_err_t err);
// Global claim budget: the first n interface_claim calls succeed (subject
// to per-device errors), the rest fail with ESP_ERR_NOT_SUPPORTED.
// -1 = unlimited (default). Proves mice-before-keyboards claim order.
void fake_set_claim_allow(int n);

// Stack events. fake_unplug() queues DEV_GONE itself; NEW_DEV is queued
// explicitly (or just call hid_scan() via pump in the test).
void fake_queue_new_dev(uint8_t addr);
void fake_deliver_events(void);
usb_host_client_event_cb_t fake_client_cb(void);

// Created (never running) tasks, in creation order.
int fake_task_count(void);
void *fake_task_fn(int i);
const char *fake_task_name(int i);

// Pending interrupt transfers.
int fake_pending_count(void);
usb_transfer_t *fake_pending(int i);
void fake_complete(usb_transfer_t *x, usb_transfer_status_t st,
                   const uint8_t *data, int len);

// Lifecycle call log, in order (retire-order assertions).
typedef enum {
    FC_HALT,
    FC_FLUSH,
    FC_CLEAR,
    FC_FREE,
    FC_RELEASE,
    FC_CLOSE,
    FC_CLAIM,
    FC_SUBMIT,
    FC_SUBMIT_CTRL,
    FC_ALLOC,
    FC_OPEN,
} fake_call_t;
int fake_call_count(void);
fake_call_t fake_call(int i);
void fake_call_clear(void);

int fake_live_xfers(void);

// usb_disp_log capture.
int fake_log_count(void);
const char *fake_log_line(int i);
bool fake_log_has(const char *substr);
void fake_log_clear(void);

#endif
