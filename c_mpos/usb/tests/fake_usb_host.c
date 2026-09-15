// Fake IDF usb_host + FreeRTOS + esp_timer + usb_disp_log for
// host-testing the real src/usb_hid.c. See fake_usb_host.h.
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "fake_usb_host.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

int64_t fake_now_us = 0;

int64_t esp_timer_get_time(void) {
    return fake_now_us;
}

void vTaskDelay(TickType_t ticks) {
    fake_now_us += (int64_t)ticks * 1000;
}

void vTaskDelete(void *task) {
    (void)task;
}

#define FAKE_MAX_TASKS 4
static struct {
    void *fn;
    const char *name;
} s_tasks[FAKE_MAX_TASKS];
static int s_ntasks = 0;

int xTaskCreate(TaskFunction_t fn, const char *name, unsigned stack,
                void *arg, unsigned prio, TaskHandle_t *handle) {
    (void)stack;
    (void)arg;
    (void)prio;
    if (s_ntasks < FAKE_MAX_TASKS) {
        s_tasks[s_ntasks].fn = (void *)fn;
        s_tasks[s_ntasks].name = name;
        s_ntasks++;
    }
    if (handle != NULL) {
        *handle = (void *)0x1;
    }
    return pdPASS;
}

int fake_task_count(void) {
    return s_ntasks;
}

void *fake_task_fn(int i) {
    return s_tasks[i].fn;
}

const char *fake_task_name(int i) {
    return s_tasks[i].name;
}

int xSemaphoreTake(SemaphoreHandle_t sem, TickType_t ticks) {
    int *count = (int *)sem;
    if (*count > 0) {
        (*count)--;
        return pdTRUE;
    }
    if (ticks == 0) {
        return pdFALSE;
    }
    fake_now_us += (int64_t)ticks * 1000;
    return pdFALSE;
}

int xSemaphoreGive(SemaphoreHandle_t sem) {
    int *count = (int *)sem;
    if (*count < 1000) {
        (*count)++;
    }
    return pdTRUE;
}

void vSemaphoreDelete(SemaphoreHandle_t sem) {
    free(sem);
}

SemaphoreHandle_t xSemaphoreCreateBinary(void) {
    int *count = (int *)calloc(1, sizeof(int));
    return (SemaphoreHandle_t)count;
}

SemaphoreHandle_t xSemaphoreCreateMutex(void) {
    int *count = (int *)calloc(1, sizeof(int));
    *count = 1;
    return (SemaphoreHandle_t)count;
}

// ---- usb_disp_log capture ----

#define FAKE_LOG_LINES 128
#define FAKE_LOG_LEN 256
static char s_log[FAKE_LOG_LINES][FAKE_LOG_LEN];
static int s_nlog = 0;

void usb_disp_log(const char *fmt, ...) {
    char *dst = s_log[s_nlog % FAKE_LOG_LINES];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(dst, FAKE_LOG_LEN, fmt, ap);
    va_end(ap);
    s_nlog++;
}

int fake_log_count(void) {
    return s_nlog;
}

const char *fake_log_line(int i) {
    return s_log[i % FAKE_LOG_LINES];
}

bool fake_log_has(const char *substr) {
    int n = s_nlog < FAKE_LOG_LINES ? s_nlog : FAKE_LOG_LINES;
    for (int i = 0; i < n; i++) {
        if (strstr(s_log[i], substr) != NULL) {
            return true;
        }
    }
    return false;
}

void fake_log_clear(void) {
    s_nlog = 0;
}

// ---- fake device model ----

#define FAKE_MAX_DEV 16
#define FAKE_CFG_MAX 128

typedef struct {
    bool used;
    bool plugged;
    uint8_t addr;
    uint16_t vid;
    uint16_t pid;
    uint8_t dev_class;
    int speed;
    uint8_t parent_hub;
    uint8_t parent_port;
    uint8_t cfg[FAKE_CFG_MAX];
    uint16_t cfg_len;
    usb_device_desc_t ddesc;
    esp_err_t open_err;
    esp_err_t claim_err;
    esp_err_t info_err;
} fake_dev_t;

static fake_dev_t s_devs[FAKE_MAX_DEV];

static fake_dev_t *fake_find(uint8_t addr) {
    for (int i = 0; i < FAKE_MAX_DEV; i++) {
        if (s_devs[i].used && s_devs[i].addr == addr) {
            return &s_devs[i];
        }
    }
    return NULL;
}

static fake_dev_t *fake_find_hdl(usb_device_handle_t hdl) {
    for (int i = 0; i < FAKE_MAX_DEV; i++) {
        if (s_devs[i].used && (usb_device_handle_t)&s_devs[i] == hdl) {
            return &s_devs[i];
        }
    }
    return NULL;
}

static esp_err_t s_register_err = ESP_OK;
static esp_err_t s_submit_err = ESP_OK;
static bool s_autocomplete = true;
static uint8_t s_ac_data[8];
static uint8_t s_ac_len = 0;
static usb_transfer_status_t s_ctrl_status = USB_TRANSFER_STATUS_COMPLETED;
static esp_err_t s_submit_ctrl_err = ESP_OK;
static bool s_nowedge = false;
static uint8_t s_reap_data[8];
static uint8_t s_reap_len = 0;
static bool s_reap_armed = false;

static usb_host_client_event_cb_t s_client_cb = NULL;
static void *s_client_cb_arg = NULL;
static int s_claim_allow = -1;

#define FAKE_MAX_EV 16
static usb_host_client_event_msg_t s_evs[FAKE_MAX_EV];
static int s_nevs = 0;

#define FAKE_MAX_PEND 16
static usb_transfer_t *s_pend[FAKE_MAX_PEND];
static int s_npend = 0;

#define FAKE_MAX_CALLS 256
static fake_call_t s_calls[FAKE_MAX_CALLS];
static int s_ncalls = 0;

static int s_live_xfers = 0;

static void fake_log_call(fake_call_t c) {
    if (s_ncalls < FAKE_MAX_CALLS) {
        s_calls[s_ncalls++] = c;
    }
}

void fake_reset(void) {
    fake_now_us = 0;
    memset(s_devs, 0, sizeof(s_devs));
    s_register_err = ESP_OK;
    s_submit_err = ESP_OK;
    s_autocomplete = true;
    s_ac_len = 0;
    s_ctrl_status = USB_TRANSFER_STATUS_COMPLETED;
    s_submit_ctrl_err = ESP_OK;
    s_nowedge = false;
    s_reap_len = 0;
    s_reap_armed = false;
    s_client_cb = NULL;
    s_client_cb_arg = NULL;
    s_claim_allow = -1;
    s_nevs = 0;
    s_npend = 0;
    s_ncalls = 0;
    s_live_xfers = 0;
    s_ntasks = 0;
    s_nlog = 0;
}

void fake_advance_ms(uint32_t ms) {
    fake_now_us += (int64_t)ms * 1000;
}

void fake_plug(uint8_t addr, uint16_t vid, uint16_t pid, uint8_t dev_class,
               int speed, const uint8_t *cfg_blob, uint16_t cfg_len) {
    fake_dev_t *d = fake_find(addr);
    if (d == NULL) {
        for (int i = 0; i < FAKE_MAX_DEV; i++) {
            if (!s_devs[i].used) {
                d = &s_devs[i];
                break;
            }
        }
    }
    if (d == NULL) {
        return;
    }
    memset(d, 0, sizeof(*d));
    d->used = true;
    d->plugged = true;
    d->addr = addr;
    d->vid = vid;
    d->pid = pid;
    d->dev_class = dev_class;
    d->speed = speed;
    d->open_err = ESP_OK;
    d->claim_err = ESP_OK;
    d->info_err = ESP_OK;
    if (cfg_len > FAKE_CFG_MAX) {
        cfg_len = FAKE_CFG_MAX;
    }
    memcpy(d->cfg, cfg_blob, cfg_len);
    d->cfg_len = cfg_len;
    d->ddesc.bDeviceClass = dev_class;
    d->ddesc.idVendor = vid;
    d->ddesc.idProduct = pid;
}

void fake_unplug(uint8_t addr) {
    fake_dev_t *d = fake_find(addr);
    if (d == NULL) {
        return;
    }
    d->plugged = false;
    if (s_nevs < FAKE_MAX_EV) {
        s_evs[s_nevs].event = USB_HOST_CLIENT_EVENT_DEV_GONE;
        s_evs[s_nevs].dev_gone.dev_hdl = (usb_device_handle_t)d;
        s_nevs++;
    }
}

void fake_set_open_err(uint8_t addr, esp_err_t err) {
    fake_dev_t *d = fake_find(addr);
    if (d != NULL) {
        d->open_err = err;
    }
}
void fake_set_parent(uint8_t addr, uint8_t hub_addr, uint8_t port) {
    fake_dev_t *d = fake_find(addr);
    if (d != NULL) {
        d->parent_hub = hub_addr;
        d->parent_port = port;
    }
}

void fake_set_claim_err(uint8_t addr, esp_err_t err) {
    fake_dev_t *d = fake_find(addr);
    if (d != NULL) {
        d->claim_err = err;
    }
}

void fake_set_info_err(uint8_t addr, esp_err_t err) {
    fake_dev_t *d = fake_find(addr);
    if (d != NULL) {
        d->info_err = err;
    }
}

void fake_set_submit_err(esp_err_t err) {
    s_submit_err = err;
}

void fake_set_autocomplete(bool on) {
    s_autocomplete = on;
}

void fake_set_autocomplete_data(const uint8_t *data, uint8_t len) {
    if (len > sizeof(s_ac_data)) {
        len = sizeof(s_ac_data);
    }
    memcpy(s_ac_data, data, len);
    s_ac_len = len;
}

void fake_set_control_status(usb_transfer_status_t st) {
    s_ctrl_status = st;
}

void fake_set_submit_control_err(esp_err_t err) {
    s_submit_ctrl_err = err;
}

void fake_set_nowedge(bool on) {
    s_nowedge = on;
}

void fake_set_reap_data(const uint8_t *data, uint8_t len) {
    if (len > sizeof(s_reap_data)) {
        len = sizeof(s_reap_data);
    }
    memcpy(s_reap_data, data, len);
    s_reap_len = len;
    s_reap_armed = true;
}

void fake_set_register_err(esp_err_t err) {
    s_register_err = err;
}

void fake_set_claim_allow(int n) {
    s_claim_allow = n;
}

void fake_queue_new_dev(uint8_t addr) {
    if (s_nevs < FAKE_MAX_EV) {
        s_evs[s_nevs].event = USB_HOST_CLIENT_EVENT_NEW_DEV;
        s_evs[s_nevs].new_dev.address = addr;
        s_nevs++;
    }
}

void fake_deliver_events(void) {
    for (int i = 0; i < s_nevs; i++) {
        if (s_client_cb != NULL) {
            s_client_cb(&s_evs[i], s_client_cb_arg);
        }
    }
    s_nevs = 0;
}

usb_host_client_event_cb_t fake_client_cb(void) {
    return s_client_cb;
}

int fake_pending_count(void) {
    return s_npend;
}

usb_transfer_t *fake_pending(int i) {
    return s_pend[i];
}

void fake_complete(usb_transfer_t *x, usb_transfer_status_t st,
                   const uint8_t *data, int len) {
    for (int i = 0; i < s_npend; i++) {
        if (s_pend[i] == x) {
            memmove(&s_pend[i], &s_pend[i + 1],
                    (size_t)(s_npend - i - 1) * sizeof(s_pend[0]));
            s_npend--;
            break;
        }
    }
    x->status = st;
    if (data != NULL && len > 0) {
        x->actual_num_bytes = len;
        memcpy(x->data_buffer, data, (size_t)len);
    } else {
        x->actual_num_bytes = 0;
    }
    if (x->callback != NULL) {
        x->callback(x);
    }
}

int fake_call_count(void) {
    return s_ncalls;
}

fake_call_t fake_call(int i) {
    return s_calls[i];
}

void fake_call_clear(void) {
    s_ncalls = 0;
}

int fake_live_xfers(void) {
    return s_live_xfers;
}

esp_err_t usb_host_client_register(const usb_host_client_config_t *config,
                                   usb_host_client_handle_t *out) {
    if (s_register_err != ESP_OK) {
        return s_register_err;
    }
    s_client_cb = config->async.client_event_callback;
    s_client_cb_arg = config->async.callback_arg;
    *out = (usb_host_client_handle_t)0xC11E47;
    return ESP_OK;
}

esp_err_t usb_host_client_deregister(usb_host_client_handle_t client) {
    (void)client;
    return ESP_OK;
}

esp_err_t usb_host_client_unblock(usb_host_client_handle_t client) {
    (void)client;
    return ESP_OK;
}

esp_err_t usb_host_client_handle_events(usb_host_client_handle_t client,
                                        uint32_t timeout_ticks) {
    (void)client;
    fake_deliver_events();
    fake_now_us += (int64_t)timeout_ticks * 1000;
    return ESP_OK;
}

esp_err_t usb_host_device_open(usb_host_client_handle_t client, uint8_t addr,
                               usb_device_handle_t *out) {
    (void)client;
    fake_log_call(FC_OPEN);
    fake_dev_t *d = fake_find(addr);
    if (d == NULL || !d->plugged) {
        return ESP_ERR_NOT_FOUND;
    }
    if (d->open_err != ESP_OK) {
        return d->open_err;
    }
    *out = (usb_device_handle_t)d;
    return ESP_OK;
}

esp_err_t usb_host_device_close(usb_host_client_handle_t client,
                                usb_device_handle_t dev) {
    (void)client;
    (void)dev;
    fake_log_call(FC_CLOSE);
    return ESP_OK;
}

esp_err_t usb_host_device_info(usb_device_handle_t dev, usb_device_info_t *info) {
    fake_dev_t *d = fake_find_hdl(dev);
    if (d == NULL) {
        return ESP_ERR_NOT_FOUND;
    }
    if (d->info_err != ESP_OK) {
        return d->info_err;
    }
    info->speed = (usb_speed_t)d->speed;
    info->parent.port_num = d->parent_port;
    fake_dev_t *hub = fake_find(d->parent_hub);
    info->parent.dev_hdl = (hub != NULL) ? (usb_device_handle_t)hub : NULL;
    info->dev_addr = d->addr;
    return ESP_OK;
}

esp_err_t usb_host_device_addr_list_fill(int size, uint8_t *addrs, int *n) {
    int count = 0;
    for (int i = 0; i < FAKE_MAX_DEV && count < size; i++) {
        if (s_devs[i].used && s_devs[i].plugged) {
            addrs[count++] = s_devs[i].addr;
        }
    }
    *n = count;
    return ESP_OK;
}

esp_err_t usb_host_get_device_descriptor(usb_device_handle_t dev,
                                         const usb_device_desc_t **out) {
    fake_dev_t *d = fake_find_hdl(dev);
    if (d == NULL) {
        return ESP_ERR_NOT_FOUND;
    }
    *out = &d->ddesc;
    return ESP_OK;
}

esp_err_t usb_host_get_active_config_descriptor(usb_device_handle_t dev,
                                                const usb_config_desc_t **out) {
    fake_dev_t *d = fake_find_hdl(dev);
    if (d == NULL || d->cfg_len == 0) {
        return ESP_ERR_NOT_FOUND;
    }
    *out = (const usb_config_desc_t *)d->cfg;
    return ESP_OK;
}

esp_err_t usb_host_interface_claim(usb_host_client_handle_t client,
                                   usb_device_handle_t dev, uint8_t iface,
                                   int flags) {
    (void)client;
    (void)iface;
    (void)flags;
    fake_log_call(FC_CLAIM);
    fake_dev_t *d = fake_find_hdl(dev);
    if (d == NULL) {
        return ESP_ERR_NOT_FOUND;
    }
    if (s_claim_allow == 0) {
        return ESP_ERR_NOT_SUPPORTED;
    }
    if (s_claim_allow > 0) {
        s_claim_allow--;
    }
    return d->claim_err;
}

esp_err_t usb_host_interface_release(usb_host_client_handle_t client,
                                     usb_device_handle_t dev, uint8_t iface) {
    (void)client;
    (void)dev;
    (void)iface;
    fake_log_call(FC_RELEASE);
    return ESP_OK;
}

esp_err_t usb_host_transfer_alloc(size_t num_bytes, int flags,
                                  usb_transfer_t **out) {
    (void)flags;
    fake_log_call(FC_ALLOC);
    usb_transfer_t *x = (usb_transfer_t *)calloc(1, sizeof(usb_transfer_t));
    if (x == NULL) {
        return ESP_ERR_NO_MEM;
    }
    x->data_buffer = (uint8_t *)calloc(1, num_bytes > 8 ? num_bytes : 8);
    if (x->data_buffer == NULL) {
        free(x);
        return ESP_ERR_NO_MEM;
    }
    s_live_xfers++;
    *out = x;
    return ESP_OK;
}

esp_err_t usb_host_transfer_free(usb_transfer_t *xfer) {
    fake_log_call(FC_FREE);
    free(xfer->data_buffer);
    free(xfer);
    s_live_xfers--;
    return ESP_OK;
}

esp_err_t usb_host_transfer_submit(usb_transfer_t *xfer) {
    fake_log_call(FC_SUBMIT);
    if (s_submit_err != ESP_OK) {
        return s_submit_err;
    }
    if (s_autocomplete) {
        xfer->status = USB_TRANSFER_STATUS_COMPLETED;
        xfer->actual_num_bytes = s_ac_len;
        memcpy(xfer->data_buffer, s_ac_data, s_ac_len);
        if (xfer->callback != NULL) {
            xfer->callback(xfer);
        }
        return ESP_OK;
    }
    if (s_npend < FAKE_MAX_PEND) {
        s_pend[s_npend++] = xfer;
    }
    return ESP_OK;
}

esp_err_t usb_host_transfer_submit_control(usb_host_client_handle_t client,
                                           usb_transfer_t *xfer) {
    (void)client;
    fake_log_call(FC_SUBMIT_CTRL);
    if (s_submit_ctrl_err != ESP_OK) {
        return s_submit_ctrl_err;
    }
    xfer->status = s_ctrl_status;
    xfer->actual_num_bytes = 0;
    if (xfer->callback != NULL) {
        xfer->callback(xfer);
    }
    return ESP_OK;
}

// Halt completes pending transfers of that endpoint inline as CANCELED,
// like the real stack (unless wedged). One armed reap-data completion
// lands COMPLETED instead (slow answer between timeout and halt).
static void fake_finish_pending(usb_device_handle_t dev, uint8_t ep) {
    for (int i = s_npend - 1; i >= 0; i--) {
        usb_transfer_t *x = s_pend[i];
        if (x->device_handle == dev && x->bEndpointAddress == ep) {
            memmove(&s_pend[i], &s_pend[i + 1],
                    (size_t)(s_npend - i - 1) * sizeof(s_pend[0]));
            s_npend--;
            if (s_reap_armed) {
                s_reap_armed = false;
                x->status = USB_TRANSFER_STATUS_COMPLETED;
                x->actual_num_bytes = s_reap_len;
                memcpy(x->data_buffer, s_reap_data, s_reap_len);
            } else {
                x->status = USB_TRANSFER_STATUS_CANCELED;
                x->actual_num_bytes = 0;
            }
            if (x->callback != NULL) {
                x->callback(x);
            }
        }
    }
}

esp_err_t usb_host_endpoint_halt(usb_device_handle_t dev, uint8_t ep) {
    fake_log_call(FC_HALT);
    if (!s_nowedge) {
        fake_finish_pending(dev, ep);
    }
    return ESP_OK;
}

esp_err_t usb_host_endpoint_flush(usb_device_handle_t dev, uint8_t ep) {
    (void)dev;
    (void)ep;
    fake_log_call(FC_FLUSH);
    return ESP_OK;
}

esp_err_t usb_host_endpoint_clear(usb_device_handle_t dev, uint8_t ep) {
    (void)dev;
    (void)ep;
    fake_log_call(FC_CLEAR);
    return ESP_OK;
}
