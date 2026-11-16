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
//                     read_file, alloc, log, wad_path, width, height)
//     mpos_core.tick(now_ms)
//     mpos_core.stop()
//     mpos_core.abi_version
//
// The blob's first bytes are a mpos_core_entry_t whose abi_version must match.

#include "py/runtime.h"
#include "py/obj.h"
#include "py/objarray.h"
#include "py/mphal.h"

#include "esp_partition.h"
#include "esp_mmu_map.h"
#include "hal/mmu_hal.h"
#include "hal/mmu_types.h"
#include "soc/soc_caps.h"

#include "../core_abi.h"

// The instruction window the MMU can serve (IBUS). A core must live inside it.
#define MPOS_CORE_VADDR_MIN 0x42000000u
#define MPOS_CORE_VADDR_MAX 0x44000000u

// -- state -------------------------------------------------------------------

static const esp_partition_t *s_partition;
static const mpos_core_entry_t *s_entry;
static void *s_mapped;
static size_t s_mapped_size;
static uint32_t s_now_ms;
static int s_width;
static int s_height;
static int s_active;

static mp_obj_t s_present_fun;
static mp_obj_t s_palette_fun;
static mp_obj_t s_poll_fun;
static mp_obj_t s_read_fun;
static mp_obj_t s_alloc_fun;
static mp_obj_t s_log_fun;

// Allocations handed to the core are kept alive until the core stops: the core
// holds raw pointers, so the bytearray behind each one must not be collected.
static mp_obj_t s_allocations;

static mpos_core_abi_t s_abi;

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
static esp_err_t map_fixed(uint32_t paddr, uint32_t vaddr, uint32_t size) {
    if ((paddr % CONFIG_MMU_PAGE_SIZE) != 0 || (vaddr % CONFIG_MMU_PAGE_SIZE) != 0) {
        return ESP_ERR_INVALID_ARG;
    }
    if (vaddr + size > MPOS_CORE_VADDR_MAX) {
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
    return (mapped >= map_size) ? ESP_OK : ESP_ERR_INVALID_SIZE;
}

static void unmap_fixed(uint32_t vaddr, uint32_t size) {
    size_t map_size = (size + CONFIG_MMU_PAGE_SIZE - 1) & ~(size_t)(CONFIG_MMU_PAGE_SIZE - 1);
    mmu_hal_unmap_region(0, vaddr, map_size);
}

// -- ABI trampolines (host side) ---------------------------------------------

static void abi_present_band(void *host, int band, int rows, const uint8_t *pixels) {
    (void)host;
    if (s_present_fun == MP_OBJ_NULL) {
        return;
    }
    mp_obj_t args[3];
    args[0] = mp_obj_new_int(band);
    args[1] = mp_obj_new_int(rows);
    args[2] = mp_obj_new_bytearray_by_ref((size_t)rows * (size_t)s_width,
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
    return s_now_ms;
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

static void *abi_alloc(void *host, uint32_t bytes) {
    (void)host;
    if (s_alloc_fun == MP_OBJ_NULL) {
        return NULL;
    }
    mp_obj_t result = mp_call_function_1(s_alloc_fun, mp_obj_new_int_from_uint(bytes));
    mp_buffer_info_t buf;
    if (!mp_get_buffer(result, &buf, MP_BUFFER_RW) || buf.len < bytes) {
        return NULL;
    }
    mp_obj_list_append(s_allocations, result);
    return buf.buf;
}

static void abi_dealloc(void *host, void *ptr) {
    (void)host;
    (void)ptr;  // released when the core stops
}

static void abi_log(void *host, const char *text) {
    (void)host;
    if (s_log_fun == MP_OBJ_NULL) {
        return;
    }
    mp_call_function_1(s_log_fun, mp_obj_new_str(text, strlen(text)));
}

// -- module functions --------------------------------------------------------

static mp_obj_t mpos_core_start(size_t n_args, const mp_obj_t *args) {
    // start(label, offset, size, present_band, palette, poll_key, read_file,
    //       alloc, log, wad_path, width, height)
    if (n_args != 12) {
        mp_raise_TypeError(MP_ERROR_TEXT("start() takes 12 arguments"));
    }
    if (s_active) {
        mp_raise_ValueError(MP_ERROR_TEXT("a core is already running"));
    }

    const char *label = mp_obj_str_get_str(args[0]);
    size_t offset = (size_t)mp_obj_get_int_truncated(args[1]);
    size_t size = (size_t)mp_obj_get_int_truncated(args[2]);

    const esp_partition_t *partition =
        esp_partition_find_first(ESP_PARTITION_TYPE_APP, ESP_PARTITION_SUBTYPE_ANY, label);
    if (partition == NULL) {
        partition = esp_partition_find_first(ESP_PARTITION_TYPE_DATA,
                                             ESP_PARTITION_SUBTYPE_ANY, label);
    }
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
    const mpos_core_entry_t *probe = (const mpos_core_entry_t *)tmp;
    if (probe->abi_version != MPOS_CORE_ABI_VERSION || probe->init == NULL) {
        esp_partition_munmap(tmp_handle);
        mp_raise_msg_varg(&mp_type_ValueError,
                          MP_ERROR_TEXT("core ABI %u, expected %u"),
                          (unsigned)probe->abi_version,
                          (unsigned)MPOS_CORE_ABI_VERSION);
    }
    const uint32_t load_addr = probe->load_addr;
    esp_partition_munmap(tmp_handle);

    if (load_addr < MPOS_CORE_VADDR_MIN || (load_addr % CONFIG_MMU_PAGE_SIZE) != 0) {
        mp_raise_msg_varg(&mp_type_ValueError,
                          MP_ERROR_TEXT("core load address 0x%x is not usable"),
                          (unsigned)load_addr);
    }

    // Map the blob at its linked address: this is the whole point, the code is
    // executed from flash through the cache, with no IRAM and no heap involved.
    err = map_fixed((uint32_t)partition->address + (uint32_t)offset, load_addr,
                    (uint32_t)size);
    if (err != ESP_OK) {
        mp_raise_msg_varg(&mp_type_OSError,
                          MP_ERROR_TEXT("core map at 0x%x failed: %d"),
                          (unsigned)load_addr, (int)err);
    }

    const void *mapped = (const void *)load_addr;
    const mpos_core_entry_t *entry = (const mpos_core_entry_t *)mapped;

    s_partition = partition;
    s_mapped = (void *)mapped;
    s_mapped_size = size;
    s_entry = entry;
    s_width = (int)mp_obj_get_int(args[10]);
    s_height = (int)mp_obj_get_int(args[11]);

    s_present_fun = args[3];
    s_palette_fun = args[4];
    s_poll_fun = args[5];
    s_read_fun = args[6];
    s_alloc_fun = args[7];
    s_log_fun = args[8];
    s_allocations = mp_obj_new_list(0, NULL);
    s_now_ms = mp_hal_ticks_ms();
    s_active = 1;

    s_abi.version = MPOS_CORE_ABI_VERSION;
    s_abi.host = NULL;
    s_abi.present_band = abi_present_band;
    s_abi.palette = abi_palette;
    s_abi.poll_key = abi_poll_key;
    s_abi.now_ms = abi_now_ms;
    s_abi.read_file = abi_read_file;
    s_abi.alloc = abi_alloc;
    s_abi.dealloc = abi_dealloc;
    s_abi.log = abi_log;
    s_abi.frame_width = s_width;
    s_abi.frame_height = s_height;

    int result = s_entry->init(&s_abi, mp_obj_str_get_str(args[9]));
    if (result != 0) {
        s_entry->stop(&s_abi);
        unmap_fixed((uint32_t)s_mapped, (uint32_t)s_mapped_size);
        s_active = 0;
        s_entry = NULL;
        mp_raise_msg_varg(&mp_type_OSError, MP_ERROR_TEXT("core init failed: %d"), result);
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mpos_core_start_obj, 12, 12, mpos_core_start);

static mp_obj_t mpos_core_tick(mp_obj_t now_obj) {
    if (!s_active || s_entry == NULL) {
        mp_raise_ValueError(MP_ERROR_TEXT("no core is running"));
    }
    s_now_ms = (uint32_t)mp_obj_get_int_truncated(now_obj);
    s_entry->tick(&s_abi, s_now_ms);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mpos_core_tick_obj, mpos_core_tick);

static mp_obj_t mpos_core_stop(void) {
    if (!s_active) {
        return mp_const_none;
    }
    if (s_entry != NULL && s_entry->stop != NULL) {
        s_entry->stop(&s_abi);
    }
    unmap_fixed((uint32_t)s_mapped, (uint32_t)s_mapped_size);
    s_entry = NULL;
    s_mapped = NULL;
    s_mapped_size = 0;
    s_present_fun = MP_OBJ_NULL;
    s_palette_fun = MP_OBJ_NULL;
    s_poll_fun = MP_OBJ_NULL;
    s_read_fun = MP_OBJ_NULL;
    s_alloc_fun = MP_OBJ_NULL;
    s_log_fun = MP_OBJ_NULL;
    s_allocations = MP_OBJ_NULL;
    s_active = 0;
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

static mp_obj_t mpos_core_abi_version(void) {
    return mp_obj_new_int(MPOS_CORE_ABI_VERSION);
}
static MP_DEFINE_CONST_FUN_OBJ_0(mpos_core_abi_version_obj, mpos_core_abi_version);

static const mp_rom_map_elem_t mpos_core_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_mpos_core) },
    { MP_ROM_QSTR(MP_QSTR_start), MP_ROM_PTR(&mpos_core_start_obj) },
    { MP_ROM_QSTR(MP_QSTR_tick), MP_ROM_PTR(&mpos_core_tick_obj) },
    { MP_ROM_QSTR(MP_QSTR_stop), MP_ROM_PTR(&mpos_core_stop_obj) },
    { MP_ROM_QSTR(MP_QSTR_mapped), MP_ROM_PTR(&mpos_core_mapped_obj) },
    { MP_ROM_QSTR(MP_QSTR_mapped_size), MP_ROM_PTR(&mpos_core_mapped_size_obj) },
    { MP_ROM_QSTR(MP_QSTR_abi_version), MP_ROM_PTR(&mpos_core_abi_version_obj) },
};
static MP_DEFINE_CONST_DICT(mpos_core_module_globals, mpos_core_module_globals_table);

const mp_obj_module_t mpos_core_user_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&mpos_core_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_mpos_core, mpos_core_user_cmodule);
