/*
 * mpos_core ABI — the contract between MicroPythonOS and a loadable native
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
 * Two windows, because the S3 has two
 * -----------------------------------
 * Instruction memory (IROM) is fetched through its own bus and is not
 * data-readable, so a string or table cannot live where the code lives - the
 * host faults with LoadStoreError the moment it reads one. The firmware itself
 * is linked the same way (.flash.text in IROM, .flash.rodata in DROM), and a
 * core does too: `load_addr` is where the blob's text is mapped, `data_addr` is
 * where its read-only data is mapped, and both come from the *same* flash
 * pages (the loader maps the partition twice, INST and DATA). A blob declares
 * both addresses in its entry table, and `data_offset` - a 64 KB boundary in
 * the partition - is where the data region starts.
 *
 * Versioning: abi_version names the newest field a blob knows about. The host
 * accepts blobs from MPOS_CORE_ABI_MIN_VERSION to MPOS_CORE_ABI_VERSION and
 * refuses the rest rather than guessing: a newer blob may call a field this
 * host does not have, and an older one is not worth supporting. Fields are
 * only ever appended to the two structs, which is what makes the range safe.
 *
 * Two ways to run a core
 * ----------------------
 * By default the host calls init() and tick() from the MicroPython task, and
 * the core's callbacks (present, read, poll, log) run there too. That needs
 * one stack for the OS and the engine together.
 *
 * A core with MPOS_CORE_FLAG_WORKER instead gets its own task, created by the
 * loader: init() and tick() run there, in C, and the loader answers every
 * callback the core can make without entering MicroPython. The core renders
 * into a back buffer and calls frame_ready(); the host shows the published
 * frame from its own task. That is how MPOS keeps a small Python stack while
 * a 1990s engine gets the 48 KB it wants, and it also lets the render and the
 * panel transfer run on two cores at once.
 */
#ifndef MPOS_CORE_ABI_H
#define MPOS_CORE_ABI_H

#include <stdint.h>

#define MPOS_CORE_ABI_VERSION 9
/* Oldest entry table this loader still runs. Everything added since is
 * appended to both structs, so a core built against an older header keeps
 * working: it never reads the fields it does not know about. A blob is refused
 * when it is newer than the host, or older than this. */
#define MPOS_CORE_ABI_MIN_VERSION 8

/* Flags for mpos_core_entry_t.flags. */
#define MPOS_CORE_FLAG_FRAMEBUFFER_PALETTED (1u << 0)  /* 8-bit indices */
#define MPOS_CORE_FLAG_FRAMEBUFFER_RGB565   (1u << 1)
/* present_band() carries RGB565 pixels instead of palette indices: the core
 * converted the frame itself, which is the only way to rotate and convert in C
 * rather than in Python. `frame_width`/`frame_height` then describe the
 * surface the host shows, not the engine's own resolution. */
#define MPOS_CORE_FLAG_BAND_RGB565          (1u << 2)
/* present_band() hands over RGB565 rows; the core converts its own palette. */
#define MPOS_CORE_FLAG_WORKER               (1u << 3)
/* The core runs on its own FreeRTOS task (ABI 9), not on the MicroPython one.
 * Everything it can call is then implemented in C by the loader: it never
 * re-enters the interpreter from its task, so the host is free to keep the
 * Python task small. The core must call frame_ready() when a frame is
 * complete; the host presents it from its own task. */

/*
 * Host services, called from core code. `host` is opaque to the core and is
 * passed back unchanged; the loader uses it to find the Python side.
 *
 * present_band(host, band, rows, pixels):
 *     show `rows` rows of the surface starting at row `band`. Two modes:
 *
 *       - pixels != NULL: the core hands over `rows * frame_width` pixels of
 *         the format named by the entry flags, and the host copies them;
 *       - pixels == NULL: the core already drew those rows into `frame` (see
 *         below) and is only announcing them, so the host can flush the band
 *         while the core draws the next one. This is what keeps the panel
 *         transfer and the conversion from adding up.
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
 * now_ms(host): monotonic milliseconds, the same clock the host passes to
 *     tick(). A core uses it to pace itself and to measure its own phases; it
 *     never reads a hardware clock.
 *
 * read_file(host, path, offset, dst, len): returns bytes read, -1 on error.
 *     Hosts may cache the open file; a core must not assume an fd survives.
 *
 * file_size(host, path): length in bytes, or -1 on error. A core's stdio needs
 *     it to seek to the end, which is how the engine measures a WAD.
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
    int (*file_size)(void *host, const char *path);
    void *(*alloc)(void *host, uint32_t bytes);
    void (*dealloc)(void *host, void *ptr);
    void (*log)(void *host, const char *text);

    /* Information for the core, set by the loader before init(). */
    int frame_width;
    int frame_height;
    /*
     * The surface the host shows, `frame_width * frame_height` RGB565 pixels,
     * row-major, or NULL. When it is set a core should draw straight into it
     * (there is no copy and no second buffer) and call present_band with
     * pixels == NULL for each finished band. `band_rows` is how many rows the
     * host can display per band: presenting exactly that many lets the transfer
     * of one band overlap the drawing of the next.
     */
    uint16_t *frame;
    int band_rows;

    /*
     * ABI 9, for a core that runs on its own task (MPOS_CORE_FLAG_WORKER).
     *
     * frame_ready(host):
     *     the frame in `abi->frame` is complete. The host publishes it and
     *     hands back the other buffer: after this call `abi->frame` points at
     *     the buffer to draw the next frame into, and presenting the previous
     *     one happens on the host's own task. A core calls it once per frame
     *     and must not touch the old buffer afterwards. May block, which is
     *     the intended backpressure - a core cannot run more than a frame
     *     ahead of the display. Always NULL in the on-task (ABI 8) mode,
     *     where present_band() presents each band immediately.
     *
     * yield(host):
     *     let other tasks run (the scheduler's idle task feeds the interrupt
     *     watchdog). A core calls this from long non-frame work such as
     *     parsing a table at start-up, and never more than a few times a
     *     second while playing. Replaces the "\x01yield" log sentinel, which
     *     is still honoured for cores built against ABI 8.
     */
    void (*frame_ready)(void *host);
    void (*yield)(void *host);
} mpos_core_abi_t;

/*
 * Entry table. A core blob places this at offset 0 of the partition region it
 * is mapped at, so the loader can find it without symbol lookup. The loader
 * copies the table out through a temporary data mapping before it maps
 * anything, so this struct is never read through the instruction window.
 *
 * init(abi, wad_path, config_dir): return 0 on success; the loader turns a
 *     negative value into an OSError. The ABI pointer stays valid until
 *     stop(). `config_dir` is where the engine writes its configuration and
 *     savegames (absolute), or NULL/"" for the engine's own default.
 * tick(abi, now_ms): run one engine frame; the ABI pointer is passed again so a
 *     core with no writable memory of its own still works.
 * stop(abi): release the core's resources; the partition may then be remapped.
 * audio_mix(dst, frames): mix `frames` mono signed-16-bit samples into `dst`
 *     from whatever the engine is playing right now, advancing its own voice
 *     state. The host pulls this at its output rate and writes the result to
 *     the codec, so the engine never blocks on audio and the host decides when
 *     to feed the DAC. May be NULL for a core with no sound.
 * quit_requested(): non-zero when the engine wants the host to close the
 *     activity - the player chose "quit", or the engine hit a state it cannot
 *     continue from. A core cannot close an app itself, and freezing on the
 *     last frame is worse than leaving: the host decides when (and how) to go.
 *     May be NULL. Cleared by init().
 */
typedef struct mpos_core_entry {
    uint32_t abi_version;
    uint32_t flags;
    /*
     * Where this blob was linked, and therefore where it must be mapped: the
     * code uses absolute addresses within its own image. Must be 64 KB aligned
     * and inside the instruction window (0x42000000..0x44000000 on S3). The
     * loader maps the partition's first `data_offset` bytes there; a blob that
     * is not mapped at its load address faults on the first instruction fetch.
     */
    uint32_t load_addr;
    /*
     * The read-only data window (0 disables it, for a blob that has no rodata).
     * Must be 64 KB aligned and inside the data window (0x3C000000..0x3E000000
     * on S3). The same flash pages are mapped here a second time, as DATA, so
     * the code and the host can read strings and tables.
     */
    uint32_t data_addr;
    /* Offset of the data region in the blob; also the size of the text region.
     * Must be 64 KB aligned (the mapping is page aligned). */
    uint32_t data_offset;
    /* Bytes of read-only data at `data_offset`. Rounded up to a page on map. */
    uint32_t data_size;
    /*
     * Writable memory (0 disables it). The blob's .data/.bss are linked at
     * `arena_addr`, so the host has to hand the core exactly that address: it
     * allocates `arena_size` bytes of page-aligned RAM, zeroes them, and maps
     * them at `arena_addr` in the data window. The pages stay the host's, so
     * they are released when the core stops. `arena_addr` must be 64 KB
     * aligned and inside the data window.
     */
    uint32_t arena_addr;
    uint32_t arena_size;
    int (*init)(const mpos_core_abi_t *abi, const char *wad_path,
                const char *config_dir);
    void (*tick)(const mpos_core_abi_t *abi, uint32_t now_ms);
    void (*stop)(const mpos_core_abi_t *abi);
    void (*audio_mix)(int16_t *dst, int frames);
    int (*quit_requested)(void);
} mpos_core_entry_t;

#endif  /* MPOS_CORE_ABI_H */
