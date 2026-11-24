/* esp_heap_caps.h for a core: the engine asks how much PSRAM is left before
 * growing a cache. The core's heap answers that from its own arena. */
#ifndef MPOS_DUKE_ESP_HEAP_CAPS_H
#define MPOS_DUKE_ESP_HEAP_CAPS_H

#include <stddef.h>

#define MALLOC_CAP_SPIRAM 0x00000800
#define MALLOC_CAP_INTERNAL 0x00001000
#define MALLOC_CAP_8BIT 0x00000004

size_t heap_caps_get_free_size(unsigned caps);
size_t heap_caps_get_largest_free_block(unsigned caps);
void *heap_caps_malloc(size_t size, unsigned caps);
void heap_caps_free(void *ptr);

#endif
