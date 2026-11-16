// hello_core - proves the mpos_core contract before a real engine uses it.
//
// It exercises all three kinds of memory a core needs: code fetched from the
// instruction window, strings read from the data window (IROM cannot be read as
// data), and writable state in the RAM arena the host maps at a fixed address.
// It paints colour bars with a marker that moves with the clock, one row at a
// time, and logs through the ABI on the way in and out.
//
// If this draws on the panel and its log lines arrive intact, then the fixed
// address link, the two flash mappings, the arena, the ABI trampolines and the
// band presentation all work together.

#include "../../core_abi.h"

// The log message lives in .rodata, which the linker script puts in the data
// window: the host is handed a pointer to it and reads it as ordinary memory.
static const char CORE_STARTED[] = "hello_core: init (rodata readable)";
static const char CORE_STOPPED[] = "hello_core: stop";
static const char CORE_NO_ZERO[] = "hello_core: arena is not zeroed";
static const char CORE_MEMORY_OK[] = "hello_core: arena keeps state";

// Writable state: this is .bss, linked at core_arena_addr and mapped there by
// the loader. Nothing initialises these at load time beyond the zero fill the
// host does, which is what C expects of .bss.
static uint32_t core_ticks;
static uint8_t core_seen[1024];

static int core_init(const mpos_core_abi_t *abi, const char *wad_path) {
    if (abi->version != MPOS_CORE_ABI_VERSION) {
        return -1;
    }
    if (core_seen[0] != 0 || core_ticks != 0) {
        abi->log(abi->host, CORE_NO_ZERO);
        return -1;
    }
    abi->log(abi->host, CORE_STARTED);
    if (wad_path != 0 && wad_path[0] != 0) {
        abi->log(abi->host, wad_path);
    }
    return 0;
}

static void core_tick(const mpos_core_abi_t *abi, uint32_t now_ms) {
    // State has to survive between frames: this is the arena working.
    core_ticks++;
    core_seen[core_ticks & 1023] = (uint8_t)core_ticks;
    if (core_ticks == 3 && core_seen[3] == 3) {
        abi->log(abi->host, CORE_MEMORY_OK);
    }

    const int width = abi->frame_width;
    const int height = abi->frame_height;
    if (width <= 0 || height <= 0 || width > 320) {
        return;
    }

    uint8_t row[320];
    const int bar_width = width / 8;
    const int marker = (int)((now_ms / 10) % (uint32_t)width);
    const int marker_y = (int)((now_ms / 20) % (uint32_t)height);

    for (int y = 0; y < height; y++) {
        for (int x = 0; x < width; x++) {
            int bar = x / (bar_width > 0 ? bar_width : 1);
            row[x] = (uint8_t)(16 + bar * 16);
        }
        if (y == marker_y) {
            row[marker] = 255;
            if (marker + 1 < width) {
                row[marker + 1] = 255;
            }
        }
        abi->present_band(abi->host, y, 1, row);
    }
}

static void core_stop(const mpos_core_abi_t *abi) {
    abi->log(abi->host, CORE_STOPPED);
}

// At offset 0 of the blob: the loader reads this through a temporary data
// mapping before it maps anything. These addresses must match core.ld: the
// loader maps the text at load_addr and the data at data_addr, and the blob's
// absolute jumps and string pointers only resolve there.
#define HELLO_CORE_TEXT_ADDR 0x43000000u
#define HELLO_CORE_DATA_ADDR 0x3DF00000u
#define HELLO_CORE_DATA_OFFSET 0x10000u
#define HELLO_CORE_ARENA_ADDR 0x3DC00000u
#define HELLO_CORE_ARENA_SIZE 0x20000u

__attribute__((section(".core_entry")))
const mpos_core_entry_t mpos_core_entry = {
    .abi_version = MPOS_CORE_ABI_VERSION,
    .flags = MPOS_CORE_FLAG_FRAMEBUFFER_PALETTED,
    .load_addr = HELLO_CORE_TEXT_ADDR,
    .data_addr = HELLO_CORE_DATA_ADDR,
    .data_offset = HELLO_CORE_DATA_OFFSET,
    .data_size = 0,  // the rest of the blob
    .arena_addr = HELLO_CORE_ARENA_ADDR,
    .arena_size = HELLO_CORE_ARENA_SIZE,
    .init = core_init,
    .tick = core_tick,
    .stop = core_stop,
};
