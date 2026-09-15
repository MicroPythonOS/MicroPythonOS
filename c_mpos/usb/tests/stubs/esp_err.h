// Host-test stub for IDF esp_err.h. Only what usb_hid.c uses.
#ifndef HOST_ESP_ERR_H
#define HOST_ESP_ERR_H

typedef int esp_err_t;

#define ESP_OK 0
#define ESP_FAIL 0x101
#define ESP_ERR_NO_MEM 0x102
#define ESP_ERR_INVALID_ARG 0x103
#define ESP_ERR_INVALID_STATE 0x104
#define ESP_ERR_NOT_FOUND 0x105
#define ESP_ERR_NOT_SUPPORTED 0x106

#endif
