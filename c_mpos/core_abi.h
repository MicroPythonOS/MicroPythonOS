/*
 * mpos_core ABI v1 — the contract between MicroPythonOS and a loadable native
 * core (Doom first, other engines later).
 *
 * Why this exists
 * ---------------
 * A MicroPython native module (natmod) has to fit its code in executable RAM.
 * On ESP32-S3 that is IRAM, and a booted badge leaves only a few KB of it, so
 * an engine like Doom (142 KB of code) cannot be loaded as a natmod even though
 * its data would fit easily. A core instead lives in its own flash partition
 * and is executed from there with esp_partition_mmap(ESP_PARTITION_MMAP_INST):
 * code runs XIP through the instruction cache, like the firmware itself, and
 * neither IRAM nor the Python heap is involved.
 *
 * That has two consequences the ABI is built around:
 *
 *   1. The blob is linked for a *fixed* address and cannot be patched at load
 *      time (flash is read-only), so it cannot reference firmware symbols.
 *      Everything the core needs from the OS is a callback in this struct,
 *      filled by the loader before init().
 *   2. The core is loaded once per sequence of frames, not once per frame: the
 *      host calls tick() and the core drives its own engine, reporting pixels
 *      through present_band().
 *
 * Versioning: abi_version must match exactly; a mismatch is refused rather than
 * guessed at. Bump it whenever a field is added, removed or reordered.
 */
#ifndef MPOS_CORE_ABI_H
#define MPOS_CORE_ABI_H

#include <stdint.h>

#define MPOS_CORE_ABI_VERSION 1

/* Flags for mpos_core_entry_t.flags. */
#define MPOS_CORE_FLAG_FRAMEBUFFER_PALETTED (1u << 0)  /* 8-bit indices */
#define MPOS_CORE_FLAG_FRAMEBUFFER_RGB565   (1u << 1)

/*
 * Host services, called from core code. `host` is opaque to the core and is
 * passed back unchanged; the loader uses it to find the Python side.
 *
 * present_band(host, band, rows, pixels):
 *     show `rows` rows of the core's 8-bit framebuffer starting at `band`, in
 *     framebuffer row-major order. The host converts and flushes; the core must
 *     not touch the panel.
 *
 * palette(host, out, entries):
 *     copy `entries` RGB565 entries of the current palette into `out`.
 *
 * poll_key(host, &pressed):
 *     next Doom-style key code ((pressed << 8) | code is the engine's own
 *     convention; here code and pressed are separate), or -1 when the queue is
 *     empty. The queue is the host's, so the app decides which buttons map to
 *     what.
 *
 * now_ms(host): monotonic milliseconds. The core never reads a clock itself.
 *
 * read_file(host, path, offset, dst, len): returns bytes read, -1 on error.
 *     Hosts may cache the open file; a core must not assume an fd survives.
 *
 * alloc/dealloc: memory for the engine's own arena (the zone). May return NULL.
 *
 * log(host, text): diagnostics to the console. Never called per frame.
 */
typedef struct mpos_core_abi {
    uint32_t version;
    void *host;

    void (*present_band)(void *host, int band, int rows, const uint8_t *pixels);
    void (*palette)(void *host, uint16_t *out, int entries);
    int (*poll_key)(void *host, int *pressed);
    uint32_t (*now_ms)(void *host);
    int (*read_file)(void *host, const char *path, uint32_t offset,
                     void *dst, uint32_t len);
    void *(*alloc)(void *host, uint32_t bytes);
    void (*dealloc)(void *host, void *ptr);
    void (*log)(void *host, const char *text);

    /* Information for the core, set by the loader before init(). */
    int frame_width;
    int frame_height;
} mpos_core_abi_t;

/*
 * Entry table. A core blob places this at offset 0 of the partition region it
 * is mapped at, so the loader can find it without symbol lookup.
 *
 * init(abi, wad_path): return 0 on success; the loader turns a negative value
 *     into an OSError. The ABI pointer stays valid until stop().
 * tick(abi, now_ms): run one engine frame; the ABI pointer is passed again so a
 *     core with no writable memory of its own still works.
 * stop(abi): release the core's resources; the partition may then be remapped.
 */
typedef struct mpos_core_entry {
    uint32_t abi_version;
    uint32_t flags;
    /*
     * Where this blob was linked, and therefore where it must be mapped: the
     * code uses absolute addresses within its own image. Must be 64 KB aligned
     * and inside the instruction window (0x42000000..0x44000000 on S3). The
     * loader maps the partition's flash pages there; a blob that is not mapped
     * at its load address faults on the first instruction fetch.
     */
    uint32_t load_addr;
    int (*init)(const mpos_core_abi_t *abi, const char *wad_path);
    void (*tick)(const mpos_core_abi_t *abi, uint32_t now_ms);
    void (*stop)(const mpos_core_abi_t *abi);
} mpos_core_entry_t;

#endif  /* MPOS_CORE_ABI_H */
