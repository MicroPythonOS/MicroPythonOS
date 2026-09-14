// Host-test stub for IDF esp_timer.h. Time is fake: vTaskDelay advances
// it, so tests never sleep. See fake_usb_host.c.
#ifndef HOST_ESP_TIMER_H
#define HOST_ESP_TIMER_H

#include <stdint.h>

int64_t esp_timer_get_time(void);

#endif
