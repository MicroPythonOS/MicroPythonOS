// Host-test stub for FreeRTOS task.h. Tasks never run: xTaskCreate only
// records the entry point for assertions. vTaskDelay advances the fake
// clock instead of sleeping. See fake_usb_host.c.
#ifndef HOST_TASK_H
#define HOST_TASK_H

#include "freertos/FreeRTOS.h"

typedef void *TaskHandle_t;
typedef void (*TaskFunction_t)(void *arg);

int xTaskCreate(TaskFunction_t fn, const char *name, unsigned stack,
                void *arg, unsigned prio, TaskHandle_t *handle);
void vTaskDelay(TickType_t ticks);
void vTaskDelete(void *task);

#endif
