// mpos_core - load and run a native core that lives in its own flash partition.
//
// Why not a natmod: a natmod's code has to be committed into executable RAM,
// which on ESP32-S3 is IRAM, and a booted badge leaves only a few KB of it
// (the Doom engine needs 142 KB). A core instead sits in a flash partition and
// is executed from there through the instruction cache:
//
//     esp_partition_mmap(part, offset, size, ESP_PARTITION_MMAP_INST, ...)
//
// which costs a handful of the 512 MMU pages, uses no IRAM and no Python heap.
// The blob is linked for the address it is mapped at and cannot be patched at
// load time, so it talks to the OS only through mpos_core_abi_t (see
// core_abi.h): the loader fills that struct from Python callables before
// calling the core's init().
//
// Python API:
//
//     mpos_core.start(label, offset, size, present_band, palette, poll_key,
//                     read_file, alloc, log, wad_path, width, height, frame,
//                     band_rows[, expected_crc[, config_dir]])
//     mpos_core.start_task(label, offset, size, width, height,
//                          band_rows=..., stack_bytes=..., asset=...,
//                          asset_name=..., wad_path=..., config_dir=...,
//                          expected_crc=..., affinity=..., surface=...)
//     mpos_core.tick(now_ms)              - on-task mode only
//     mpos_core.stop()
//     mpos_core.abi_version
//     mpos_core.buffer(size)     - C-heap memory for an asset (free explicitly)
//     mpos_core.buffer_free(buf)
//
// and, while a worker core runs:
//
//     mpos_core.task_frame()     - (buffer index, sequence) or None
//     mpos_core.task_presented() - that frame is on the panel; free its buffer
//     mpos_core.task_surface(i)  - the pixels of buffer i, no copy
//     mpos_core.task_log()       - the next start-up/game log line, or None
//     mpos_core.post_key(code, pressed)
//     mpos_core.task_running()
//     mpos_core.task_stack()     - free bytes on the worker's stack
//
// The blob's first bytes are a mpos_core_entry_t whose abi_version must be
// between MPOS_CORE_ABI_MIN_VERSION and MPOS_CORE_ABI_VERSION.

#include <stdio.h>
#include <string.h>

#include "py/runtime.h"
#include "py/obj.h"
#include "py/objarray.h"
#include "py/mphal.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "freertos/idf_additions.h"

#include "esp_partition.h"
#include "esp_heap_caps.h"
#include "esp_rom_crc.h"
#include "esp_mmu_map.h"
#include "esp_timer.h"
#include "hal/mmu_hal.h"
#include "hal/mmu_types.h"
#include "soc/soc_caps.h"

#include "../core_abi.h"

// The two windows the MMU can serve a flash partition from. A core's text must
// live in the instruction window (IBUS) and its read-only data in the data
// window (DBUS), because instruction memory is not data-readable.
#define MPOS_CORE_TEXT_MIN 0x42000000u
#define MPOS_CORE_TEXT_MAX 0x44000000u
#define MPOS_CORE_DATA_MIN 0x3C000000u
#define MPOS_CORE_DATA_MAX 0x3E000000u

// The Python callbacks are kept alive by the garbage collector only through a
// registered root pointer: a plain C static is invisible to it, and a collected
// bound method would be a dangling pointer the next time the core called back.
MP_REGISTER_ROOT_POINTER(mp_obj_t mpos_core_refs);

// -- worker mode ------------------------------------------------------------

// Two surfaces: the core draws into one while the other is on its way to the
// panel. The handshake below never lets the presenter read a buffer the engine
// is writing, and the engine can run one frame ahead of the display, no more.
#define MPOS_CORE_BUFFERS 2
#define MPOS_CORE_KEY_RING 64
#define MPOS_CORE_LOG_LINES 48
#define MPOS_CORE_LOG_CHARS 160
#define MPOS_CORE_ASSET_NAME 32
#define MPOS_CORE_PATH_CHARS 96
// The engine's stack, not the OS's. Measured with Duke: its deepest path
// (not start-up - that stays under 20 KiB) needs about 38 KiB, so 16, 20, 24
// and 31 KiB all die in play while 48 KiB has 11 KiB to spare. That is more
// than the largest internal block some boards can hand out (the fri3d's DRAM
// comes in 32 KiB islands), which is the one case start_task falls back to
// PSRAM for.
#define MPOS_CORE_WORKER_STACK (48u * 1024u)
// The MicroPython task runs on core 1 (MP_TASK_COREID); the renderer gets the
// other one so the panel transfer and the next frame overlap.
#define MPOS_CORE_WORKER_CORE 0
#define MPOS_CORE_WORKER_PRIORITY 5

// -- state -------------------------------------------------------------------

static const esp_partition_t *s_partition;
// The entry table is copied out of the blob before it is mapped: the loader must
// not read it through the instruction window.
static mpos_core_entry_t s_entry_copy;
static const mpos_core_entry_t *s_entry;
static void *s_mapped;
static size_t s_mapped_size;
// The MMU blocks esp_mmu_map() reserved for us (one per window), released on
// stop(). Without them the pages stay booked for the life of the boot.
static void *s_text_alias;
static void *s_data_alias;
// The core's writable memory: ordinary RAM that is also mapped at the fixed
// address the blob was linked for.
static void *s_arena_buf;
static uint32_t s_arena_addr;
static uint32_t s_arena_size;
static uint32_t s_data_addr;
static uint32_t s_data_size;
static uint32_t s_now_ms;
static int s_width;
static int s_height;
static int s_band_rows;
static uint16_t *s_frame;
static uint32_t s_flags;
static int s_active;

static mp_obj_t s_present_fun;
static mp_obj_t s_palette_fun;
static mp_obj_t s_poll_fun;
static mp_obj_t s_read_fun;
static mp_obj_t s_size_fun;
static mp_obj_t s_log_fun;

// Memory handed to the core is allocated here, not in Python: the core holds
// raw pointers for as long as it runs, so the host owns them and releases them
// when the core stops.
#define MPOS_CORE_MAX_ALLOCATIONS 64
// Blocks up to this size are taken from internal RAM when it has room.
#define MPOS_CORE_SMALL_ALLOC (96u * 1024u)
static void *s_allocs[MPOS_CORE_MAX_ALLOCATIONS];
static int s_alloc_count;

static mpos_core_abi_t s_abi;

// Worker task and its hand-off state.
static TaskHandle_t s_task;
static SemaphoreHandle_t s_task_ready;
static SemaphoreHandle_t s_task_exit;
// Given whenever the presenter starts or stops reading a buffer, so a worker
// waiting for one wakes at once instead of on its next poll.
static SemaphoreHandle_t s_present_wake;
static volatile int s_task_stop;
static volatile int s_task_result;
static volatile int s_front_buffer;
static volatile int s_back_buffer;
static volatile uint32_t s_published;
static int s_presenting;
static uint32_t s_presenting_seq;
static uint32_t s_presented;
static uint16_t *s_buffers[MPOS_CORE_BUFFERS];
static int s_buffer_owned[MPOS_CORE_BUFFERS];
static size_t s_buffer_bytes;

// The asset a worker core reads: an ordinary buffer the app allocated, served
// by the loader's read_file so the engine never asks Python for a byte.
// The asset, in one buffer or in several. A GRP is 2.4 MiB and a fragmented
// heap may not have that in one piece; a handful of 512 KiB buffers is easy to
// find, and a read that crosses a boundary costs one extra memcpy.
#define MPOS_CORE_ASSET_CHUNKS 16
static const uint8_t *s_asset_chunks[MPOS_CORE_ASSET_CHUNKS];
static uint32_t s_asset_chunk_size[MPOS_CORE_ASSET_CHUNKS];
static uint32_t s_asset_chunk_count;
static uint32_t s_asset_size;
static char s_asset_name[MPOS_CORE_ASSET_NAME];
static char s_wad_path[MPOS_CORE_PATH_CHARS];
static char s_config_dir[MPOS_CORE_PATH_CHARS];

// Input and log rings between the two tasks. One producer and one consumer
// each, and the critical section is only a few instructions: a spinlock is
// cheaper than a queue allocation and does not block either side.
static uint8_t *s_key_code;
static uint8_t *s_key_pressed;
static uint32_t s_key_head;
static uint32_t s_key_tail;
static char *s_log_ring;
static uint32_t s_log_head;
static uint32_t s_log_tail;
static uint32_t s_log_lost;
static portMUX_TYPE s_ring_lock = portMUX_INITIALIZER_UNLOCKED;

// -- mapping ----------------------------------------------------------------

// Map flash pages at a *chosen* virtual address.
//
// esp_partition_mmap()/spi_flash_mmap() pick the vaddr themselves (first free
// MMU block), which is useless for a blob that is linked for a fixed address:
// its absolute jumps point into unmapped instruction space and the CPU faults
// with "MMU entry fault".
//
// Two steps, deliberately:
//
//  1. esp_mmu_map() for the same physical range. It validates the paddr, books
//     the pages so the allocator will not hand them out again, and does its own
//     cache/MMU dance (which must not be copied here: doing disable-interrupts,
//     reprogram, enable by hand from a MicroPython task deadlocks the interrupt
//     watchdog on the S3 - tried it).
//  2. mmu_hal_map_region() to programme the entry at the address the blob was
//     linked for. No cache maintenance is needed: that vaddr was never
//     accessed, and the L1 cache is physically tagged, so the two aliases of
//     the same flash pages cannot disagree.
static esp_err_t map_fixed(uint32_t paddr, uint32_t vaddr, uint32_t size,
                           void **alias) {
    if ((paddr % CONFIG_MMU_PAGE_SIZE) != 0 || (vaddr % CONFIG_MMU_PAGE_SIZE) != 0) {
        return ESP_ERR_INVALID_ARG;
    }

    size_t map_size = (size + CONFIG_MMU_PAGE_SIZE - 1) & ~(size_t)(CONFIG_MMU_PAGE_SIZE - 1);
    void *reserved = NULL;
    esp_err_t err = esp_mmu_map(paddr, map_size, MMU_TARGET_FLASH0,
                                MMU_MEM_CAP_READ | MMU_MEM_CAP_EXEC, 0, &reserved);
    if (err != ESP_OK) {
        return err;
    }

    uint32_t mapped = 0;
    mmu_hal_map_region(0, MMU_TARGET_FLASH0, vaddr, paddr, map_size, &mapped);
    if (mapped < map_size) {
        esp_mmu_unmap(reserved);
        return ESP_ERR_INVALID_SIZE;
    }
    *alias = reserved;
    return ESP_OK;
}

// Map a RAM allocation at a chosen address, one MMU page at a time: the pages
// behind a heap allocation are not guaranteed to be physically contiguous, so
// each page is translated back to its paddr and programmed separately.
static esp_err_t map_arena(uint32_t vaddr, void *buf, uint32_t size) {
    for (uint32_t done = 0; done < size; done += CONFIG_MMU_PAGE_SIZE) {
        esp_paddr_t paddr = 0;
        mmu_target_t target = MMU_TARGET_FLASH0;
        esp_err_t err = esp_mmu_vaddr_to_paddr((void *)((uintptr_t)buf + done),
                                               &paddr, &target);
        if (err != ESP_OK) {
            return err;
        }
        if ((paddr % CONFIG_MMU_PAGE_SIZE) != 0) {
            return ESP_ERR_INVALID_ARG;
        }
        uint32_t mapped = 0;
        mmu_hal_map_region(0, target, vaddr + done, paddr,
                           CONFIG_MMU_PAGE_SIZE, &mapped);
        if (mapped < CONFIG_MMU_PAGE_SIZE) {
            return ESP_ERR_INVALID_SIZE;
        }
    }
    return ESP_OK;
}

static void unmap_arena(uint32_t vaddr, uint32_t size, void *buf) {
    (void)vaddr;
    (void)size;
    heap_caps_free(buf);
}

static void unmap_fixed(uint32_t vaddr, uint32_t size, void *alias) {
    (void)vaddr;
    (void)size;
    // The entries we programmed by hand stay in the MMU for the rest of the
    // boot. Invalidating them with mmu_hal_unmap_region() while the caches are
    // live panics the chip ("Cache error", both cores) as soon as the freed
    // pages are reused - the aliases are never read after stop(), and the next
    // start re-maps the same addresses, so leaving them costs nothing. Only the
    // block esp_mmu_map() booked is released, through IDF's own API.
    if (alias != NULL) {
        esp_mmu_unmap(alias);
    }
}

// -- ABI trampolines (host side) ---------------------------------------------

static void abi_present_band(void *host, int band, int rows, const uint8_t *pixels) {
    (void)host;
    if (s_present_fun == MP_OBJ_NULL) {
        return;
    }
    const bool rgb565 = (s_flags & MPOS_CORE_FLAG_BAND_RGB565) != 0;
    mp_obj_t args[3];
    args[0] = mp_obj_new_int(band);
    args[1] = mp_obj_new_int(rows);
    // pixels == NULL: the core drew the band into the host's own surface, so
    // there is nothing to copy - the callback just says "this band is ready".
    args[2] = pixels == NULL ? mp_const_none
             : mp_obj_new_bytearray_by_ref(
                   (size_t)rows * (size_t)s_width * (rgb565 ? 2u : 1u),
                   (void *)pixels);
    mp_call_function_n_kw(s_present_fun, 3, 0, args);
}

static void abi_palette(void *host, uint16_t *out, int entries) {
    (void)host;
    if (s_palette_fun == MP_OBJ_NULL) {
        return;
    }
    mp_obj_t result = mp_call_function_1(s_palette_fun, mp_obj_new_int(entries));
    mp_buffer_info_t buf;
    if (mp_get_buffer(result, &buf, MP_BUFFER_READ)) {
        size_t bytes = buf.len < (size_t)entries * 2 ? buf.len : (size_t)entries * 2;
        memcpy(out, buf.buf, bytes);
    }
}

static int abi_poll_key(void *host, int *pressed) {
    (void)host;
    if (s_poll_fun == MP_OBJ_NULL) {
        return -1;
    }
    mp_obj_t result = mp_call_function_0(s_poll_fun);
    if (result == mp_const_none) {
        return -1;
    }
    int value = (int)mp_obj_get_int(result);
    if (value < 0) {
        return -1;
    }
    *pressed = (value >> 8) & 0xff;
    return value & 0xff;
}

static uint32_t abi_now_ms(void *host) {
    (void)host;
    // A live clock, not the tick's timestamp: a core measures its own phases
    // with it, and pacing on a clock that only moves once per tick cannot tell
    // how long the tick took. esp_timer is the same clock MicroPython's
    // time.ticks_ms() is built on, and it is safe to read from any task.
    return (uint32_t)(esp_timer_get_time() / 1000);
}

static int abi_read_file(void *host, const char *path, uint32_t offset,
                         void *dst, uint32_t len) {
    (void)host;
    if (s_read_fun == MP_OBJ_NULL) {
        return -1;
    }
    mp_obj_t args[3];
    args[0] = mp_obj_new_str(path, strlen(path));
    args[1] = mp_obj_new_int_from_uint(offset);
    args[2] = mp_obj_new_bytearray_by_ref(len, dst);
    mp_obj_t result = mp_call_function_n_kw(s_read_fun, 3, 0, args);
    if (result == mp_const_none) {
        return -1;
    }
    return (int)mp_obj_get_int(result);
}

static int abi_file_size(void *host, const char *path) {
    (void)host;
    if (s_size_fun == MP_OBJ_NULL) {
        return -1;
    }
    mp_obj_t result = mp_call_function_1(s_size_fun, mp_obj_new_str(path, strlen(path)));
    if (result == mp_const_none) {
        return -1;
    }
    return (int)mp_obj_get_int(result);
}

static void *abi_alloc(void *host, uint32_t bytes) {
    (void)host;
    if (s_alloc_count >= MPOS_CORE_MAX_ALLOCATIONS) {
        return NULL;
    }
    // Small blocks first, because they are usually the hot ones (an engine's
    // framebuffer, lookup tables) and internal RAM is several times faster than
    // PSRAM; big ones (a zone) only fit in PSRAM. Both fall back to the other.
    void *ptr = NULL;
    if (bytes <= MPOS_CORE_SMALL_ALLOC) {
        ptr = heap_caps_malloc(bytes, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    }
    if (ptr == NULL) {
        ptr = heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    }
    if (ptr == NULL) {
        ptr = heap_caps_malloc(bytes, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    }
    if (ptr == NULL) {
        return NULL;
    }
    s_allocs[s_alloc_count++] = ptr;
    return ptr;
}

static void abi_dealloc(void *host, void *ptr) {
    (void)host;
    for (int i = 0; i < s_alloc_count; i++) {
        if (s_allocs[i] == ptr) {
            s_allocs[i] = s_allocs[--s_alloc_count];
            heap_caps_free(ptr);
            return;
        }
    }
}

static void free_allocations(void) {
    while (s_alloc_count > 0) {
        heap_caps_free(s_allocs[--s_alloc_count]);
    }
}

static void abi_log(void *host, const char *text) {
    (void)host;
    // A core that parses a large table in C has no way to yield: it cannot
    // call FreeRTOS, and re-entering MicroPython to sleep from a deep engine
    // frame is not safe. A one-byte sentinel asks for a scheduler yield here,
    // in C, which is what keeps the idle task feeding the interrupt watchdog
    // during Duke3D's start-up.
    if (text != NULL && text[0] == '\x01') {
        vTaskDelay(1);
        return;
    }
    if (s_log_fun == MP_OBJ_NULL) {
        return;
    }
    mp_call_function_1(s_log_fun, mp_obj_new_str(text, strlen(text)));
}

// -- worker-side services ----------------------------------------------------
//
// Nothing below may enter MicroPython: it runs on the worker task, next to a
// main thread that is inside the interpreter.

static void abi_yield(void *host) {
    (void)host;
    // One tick. The idle task then runs, and it is the idle task that feeds
    // the interrupt watchdog during a multi-second engine start-up.
    vTaskDelay(1);
}

static void worker_present_band(void *host, int band, int rows,
                                const uint8_t *pixels) {
    (void)host;
    (void)band;
    (void)rows;
    (void)pixels;
    // The core drew into its own surface; there is nothing to copy and nothing
    // to show yet. frame_ready() is the end of the frame.
}

static void worker_palette(void *host, uint16_t *out, int entries) {
    (void)host;
    if (out != NULL && entries > 0) {
        memset(out, 0, (size_t)entries * 2u);
    }
}

static int worker_poll_key(void *host, int *pressed) {
    (void)host;
    int code = 0;
    int state = 0;
    int have = 0;
    if (s_key_code == NULL) {
        return -1;
    }
    portENTER_CRITICAL(&s_ring_lock);
    if (s_key_head != s_key_tail) {
        const uint32_t slot = s_key_tail % MPOS_CORE_KEY_RING;
        code = s_key_code[slot];
        state = s_key_pressed[slot];
        s_key_tail++;
        have = 1;
    }
    portEXIT_CRITICAL(&s_ring_lock);
    if (!have) {
        return -1;
    }
    *pressed = state;
    return code;
}

static int worker_read_file(void *host, const char *path, uint32_t offset,
                            void *dst, uint32_t len) {
    (void)host;
    if (s_asset_chunk_count == 0 || path == NULL || dst == NULL
            || strcmp(path, s_asset_name) != 0) {
        return -1;
    }
    if (offset >= s_asset_size) {
        return -1;
    }
    uint32_t count = s_asset_size - offset;
    if (count > len) {
        count = len;
    }
    // Walk to the chunk that holds the first byte, then copy across as many
    // chunks as the read needs.
    uint32_t index = 0;
    uint32_t skip = offset;
    while (index < s_asset_chunk_count && skip >= s_asset_chunk_size[index]) {
        skip -= s_asset_chunk_size[index];
        index++;
    }
    uint32_t done = 0;
    while (done < count && index < s_asset_chunk_count) {
        uint32_t available = s_asset_chunk_size[index] - skip;
        uint32_t take = (count - done) < available ? (count - done) : available;
        memcpy((uint8_t *)dst + done, s_asset_chunks[index] + skip, take);
        done += take;
        skip = 0;
        index++;
    }
    return (int)done;
}

static int worker_file_size(void *host, const char *path) {
    (void)host;
    if (s_asset_chunk_count == 0 || path == NULL
            || strcmp(path, s_asset_name) != 0) {
        return -1;
    }
    return (int)s_asset_size;
}

static void log_push(const char *line) {
    if (s_log_ring == NULL || line == NULL) {
        return;
    }
    portENTER_CRITICAL(&s_ring_lock);
    if (s_log_head - s_log_tail >= MPOS_CORE_LOG_LINES) {
        s_log_lost++;
    } else {
        char *dst = s_log_ring
                  + (size_t)(s_log_head % MPOS_CORE_LOG_LINES) * MPOS_CORE_LOG_CHARS;
        size_t i = 0;
        while (line[i] != '\0' && i + 1 < MPOS_CORE_LOG_CHARS) {
            dst[i] = line[i];
            i++;
        }
        dst[i] = '\0';
        s_log_head++;
    }
    portEXIT_CRITICAL(&s_ring_lock);
}

static void worker_log(void *host, const char *text) {
    (void)host;
    if (text == NULL) {
        return;
    }
    if (text[0] == '\x01') {
        // The ABI 8 way of asking for a yield; a core built against the older
        // header still sends it through here.
        vTaskDelay(1);
        return;
    }
    log_push(text);
}

// The end of a frame: publish it, then wait until the buffer the next frame
// goes into is not the one the presenter is reading.
//
// Two rules, and between them they are the whole hand-off:
//
//  - the presenter only ever reads `s_front_buffer`, which is never the buffer
//    the core is drawing into (this function makes them differ before the core
//    carries on);
//  - the core may recycle the buffer it published *two* frames ago, which is
//    the one the presenter may still be reading, so it waits for that.
//
// A frame the presenter never gets to (a newer one was published first) is
// simply overwritten, which is the whole point of a second buffer. Naming the
// condition - "is the presenter reading this one?" - also means a skipped
// frame cannot wedge the pair the way a token count can.
static void worker_frame_ready(void *host) {
    (void)host;
    const int published = s_back_buffer;
    s_back_buffer = published ^ 1;
    portENTER_CRITICAL(&s_ring_lock);
    s_front_buffer = published;
    s_published++;
    portEXIT_CRITICAL(&s_ring_lock);
    for (;;) {
        portENTER_CRITICAL(&s_ring_lock);
        const int busy = s_presenting == s_back_buffer;
        portEXIT_CRITICAL(&s_ring_lock);
        if (!busy || s_task_stop) {
            break;
        }
        // The presenter gives the wake-up when it finishes, so this is a
        // fallback for a signal that arrived just before the check.
        xSemaphoreTake(s_present_wake, pdMS_TO_TICKS(5));
    }
    // The next frame goes into whichever buffer the presenter is not showing.
    s_abi.frame = s_buffers[s_back_buffer];
}

static void core_task_main(void *arg) {
    (void)arg;
    int result = s_entry->init(
        &s_abi, s_wad_path[0] != '\0' ? s_wad_path : NULL,
        s_config_dir[0] != '\0' ? s_config_dir : NULL);
    if (result != 0 && s_entry->stop != NULL) {
        s_entry->stop(&s_abi);
    }
    s_task_result = result;
    xSemaphoreGive(s_task_ready);
    if (result == 0) {
        while (!s_task_stop) {
            s_entry->tick(&s_abi, abi_now_ms(NULL));
        }
        if (s_entry->stop != NULL) {
            s_entry->stop(&s_abi);
        }
    }
    xSemaphoreGive(s_task_exit);
    vTaskDelete(NULL);
}

// -- module functions --------------------------------------------------------

// The partition list is loaded lazily and never refreshed. A bad read of the
// table sector leaves only its first entry in the list (the badge has been
// seen to do this on some cold boots), and every later lookup then claims the
// partition is missing while the flash is intact - the filesystem still
// mounts, because it uses a fixed address. Drop the list and read it again
// before believing that the partition does not exist.
static const esp_partition_t *find_partition(const char *label) {
    const esp_partition_t *partition = esp_partition_find_first(
        ESP_PARTITION_TYPE_APP, ESP_PARTITION_SUBTYPE_ANY, label);
    if (partition == NULL) {
        partition = esp_partition_find_first(
            ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_ANY, label);
    }
    return partition;
}

static const esp_partition_t *find_partition_retry(const char *label) {
    const esp_partition_t *partition = find_partition(label);
    for (int attempt = 0; partition == NULL && attempt < 2; attempt++) {
        esp_partition_unload_all();
        partition = find_partition(label);
    }
    return partition;
}

// Unmap everything the core was given and release its memory. Safe to call
// after a partial map, and after a failed init.
static void core_release(void) {
    if (s_mapped != NULL) {
        unmap_fixed((uint32_t)s_mapped, (uint32_t)s_mapped_size, s_text_alias);
    }
    if (s_data_alias != NULL) {
        unmap_fixed(s_data_addr, s_data_size, s_data_alias);
    }
    if (s_arena_buf != NULL) {
        unmap_arena(s_arena_addr, s_arena_size, s_arena_buf);
    }
    free_allocations();
    s_text_alias = NULL;
    s_data_alias = NULL;
    s_arena_buf = NULL;
    s_arena_addr = 0;
    s_arena_size = 0;
    s_mapped = NULL;
    s_mapped_size = 0;
    s_data_addr = 0;
    s_data_size = 0;
    s_partition = NULL;
    s_entry = NULL;
    s_active = 0;
}

// Map the blob at the addresses it was linked for and fill in the identity
// fields of the ABI. Everything a mode decides (callbacks, surface, who runs
// init) is left to the caller.
static void core_attach(const char *label, size_t offset, size_t size,
                        uint32_t expected_crc) {
    const esp_partition_t *partition = find_partition_retry(label);
    if (partition == NULL) {
        mp_raise_msg_varg(&mp_type_ValueError,
                          MP_ERROR_TEXT("no partition labelled %s"), label);
    }
    if (offset > partition->size || size == 0 || size > partition->size - offset) {
        mp_raise_ValueError(MP_ERROR_TEXT("core does not fit the partition"));
    }

    // Read the entry table through a temporary data mapping to learn where the
    // blob wants to live. The paddr must be page aligned: the blob is mapped
    // at exactly load_addr, so the flash page must start there too.
    const void *tmp = NULL;
    esp_partition_mmap_handle_t tmp_handle = 0;
    esp_err_t err = esp_partition_mmap(partition, offset, size,
                                       ESP_PARTITION_MMAP_DATA, &tmp, &tmp_handle);
    if (err != ESP_OK || tmp == NULL) {
        mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("core read failed: %d"), (int)err);
    }
    // Verify the payload through the temporary mapping, before anything is
    // mapped executable: a corrupt or overwritten core (a stock littlefs write
    // may treat an extent's blocks as free) is refused here rather than run.
    if (expected_crc != 0) {
        uint32_t got = (uint32_t)esp_rom_crc32_le(0, (const uint8_t *)tmp, (uint32_t)size);
        if (got != expected_crc) {
            esp_partition_munmap(tmp_handle);
            mp_raise_msg_varg(&mp_type_OSError,
                              MP_ERROR_TEXT("core CRC mismatch: expected %08x, got %08x"),
                              (unsigned)expected_crc, (unsigned)got);
        }
    }
    const mpos_core_entry_t *probe = (const mpos_core_entry_t *)tmp;
    if (probe->abi_version < MPOS_CORE_ABI_MIN_VERSION
            || probe->abi_version > MPOS_CORE_ABI_VERSION
            || probe->init == NULL) {
        uint32_t found = probe->abi_version;
        esp_partition_munmap(tmp_handle);
        mp_raise_msg_varg(&mp_type_ValueError,
                          MP_ERROR_TEXT("core ABI %u, expected %u..%u"),
                          (unsigned)found,
                          (unsigned)MPOS_CORE_ABI_MIN_VERSION,
                          (unsigned)MPOS_CORE_ABI_VERSION);
    }
    // Copy the table out now: after the temporary mapping goes away the blob is
    // only reachable through the instruction window, and the host must not read
    // data from there (that is exactly the LoadStoreError this layout avoids).
    mpos_core_entry_t entry = *probe;
    esp_partition_munmap(tmp_handle);

    if (entry.load_addr < MPOS_CORE_TEXT_MIN
            || (entry.load_addr % CONFIG_MMU_PAGE_SIZE) != 0) {
        mp_raise_msg_varg(&mp_type_ValueError,
                          MP_ERROR_TEXT("core load address 0x%x is not usable"),
                          (unsigned)entry.load_addr);
    }

    // The text region is everything before the data region; a blob with no
    // rodata maps all of itself as text.
    uint32_t text_size = (uint32_t)size;
    uint32_t data_size = 0;
    if (entry.data_addr != 0) {
        if (entry.data_addr < MPOS_CORE_DATA_MIN
                || entry.data_addr > MPOS_CORE_DATA_MAX
                || (entry.data_addr % CONFIG_MMU_PAGE_SIZE) != 0) {
            mp_raise_msg_varg(&mp_type_ValueError,
                              MP_ERROR_TEXT("core data address 0x%x is not usable"),
                              (unsigned)entry.data_addr);
        }
        if (entry.data_offset == 0
                || (entry.data_offset % CONFIG_MMU_PAGE_SIZE) != 0
                || entry.data_offset > (uint32_t)size) {
            mp_raise_msg_varg(&mp_type_ValueError,
                              MP_ERROR_TEXT("core data offset %u is not usable"),
                              (unsigned)entry.data_offset);
        }
        // A data size of 0 means "everything after the offset": in a blob the
        // data region is last, so the caller's size already describes it.
        data_size = entry.data_size != 0
                    ? entry.data_size
                    : (uint32_t)size - entry.data_offset;
        if (data_size > (uint32_t)size - entry.data_offset) {
            mp_raise_msg_varg(&mp_type_ValueError,
                              MP_ERROR_TEXT("core data region %u+%u does not fit %u bytes"),
                              (unsigned)entry.data_offset,
                              (unsigned)data_size,
                              (unsigned)size);
        }
        text_size = entry.data_offset;
    }
    if (entry.load_addr + text_size > MPOS_CORE_TEXT_MAX) {
        mp_raise_ValueError(MP_ERROR_TEXT("core text does not fit the instruction window"));
    }
    // Mapping rounds up to a page, so the rounded end must still be inside the
    // partition: mapping past it would alias whatever is stored next.
    size_t data_end = (size_t)text_size
                    + ((data_size + CONFIG_MMU_PAGE_SIZE - 1)
                       & ~(size_t)(CONFIG_MMU_PAGE_SIZE - 1));
    if (offset + data_end > partition->size) {
        mp_raise_ValueError(MP_ERROR_TEXT("core does not fit the partition"));
    }

    // Map the blob at its linked addresses: this is the whole point, the code is
    // executed from flash through the cache, with no IRAM and no heap involved.
    // The same flash pages appear twice, as INST for the text and as DATA for
    // the read-only data.
    void *text_alias = NULL;
    err = map_fixed((uint32_t)partition->address + (uint32_t)offset,
                    entry.load_addr, text_size, &text_alias);
    if (err != ESP_OK) {
        mp_raise_msg_varg(&mp_type_OSError,
                          MP_ERROR_TEXT("core map at 0x%x failed: %d"),
                          (unsigned)entry.load_addr, (int)err);
    }
    void *data_alias = NULL;
    if (entry.data_addr != 0) {
        err = map_fixed((uint32_t)partition->address + (uint32_t)offset + entry.data_offset,
                        entry.data_addr, data_size, &data_alias);
        if (err != ESP_OK) {
            unmap_fixed(entry.load_addr, text_size, text_alias);
            mp_raise_msg_varg(&mp_type_OSError,
                              MP_ERROR_TEXT("core data map at 0x%x failed: %d"),
                              (unsigned)entry.data_addr, (int)err);
        }
    }

    // The core's writable memory, mapped at the address it was linked for. It
    // is ordinary RAM (PSRAM when available) that belongs to the host, zeroed
    // because .bss is expected to start at zero.
    void *arena_buf = NULL;
    if (entry.arena_addr != 0) {
        if (entry.arena_addr < MPOS_CORE_DATA_MIN
                || entry.arena_addr > MPOS_CORE_DATA_MAX
                || (entry.arena_addr % CONFIG_MMU_PAGE_SIZE) != 0
                || entry.arena_size == 0
                || (entry.arena_size % CONFIG_MMU_PAGE_SIZE) != 0
                || entry.arena_addr + entry.arena_size > MPOS_CORE_DATA_MAX) {
            unmap_fixed(entry.load_addr, text_size, text_alias);
            if (data_alias != NULL) {
                unmap_fixed(entry.data_addr, data_size, data_alias);
            }
            mp_raise_msg_varg(&mp_type_ValueError,
                              MP_ERROR_TEXT("core arena 0x%x+%u is not usable"),
                              (unsigned)entry.arena_addr,
                              (unsigned)entry.arena_size);
        }
        arena_buf = heap_caps_aligned_alloc(CONFIG_MMU_PAGE_SIZE, entry.arena_size,
                                            MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
        if (arena_buf == NULL) {
            arena_buf = heap_caps_aligned_alloc(CONFIG_MMU_PAGE_SIZE, entry.arena_size,
                                                MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
        }
        if (arena_buf == NULL) {
            unmap_fixed(entry.load_addr, text_size, text_alias);
            if (data_alias != NULL) {
                unmap_fixed(entry.data_addr, data_size, data_alias);
            }
            mp_raise_msg_varg(&mp_type_OSError,
                              MP_ERROR_TEXT("no memory for a %u byte arena"),
                              (unsigned)entry.arena_size);
        }
        memset(arena_buf, 0, entry.arena_size);
        err = map_arena(entry.arena_addr, arena_buf, entry.arena_size);
        if (err != ESP_OK) {
            heap_caps_free(arena_buf);
            unmap_fixed(entry.load_addr, text_size, text_alias);
            if (data_alias != NULL) {
                unmap_fixed(entry.data_addr, data_size, data_alias);
            }
            mp_raise_msg_varg(&mp_type_OSError,
                              MP_ERROR_TEXT("core arena map at 0x%x failed: %d"),
                              (unsigned)entry.arena_addr, (int)err);
        }
    }

    s_arena_buf = arena_buf;
    s_arena_addr = entry.arena_addr;
    s_arena_size = entry.arena_size;
    s_entry_copy = entry;
    s_flags = entry.flags;
    s_partition = partition;
    s_mapped = (void *)entry.load_addr;
    s_mapped_size = text_size;
    s_text_alias = text_alias;
    s_data_alias = data_alias;
    s_data_addr = entry.data_addr;
    s_data_size = data_size;
    s_entry = &s_entry_copy;
    s_active = 1;
}

// The ABI fields every mode shares. The callbacks and the surface are the
// difference between the two modes and are set by each caller.
static void abi_init_common(void) {
    memset(&s_abi, 0, sizeof(s_abi));
    s_abi.version = s_entry->abi_version;
    s_abi.host = NULL;
    s_abi.now_ms = abi_now_ms;
    s_abi.alloc = abi_alloc;
    s_abi.dealloc = abi_dealloc;
    s_abi.frame_width = s_width;
    s_abi.frame_height = s_height;
    s_abi.band_rows = s_band_rows;
}

static mp_obj_t mpos_core_start(size_t n_args, const mp_obj_t *args) {
    // start(label, offset, size, present_band, palette, poll_key, read_file,
    //       file_size, log, wad_path, width, height, frame, band_rows,
    //       expected_crc=0, config_dir=None)
    if (n_args < 14 || n_args > 16) {
        mp_raise_TypeError(MP_ERROR_TEXT("start() takes 14 to 16 arguments"));
    }
    if (s_active) {
        mp_raise_ValueError(MP_ERROR_TEXT("a core is already running"));
    }

    const char *label = mp_obj_str_get_str(args[0]);
    uint32_t expected_crc = 0;
    if (n_args > 14 && args[14] != mp_const_none) {
        expected_crc = (uint32_t)mp_obj_get_int_truncated(args[14]);
    }
    core_attach(label, (size_t)mp_obj_get_int_truncated(args[1]),
                (size_t)mp_obj_get_int_truncated(args[2]), expected_crc);

    s_width = (int)mp_obj_get_int(args[10]);
    s_height = (int)mp_obj_get_int(args[11]);

    // The surface the core may draw into: an ordinary Python buffer, so the app
    // owns it and the core writes straight into what LVGL displays.
    int band_rows = (int)mp_obj_get_int(args[13]);
    if (band_rows <= 0) {
        band_rows = s_height;
    }
    if (band_rows > s_height) {
        band_rows = s_height;
    }
    s_band_rows = band_rows;
    if (args[12] != mp_const_none) {
        mp_buffer_info_t buf;
        if (!mp_get_buffer(args[12], &buf, MP_BUFFER_WRITE)
                || buf.len < (size_t)s_width * (size_t)s_height * 2u) {
            core_release();
            mp_raise_ValueError(MP_ERROR_TEXT("frame buffer is too small"));
        }
        s_frame = (uint16_t *)buf.buf;
    } else {
        s_frame = NULL;
    }

    s_present_fun = args[3];
    s_palette_fun = args[4];
    s_poll_fun = args[5];
    s_read_fun = args[6];
    s_size_fun = args[7];
    s_log_fun = args[8];
    // Root every callback (and the surface buffer) in one tuple: the statics
    // above are not roots, so the collector would free them mid-run.
    mp_obj_t roots[7];
    for (int i = 0; i < 6; i++) {
        roots[i] = args[3 + i];
    }
    roots[6] = args[12];
    MP_STATE_VM(mpos_core_refs) = mp_obj_new_tuple(7, roots);
    s_now_ms = abi_now_ms(NULL);

    abi_init_common();
    s_abi.present_band = abi_present_band;
    s_abi.palette = abi_palette;
    s_abi.poll_key = abi_poll_key;
    s_abi.read_file = abi_read_file;
    s_abi.file_size = abi_file_size;
    s_abi.log = abi_log;
    s_abi.frame = s_frame;
    // No frame_ready/yield: this mode presents every band as it is finished and
    // has no task of its own to yield from.

    const char *config_dir = NULL;
    if (n_args > 15 && args[15] != mp_const_none) {
        config_dir = mp_obj_str_get_str(args[15]);
    }
    int result = s_entry->init(&s_abi, mp_obj_str_get_str(args[9]), config_dir);
    if (result != 0) {
        s_entry->stop(&s_abi);
        core_release();
        mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("core init failed: %d"), result);
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mpos_core_start_obj, 14, 16, mpos_core_start);

static mp_obj_t mpos_core_tick(mp_obj_t now_obj) {
    if (!s_active || s_entry == NULL) {
        mp_raise_ValueError(MP_ERROR_TEXT("no core is running"));
    }
    if (s_task != NULL) {
        // A worker core advances itself; the frame loop only presents.
        return mp_const_none;
    }
    s_now_ms = (uint32_t)mp_obj_get_int_truncated(now_obj);
    s_entry->tick(&s_abi, s_now_ms);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mpos_core_tick_obj, mpos_core_tick);

// -- worker start ------------------------------------------------------------

// Stop the worker and wait for it to leave the engine. The core's globals live
// in the arena and its code in the mapping, so nothing may be released while
// it is still ticking.
static void stop_task(void) {
    if (s_task == NULL) {
        return;
    }
    s_task_stop = 1;
    // Wake a worker parked in the buffer handshake.
    if (s_present_wake != NULL) {
        xSemaphoreGive(s_present_wake);
    }
    if (xSemaphoreTake(s_task_exit, pdMS_TO_TICKS(3000)) != pdTRUE) {
        // A core that will not return from a tick cannot be left running over
        // memory the host is about to hand back. Killing it leaks whatever it
        // held, which beats the alternative of it executing unmapped code.
        printf("mpos_core: worker did not stop, deleting it\n");
        vTaskDelete(s_task);
    }
    s_task = NULL;
    s_task_stop = 0;
}

static void release_task_memory(void) {
    stop_task();
    for (int i = 0; i < MPOS_CORE_BUFFERS; i++) {
        if (s_buffer_owned[i] && s_buffers[i] != NULL) {
            heap_caps_free(s_buffers[i]);
        }
        s_buffers[i] = NULL;
        s_buffer_owned[i] = 0;
    }
    if (s_present_wake != NULL) {
        vSemaphoreDelete(s_present_wake);
        s_present_wake = NULL;
    }
    if (s_key_code != NULL) {
        heap_caps_free(s_key_code);
        s_key_code = NULL;
    }
    if (s_key_pressed != NULL) {
        heap_caps_free(s_key_pressed);
        s_key_pressed = NULL;
    }
    if (s_log_ring != NULL) {
        heap_caps_free(s_log_ring);
        s_log_ring = NULL;
    }
    if (s_task_ready != NULL) {
        vSemaphoreDelete(s_task_ready);
        s_task_ready = NULL;
    }
    if (s_task_exit != NULL) {
        vSemaphoreDelete(s_task_exit);
        s_task_exit = NULL;
    }
    s_buffer_bytes = 0;
    s_asset_chunk_count = 0;
    s_asset_size = 0;
    s_asset_name[0] = '\0';
    s_wad_path[0] = '\0';
    s_config_dir[0] = '\0';
    s_key_head = 0;
    s_key_tail = 0;
    s_log_head = 0;
    s_log_tail = 0;
    s_log_lost = 0;
    s_published = 0;
    s_presented = 0;
    s_presenting = -1;
    s_presenting_seq = 0;
    s_front_buffer = 0;
    s_back_buffer = 0;
    s_task_result = 0;
    s_task_stop = 0;
}

enum {
    ARG_label,
    ARG_offset,
    ARG_size,
    ARG_width,
    ARG_height,
    ARG_band_rows,
    ARG_stack_bytes,
    ARG_asset,
    ARG_asset_name,
    ARG_wad_path,
    ARG_config_dir,
    ARG_expected_crc,
    ARG_affinity,
    ARG_surface,
};

static const mp_arg_t start_task_args[] = {
    { MP_QSTR_label, MP_ARG_REQUIRED | MP_ARG_OBJ, {.u_rom_obj = MP_ROM_NONE} },
    { MP_QSTR_offset, MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0} },
    { MP_QSTR_size, MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0} },
    { MP_QSTR_width, MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0} },
    { MP_QSTR_height, MP_ARG_REQUIRED | MP_ARG_INT, {.u_int = 0} },
    { MP_QSTR_band_rows, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 0} },
    { MP_QSTR_stack_bytes, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = (int)MPOS_CORE_WORKER_STACK} },
    { MP_QSTR_asset, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_rom_obj = MP_ROM_NONE} },
    { MP_QSTR_asset_name, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_rom_obj = MP_ROM_NONE} },
    { MP_QSTR_wad_path, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_rom_obj = MP_ROM_NONE} },
    { MP_QSTR_config_dir, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_rom_obj = MP_ROM_NONE} },
    { MP_QSTR_expected_crc, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = 0} },
    { MP_QSTR_affinity, MP_ARG_KW_ONLY | MP_ARG_INT, {.u_int = MPOS_CORE_WORKER_CORE} },
    { MP_QSTR_surface, MP_ARG_KW_ONLY | MP_ARG_OBJ, {.u_rom_obj = MP_ROM_NONE} },
};

// Copy a Python string into a fixed buffer; an empty result means "none".
static void copy_path(char *dst, size_t size, mp_obj_t value) {
    dst[0] = '\0';
    if (value == mp_const_none) {
        return;
    }
    const char *text = mp_obj_str_get_str(value);
    size_t len = strlen(text);
    if (len >= size) {
        len = size - 1;
    }
    memcpy(dst, text, len);
    dst[len] = '\0';
}

static mp_obj_t mpos_core_start_task(size_t n_args, const mp_obj_t *pos_args,
                                     mp_map_t *kw_args) {
    mp_arg_val_t parsed[MP_ARRAY_SIZE(start_task_args)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(start_task_args),
                     start_task_args, parsed);

    if (s_active) {
        mp_raise_ValueError(MP_ERROR_TEXT("a core is already running"));
    }

    const char *label = mp_obj_str_get_str(parsed[ARG_label].u_obj);
    core_attach(label, (size_t)parsed[ARG_offset].u_int,
                (size_t)parsed[ARG_size].u_int,
                (uint32_t)parsed[ARG_expected_crc].u_int);

    s_width = parsed[ARG_width].u_int;
    s_height = parsed[ARG_height].u_int;
    if (s_width <= 0 || s_height <= 0) {
        core_release();
        mp_raise_ValueError(MP_ERROR_TEXT("surface size must be positive"));
    }
    int band_rows = parsed[ARG_band_rows].u_int;
    if (band_rows <= 0 || band_rows > s_height) {
        band_rows = s_height;
    }
    s_band_rows = band_rows;

    // A worker core never enters MicroPython, so its input, its log and its
    // asset are all served from C. The rings are small and fixed.
    s_key_code = heap_caps_malloc(MPOS_CORE_KEY_RING, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    s_key_pressed = heap_caps_malloc(MPOS_CORE_KEY_RING, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    s_log_ring = heap_caps_malloc(MPOS_CORE_LOG_LINES * MPOS_CORE_LOG_CHARS,
                                  MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (s_log_ring == NULL) {
        s_log_ring = heap_caps_malloc(MPOS_CORE_LOG_LINES * MPOS_CORE_LOG_CHARS,
                                      MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    }
    if (s_key_code == NULL || s_key_pressed == NULL || s_log_ring == NULL) {
        release_task_memory();
        core_release();
        mp_raise_msg(&mp_type_MemoryError,
                     MP_ERROR_TEXT("no memory for the core's input and log rings"));
    }

    // The asset: the app's buffer (or a list of them, which is how an asset
    // too big for one block is carried), sliced by the loader.
    if (parsed[ARG_asset].u_obj != mp_const_none) {
        size_t chunk_count = 0;
        mp_obj_t *chunks = NULL;
        mp_obj_t asset = parsed[ARG_asset].u_obj;
        if (mp_obj_is_type(asset, &mp_type_list)
                || mp_obj_is_type(asset, &mp_type_tuple)) {
            mp_obj_get_array(asset, &chunk_count, &chunks);
            if (chunk_count == 0 || chunk_count > MPOS_CORE_ASSET_CHUNKS) {
                release_task_memory();
                core_release();
                mp_raise_ValueError(
                    MP_ERROR_TEXT("asset needs 1 to 16 chunk buffers"));
            }
        } else {
            chunk_count = 1;
            chunks = &asset;
        }
        s_asset_size = 0;
        for (size_t i = 0; i < chunk_count; i++) {
            mp_buffer_info_t info;
            if (!mp_get_buffer(chunks[i], &info, MP_BUFFER_READ)) {
                release_task_memory();
                core_release();
                mp_raise_TypeError(MP_ERROR_TEXT("asset must be a buffer"));
            }
            s_asset_chunks[i] = (const uint8_t *)info.buf;
            s_asset_chunk_size[i] = (uint32_t)info.len;
            s_asset_size += (uint32_t)info.len;
        }
        s_asset_chunk_count = (uint32_t)chunk_count;
        copy_path(s_asset_name, sizeof(s_asset_name), parsed[ARG_asset_name].u_obj);
        if (s_asset_name[0] == '\0') {
            release_task_memory();
            core_release();
            mp_raise_ValueError(MP_ERROR_TEXT("an asset needs asset_name"));
        }
    }
    copy_path(s_wad_path, sizeof(s_wad_path), parsed[ARG_wad_path].u_obj);
    copy_path(s_config_dir, sizeof(s_config_dir), parsed[ARG_config_dir].u_obj);

    // Two surfaces. The app's own (the one LVGL shows) is used as buffer 0 when
    // it passes one, so only the second has to be allocated here.
    s_buffer_bytes = (size_t)s_width * (size_t)s_height * 2u;
    for (int i = 0; i < MPOS_CORE_BUFFERS; i++) {
        s_buffers[i] = NULL;
        s_buffer_owned[i] = 0;
    }
    if (parsed[ARG_surface].u_obj != mp_const_none) {
        mp_buffer_info_t info;
        if (!mp_get_buffer(parsed[ARG_surface].u_obj, &info, MP_BUFFER_WRITE)
                || info.len < s_buffer_bytes) {
            release_task_memory();
            core_release();
            mp_raise_ValueError(MP_ERROR_TEXT("frame buffer is too small"));
        }
        s_buffers[0] = (uint16_t *)info.buf;
    }
    for (int i = 0; i < MPOS_CORE_BUFFERS; i++) {
        if (s_buffers[i] != NULL) {
            continue;
        }
        s_buffers[i] = heap_caps_malloc(s_buffer_bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
        if (s_buffers[i] == NULL) {
            s_buffers[i] = heap_caps_malloc(s_buffer_bytes,
                                            MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
        }
        if (s_buffers[i] == NULL) {
            release_task_memory();
            core_release();
            mp_raise_msg_varg(&mp_type_MemoryError,
                              MP_ERROR_TEXT("no memory for a %u byte surface"),
                              (unsigned)s_buffer_bytes);
        }
        s_buffer_owned[i] = 1;
    }

    // Root the asset and the surface: the loader holds raw pointers into both
    // for the whole session, and the collector cannot see those pointers.
    mp_obj_t roots[2];
    roots[0] = parsed[ARG_asset].u_obj;
    roots[1] = parsed[ARG_surface].u_obj;
    MP_STATE_VM(mpos_core_refs) = mp_obj_new_tuple(2, roots);

    s_task_ready = xSemaphoreCreateBinary();
    s_task_exit = xSemaphoreCreateBinary();
    s_present_wake = xSemaphoreCreateBinary();
    if (s_task_ready == NULL || s_task_exit == NULL
            || s_present_wake == NULL) {
        release_task_memory();
        core_release();
        mp_raise_msg(&mp_type_MemoryError,
                     MP_ERROR_TEXT("no memory for the core's hand-off"));
    }

    s_task_stop = 0;
    s_task_result = 0;
    s_published = 0;
    s_presented = 0;
    s_presenting = -1;
    s_presenting_seq = 0;
    s_front_buffer = MPOS_CORE_BUFFERS - 1;
    s_back_buffer = 0;
    s_key_head = 0;
    s_key_tail = 0;
    s_log_head = 0;
    s_log_tail = 0;
    s_log_lost = 0;

    abi_init_common();
    s_abi.present_band = worker_present_band;
    s_abi.palette = worker_palette;
    s_abi.poll_key = worker_poll_key;
    s_abi.read_file = worker_read_file;
    s_abi.file_size = worker_file_size;
    s_abi.log = worker_log;
    s_abi.frame = s_buffers[s_back_buffer];
    s_abi.frame_ready = worker_frame_ready;
    s_abi.yield = abi_yield;

    // Internal RAM first: it is what a task stack has always been, and it is
    // several times faster than PSRAM. A board whose DRAM is fragmented into
    // blocks smaller than the engine's stack cannot give one, though, and the
    // engine's data already lives in PSRAM - a stack there is slower for the
    // hot frames, which beats a game that cannot start at all.
    const uint32_t stack_bytes = (uint32_t)parsed[ARG_stack_bytes].u_int;
    const BaseType_t core_id = (BaseType_t)parsed[ARG_affinity].u_int;
    BaseType_t created = xTaskCreatePinnedToCoreWithCaps(
        core_task_main, "mpos_core", stack_bytes, NULL,
        MPOS_CORE_WORKER_PRIORITY, &s_task, core_id,
        MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    if (created != pdPASS) {
        created = xTaskCreatePinnedToCoreWithCaps(
            core_task_main, "mpos_core", stack_bytes, NULL,
            MPOS_CORE_WORKER_PRIORITY, &s_task, core_id,
            MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
        if (created == pdPASS) {
            char line[96];
            snprintf(line, sizeof(line),
                     "core: no %u KiB internal block, stack in PSRAM",
                     (unsigned)(stack_bytes / 1024));
            log_push(line);
        }
    }
    if (created != pdPASS) {
        s_task = NULL;
        release_task_memory();
        core_release();
        mp_raise_msg(&mp_type_MemoryError,
                     MP_ERROR_TEXT("cannot create the core's task"));
    }

    // Block until the core has finished its start-up (or failed): the caller
    // shows a progress message, and nothing may tick before init returned.
    xSemaphoreTake(s_task_ready, portMAX_DELAY);
    if (s_task_result != 0) {
        int result = s_task_result;
        release_task_memory();
        core_release();
        mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("core init failed: %d"), result);
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_KW(mpos_core_start_task_obj, 3, mpos_core_start_task);

static mp_obj_t mpos_core_stop(void) {
    if (!s_active) {
        return mp_const_none;
    }
    if (s_task != NULL) {
        release_task_memory();
    } else if (s_entry != NULL && s_entry->stop != NULL) {
        s_entry->stop(&s_abi);
    }
    core_release();
    // The engine can be started again after stop() (a game that quits to the
    // launcher and is started again), so leave nothing of this session behind
    // for the next one to read: the surface pointer especially, which points
    // into an activity that is about to be destroyed.
    s_frame = NULL;
    s_width = 0;
    s_height = 0;
    s_band_rows = 0;
    s_flags = 0;
    s_now_ms = 0;
    s_present_fun = MP_OBJ_NULL;
    s_palette_fun = MP_OBJ_NULL;
    s_poll_fun = MP_OBJ_NULL;
    s_read_fun = MP_OBJ_NULL;
    s_size_fun = MP_OBJ_NULL;
    s_log_fun = MP_OBJ_NULL;
    MP_STATE_VM(mpos_core_refs) = MP_OBJ_NULL;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mpos_core_stop_obj, mpos_core_stop);

static mp_obj_t mpos_core_mapped(void) {
    return mp_obj_new_int_from_uint((uintptr_t)s_mapped);
}
static MP_DEFINE_CONST_FUN_OBJ_0(mpos_core_mapped_obj, mpos_core_mapped);

static mp_obj_t mpos_core_mapped_size(void) {
    return mp_obj_new_int_from_uint(s_mapped_size);
}
static MP_DEFINE_CONST_FUN_OBJ_0(mpos_core_mapped_size_obj, mpos_core_mapped_size);

// Free bytes left on the calling task's stack. A core runs on the MicroPython
// task, so this is the record of the deepest Python + engine frame since boot:
// it is how a stack size is chosen instead of guessed.
static mp_obj_t mpos_core_stack_high_water(void) {
    return mp_obj_new_int((mp_int_t)uxTaskGetStackHighWaterMark(NULL)
                          * (mp_int_t)sizeof(StackType_t));
}
static MP_DEFINE_CONST_FUN_OBJ_0(mpos_core_stack_high_water_obj,
                                 mpos_core_stack_high_water);

static mp_obj_t mpos_core_task_frame(void) {
    if (!s_active || s_task == NULL) {
        return mp_const_none;
    }
    int index;
    uint32_t seq;
    portENTER_CRITICAL(&s_ring_lock);
    if (s_presenting < 0 && s_published != s_presented) {
        s_presenting = s_front_buffer;
        s_presenting_seq = s_published;
    }
    index = s_presenting;
    seq = s_presenting_seq;
    portEXIT_CRITICAL(&s_ring_lock);
    if (index < 0) {
        return mp_const_none;
    }
    mp_obj_t items[2];
    items[0] = mp_obj_new_int(index);
    items[1] = mp_obj_new_int_from_uint(seq);
    return mp_obj_new_tuple(2, items);
}
static MP_DEFINE_CONST_FUN_OBJ_0(mpos_core_task_frame_obj, mpos_core_task_frame);

// The frame is on the panel (or has been dropped on purpose): the buffer goes
// back to the engine, which has been waiting for it.
static mp_obj_t mpos_core_task_presented(void) {
    if (!s_active || s_presenting < 0) {
        return mp_const_none;
    }
    int index;
    portENTER_CRITICAL(&s_ring_lock);
    index = s_presenting;
    s_presented = s_presenting_seq;
    s_presenting = -1;
    portEXIT_CRITICAL(&s_ring_lock);
    if (s_present_wake != NULL) {
        xSemaphoreGive(s_present_wake);
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mpos_core_task_presented_obj, mpos_core_task_presented);

// The pixels of one buffer, with no copy: the app wraps it in a display surface
// and LVGL reads it directly.
static mp_obj_t mpos_core_task_surface(mp_obj_t index_obj) {
    if (!s_active || s_task == NULL) {
        mp_raise_ValueError(MP_ERROR_TEXT("no worker core is running"));
    }
    int index = (int)mp_obj_get_int(index_obj);
    if (index < 0 || index >= MPOS_CORE_BUFFERS || s_buffers[index] == NULL) {
        mp_raise_ValueError(MP_ERROR_TEXT("no such surface"));
    }
    return mp_obj_new_bytearray_by_ref(s_buffer_bytes, s_buffers[index]);
}
static MP_DEFINE_CONST_FUN_OBJ_1(mpos_core_task_surface_obj, mpos_core_task_surface);

static mp_obj_t mpos_core_task_log(void) {
    if (s_log_ring == NULL) {
        return mp_const_none;
    }
    char line[MPOS_CORE_LOG_CHARS];
    uint32_t lost = 0;
    int have = 0;
    portENTER_CRITICAL(&s_ring_lock);
    if (s_log_head != s_log_tail) {
        const char *src = s_log_ring
                        + (size_t)(s_log_tail % MPOS_CORE_LOG_LINES) * MPOS_CORE_LOG_CHARS;
        size_t i = 0;
        while (src[i] != '\0' && i + 1 < MPOS_CORE_LOG_CHARS) {
            line[i] = src[i];
            i++;
        }
        line[i] = '\0';
        s_log_tail++;
        have = 1;
    } else {
        lost = s_log_lost;
        s_log_lost = 0;
    }
    portEXIT_CRITICAL(&s_ring_lock);
    if (have) {
        return mp_obj_new_str(line, strlen(line));
    }
    if (lost != 0) {
        char text[48];
        snprintf(text, sizeof(text), "(%u log lines dropped)", (unsigned)lost);
        return mp_obj_new_str(text, strlen(text));
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mpos_core_task_log_obj, mpos_core_task_log);

static mp_obj_t mpos_core_post_key(mp_obj_t code_obj, mp_obj_t pressed_obj) {
    if (s_key_code == NULL) {
        return mp_const_false;
    }
    const uint8_t code = (uint8_t)mp_obj_get_int(code_obj);
    const uint8_t pressed = mp_obj_get_int(pressed_obj) ? 1 : 0;
    int pushed = 0;
    portENTER_CRITICAL(&s_ring_lock);
    if (s_key_head - s_key_tail < MPOS_CORE_KEY_RING) {
        const uint32_t slot = s_key_head % MPOS_CORE_KEY_RING;
        s_key_code[slot] = code;
        s_key_pressed[slot] = pressed;
        s_key_head++;
        pushed = 1;
    }
    portEXIT_CRITICAL(&s_ring_lock);
    return mp_obj_new_bool(pushed);
}
static MP_DEFINE_CONST_FUN_OBJ_2(mpos_core_post_key_obj, mpos_core_post_key);

static mp_obj_t mpos_core_task_running(void) {
    return mp_obj_new_bool(s_task != NULL);
}
static MP_DEFINE_CONST_FUN_OBJ_0(mpos_core_task_running_obj, mpos_core_task_running);

// Free bytes left on the worker's stack: the record of the engine's own deepest
// frame, without the OS's frames mixed into it.
static mp_obj_t mpos_core_task_stack(void) {
    if (s_task == NULL) {
        return mp_obj_new_int(0);
    }
    return mp_obj_new_int((mp_int_t)uxTaskGetStackHighWaterMark(s_task)
                          * (mp_int_t)sizeof(StackType_t));
}
static MP_DEFINE_CONST_FUN_OBJ_0(mpos_core_task_stack_obj, mpos_core_task_stack);

static mp_obj_t mpos_core_audio_mix(mp_obj_t buffer) {
    if (s_entry == NULL || s_entry->audio_mix == NULL) {
        return mp_obj_new_int(0);
    }
    mp_buffer_info_t info;
    mp_get_buffer_raise(buffer, &info, MP_BUFFER_WRITE);
    int frames = (int)(info.len / sizeof(int16_t));
    if (frames <= 0) {
        return mp_obj_new_int(0);
    }
    s_entry->audio_mix((int16_t *)info.buf, frames);
    return mp_obj_new_int(frames);
}
static MP_DEFINE_CONST_FUN_OBJ_1(mpos_core_audio_mix_obj, mpos_core_audio_mix);

static mp_obj_t mpos_core_quit_requested(void) {
    if (s_entry == NULL || s_entry->quit_requested == NULL) {
        return mp_const_false;
    }
    return mp_obj_new_bool(s_entry->quit_requested());
}
static MP_DEFINE_CONST_FUN_OBJ_0(mpos_core_quit_requested_obj,
                                 mpos_core_quit_requested);

static mp_obj_t mpos_core_abi_version(void) {
    return mp_obj_new_int(MPOS_CORE_ABI_VERSION);
}
static MP_DEFINE_CONST_FUN_OBJ_0(mpos_core_abi_version_obj, mpos_core_abi_version);

// -- host buffers ------------------------------------------------------------
//
// A native game's asset (Doom's 1.8 MiB WAD) has to live outside MicroPython's
// GC heap. A Python bytearray of that size forces the split GC heap to add an
// area, and as soon as anything else lives in that area it can never be handed
// back to the IDF heap - while the engine's zone needs one contiguous block
// after the asset is in RAM, so a second launch in the same boot fails.
// A buffer from here is ordinary C memory with an explicit free; the caller
// owns it for exactly as long as its game session needs it.

#define MPOS_CORE_MAX_BUFFERS 4

typedef struct {
    void *ptr;
    size_t size;
} mpos_core_buffer_t;

static mpos_core_buffer_t s_buffers_pool[MPOS_CORE_MAX_BUFFERS];

static mp_obj_t mpos_core_buffer(mp_obj_t size_obj) {
    size_t size = (size_t)mp_obj_get_int_truncated(size_obj);
    if (size == 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("buffer size must be positive"));
    }
    int slot = -1;
    for (int i = 0; i < MPOS_CORE_MAX_BUFFERS; i++) {
        if (s_buffers_pool[i].ptr == NULL) {
            slot = i;
            break;
        }
    }
    if (slot < 0) {
        mp_raise_msg(&mp_type_MemoryError,
                     MP_ERROR_TEXT("too many mpos_core buffers"));
    }
    void *ptr = heap_caps_malloc(size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (ptr == NULL) {
        ptr = heap_caps_malloc(size, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    }
    if (ptr == NULL) {
        mp_raise_msg(&mp_type_MemoryError,
                     MP_ERROR_TEXT("cannot allocate the buffer"));
    }
    s_buffers_pool[slot].ptr = ptr;
    s_buffers_pool[slot].size = size;
    return mp_obj_new_bytearray_by_ref(size, ptr);
}
static MP_DEFINE_CONST_FUN_OBJ_1(mpos_core_buffer_obj, mpos_core_buffer);

static mp_obj_t mpos_core_buffer_free(mp_obj_t buffer) {
    mp_buffer_info_t info;
    mp_get_buffer_raise(buffer, &info, MP_BUFFER_READ);
    for (int i = 0; i < MPOS_CORE_MAX_BUFFERS; i++) {
        if (s_buffers_pool[i].ptr == info.buf) {
            heap_caps_free(s_buffers_pool[i].ptr);
            s_buffers_pool[i].ptr = NULL;
            s_buffers_pool[i].size = 0;
            return mp_const_none;
        }
    }
    mp_raise_ValueError(MP_ERROR_TEXT("not an mpos_core buffer"));
}
static MP_DEFINE_CONST_FUN_OBJ_1(mpos_core_buffer_free_obj, mpos_core_buffer_free);

static const mp_rom_map_elem_t mpos_core_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_mpos_core) },
    { MP_ROM_QSTR(MP_QSTR_start), MP_ROM_PTR(&mpos_core_start_obj) },
    { MP_ROM_QSTR(MP_QSTR_start_task), MP_ROM_PTR(&mpos_core_start_task_obj) },
    { MP_ROM_QSTR(MP_QSTR_tick), MP_ROM_PTR(&mpos_core_tick_obj) },
    { MP_ROM_QSTR(MP_QSTR_stop), MP_ROM_PTR(&mpos_core_stop_obj) },
    { MP_ROM_QSTR(MP_QSTR_mapped), MP_ROM_PTR(&mpos_core_mapped_obj) },
    { MP_ROM_QSTR(MP_QSTR_mapped_size), MP_ROM_PTR(&mpos_core_mapped_size_obj) },
    { MP_ROM_QSTR(MP_QSTR_stack_high_water), MP_ROM_PTR(&mpos_core_stack_high_water_obj) },
    { MP_ROM_QSTR(MP_QSTR_abi_version), MP_ROM_PTR(&mpos_core_abi_version_obj) },
    { MP_ROM_QSTR(MP_QSTR_audio_mix), MP_ROM_PTR(&mpos_core_audio_mix_obj) },
    { MP_ROM_QSTR(MP_QSTR_quit_requested), MP_ROM_PTR(&mpos_core_quit_requested_obj) },
    { MP_ROM_QSTR(MP_QSTR_task_frame), MP_ROM_PTR(&mpos_core_task_frame_obj) },
    { MP_ROM_QSTR(MP_QSTR_task_presented), MP_ROM_PTR(&mpos_core_task_presented_obj) },
    { MP_ROM_QSTR(MP_QSTR_task_surface), MP_ROM_PTR(&mpos_core_task_surface_obj) },
    { MP_ROM_QSTR(MP_QSTR_task_log), MP_ROM_PTR(&mpos_core_task_log_obj) },
    { MP_ROM_QSTR(MP_QSTR_task_running), MP_ROM_PTR(&mpos_core_task_running_obj) },
    { MP_ROM_QSTR(MP_QSTR_task_stack), MP_ROM_PTR(&mpos_core_task_stack_obj) },
    { MP_ROM_QSTR(MP_QSTR_post_key), MP_ROM_PTR(&mpos_core_post_key_obj) },
    { MP_ROM_QSTR(MP_QSTR_buffer), MP_ROM_PTR(&mpos_core_buffer_obj) },
    { MP_ROM_QSTR(MP_QSTR_buffer_free), MP_ROM_PTR(&mpos_core_buffer_free_obj) },
};
static MP_DEFINE_CONST_DICT(mpos_core_module_globals, mpos_core_module_globals_table);

const mp_obj_module_t mpos_core_user_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&mpos_core_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_mpos_core, mpos_core_user_cmodule);
