// Host-test stub for FreeRTOS FreeRTOS.h. Only what usb_hid.c uses.
#ifndef HOST_FREERTOS_H
#define HOST_FREERTOS_H

#include <stdint.h>

typedef int BaseType_t;
typedef unsigned int UBaseType_t;
typedef unsigned int TickType_t;

#define pdFALSE 0
#define pdTRUE 1
#define pdPASS 1
#define pdMS_TO_TICKS(ms) ((TickType_t)(ms))

#endif
