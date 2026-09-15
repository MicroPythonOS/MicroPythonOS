// Host-test stub for FreeRTOS semphr.h. Single-threaded: Take succeeds
// when the count is available, otherwise advances the fake clock and
// fails. See fake_usb_host.c.
#ifndef HOST_SEMPHR_H
#define HOST_SEMPHR_H

#include "freertos/FreeRTOS.h"

typedef void *SemaphoreHandle_t;

SemaphoreHandle_t xSemaphoreCreateBinary(void);
SemaphoreHandle_t xSemaphoreCreateMutex(void);
int xSemaphoreTake(SemaphoreHandle_t sem, TickType_t ticks);
int xSemaphoreGive(SemaphoreHandle_t sem);

#endif
