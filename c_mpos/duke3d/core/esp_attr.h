/* The Duke engine sources include ESP-IDF's esp_attr.h for IRAM/PSRAM
 * placement. A core blob is linked into flash by its own script, and every
 * piece of writable state lives in the host's arena, so the attributes become
 * empty here instead of pulling in the firmware headers. */
#ifndef MPOS_DUKE_ESP_ATTR_H
#define MPOS_DUKE_ESP_ATTR_H

#define IRAM_ATTR
#define DRAM_ATTR
#define EXT_RAM_ATTR
#define EXT_RAM_BSS_ATTR
#define RTC_DATA_ATTR
#define RTC_NOINIT_ATTR
#define WORD_ALIGNED_ATTR

#endif
