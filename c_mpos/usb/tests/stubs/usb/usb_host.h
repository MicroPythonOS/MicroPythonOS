// Host-test stub for IDF usb_host (usb/usb_host.h). Only the surface
// usb_hid.c uses. Behavior lives in fake_usb_host.c; this header only
// declares types.
#ifndef HOST_USB_HOST_H
#define HOST_USB_HOST_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "esp_err.h"

typedef void *usb_host_client_handle_t;
typedef void *usb_device_handle_t;

typedef enum {
    USB_TRANSFER_STATUS_COMPLETED = 0,
    USB_TRANSFER_STATUS_ERROR,
    USB_TRANSFER_STATUS_TIMED_OUT,
    USB_TRANSFER_STATUS_CANCELED,
    USB_TRANSFER_STATUS_STALL,
    USB_TRANSFER_STATUS_OVERFLOW,
    USB_TRANSFER_STATUS_SKIPPED,
    USB_TRANSFER_STATUS_NO_DEVICE,
} usb_transfer_status_t;

typedef struct usb_transfer_s usb_transfer_t;
typedef void (*usb_transfer_cb_t)(usb_transfer_t *xfer);

struct usb_transfer_s {
    usb_transfer_status_t status;
    int actual_num_bytes;
    int num_bytes;
    uint8_t *data_buffer;
    usb_device_handle_t device_handle;
    uint8_t bEndpointAddress;
    usb_transfer_cb_t callback;
    void *context;
};

typedef enum {
    USB_HOST_CLIENT_EVENT_NEW_DEV = 0,
    USB_HOST_CLIENT_EVENT_DEV_GONE,
} usb_host_client_event_t;

typedef struct {
    usb_host_client_event_t event;
    union {
        struct {
            uint8_t address;
        } new_dev;
        struct {
            usb_device_handle_t dev_hdl;
        } dev_gone;
    };
} usb_host_client_event_msg_t;

typedef void (*usb_host_client_event_cb_t)(const usb_host_client_event_msg_t *msg,
                                           void *arg);

typedef struct {
    bool is_synchronous;
    uint8_t max_num_event_msg;
    struct {
        usb_host_client_event_cb_t client_event_callback;
        void *callback_arg;
    } async;
} usb_host_client_config_t;

typedef enum {
    USB_SPEED_LOW = 0,
    USB_SPEED_FULL,
    USB_SPEED_HIGH,
} usb_speed_t;

typedef struct {
    uint8_t bLength;
    uint8_t bDescriptorType;
    uint8_t bDeviceClass;
    uint16_t idVendor;
    uint16_t idProduct;
} usb_device_desc_t;

typedef struct {
    uint8_t bLength;
    uint8_t bDescriptorType;
    uint16_t wTotalLength;
} usb_config_desc_t;

// Mirrors the real IDF layout (names must match: production code reads
// parent.port_num / parent.dev_hdl / dev_addr for the HID port skip).
typedef struct {
    usb_device_handle_t dev_hdl;
    uint8_t port_num;
} usb_parent_dev_info_t;

typedef struct {
    usb_parent_dev_info_t parent;
    usb_speed_t speed;
    uint8_t dev_addr;
} usb_device_info_t;

esp_err_t usb_host_client_register(const usb_host_client_config_t *config,
                                   usb_host_client_handle_t *out);
esp_err_t usb_host_client_deregister(usb_host_client_handle_t client);
esp_err_t usb_host_client_handle_events(usb_host_client_handle_t client,
                                        uint32_t timeout_ticks);
esp_err_t usb_host_device_open(usb_host_client_handle_t client, uint8_t addr,
                               usb_device_handle_t *out);
esp_err_t usb_host_device_close(usb_host_client_handle_t client,
                                usb_device_handle_t dev);
esp_err_t usb_host_device_info(usb_device_handle_t dev, usb_device_info_t *info);
esp_err_t usb_host_device_addr_list_fill(int size, uint8_t *addrs, int *n);
esp_err_t usb_host_get_device_descriptor(usb_device_handle_t dev,
                                         const usb_device_desc_t **out);
esp_err_t usb_host_get_active_config_descriptor(usb_device_handle_t dev,
                                                const usb_config_desc_t **out);
esp_err_t usb_host_interface_claim(usb_host_client_handle_t client,
                                   usb_device_handle_t dev, uint8_t iface,
                                   int flags);
esp_err_t usb_host_interface_release(usb_host_client_handle_t client,
                                     usb_device_handle_t dev, uint8_t iface);
esp_err_t usb_host_transfer_alloc(size_t num_bytes, int flags, usb_transfer_t **out);
esp_err_t usb_host_transfer_free(usb_transfer_t *xfer);
esp_err_t usb_host_transfer_submit(usb_transfer_t *xfer);
esp_err_t usb_host_transfer_submit_control(usb_host_client_handle_t client,
                                           usb_transfer_t *xfer);
esp_err_t usb_host_endpoint_halt(usb_device_handle_t dev, uint8_t ep);
esp_err_t usb_host_endpoint_flush(usb_device_handle_t dev, uint8_t ep);
esp_err_t usb_host_endpoint_clear(usb_device_handle_t dev, uint8_t ep);

#endif
