// hello_core - proves the mpos_core contract before a real engine uses it.
//
// Deliberately stateless: no .data, no .bss, so it can be linked at a fixed
// flash address and mapped executable without any writable arena. It paints
// colour bars with a marker that moves with the clock, one row at a time, and
// logs through the ABI on the way in and out.
//
// If this draws on the panel, then mmap-as-instruction-memory, the fixed-address
// link, the ABI trampolines and the band presentation all work together.

#include "../../core_abi.h"

static int core_init(const mpos_core_abi_t *abi, const char *wad_path) {
    if (abi->version != MPOS_CORE_ABI_VERSION) {
        return -1;
    }
    abi->log(abi->host, "hello_core: init");
    if (wad_path != 0 && wad_path[0] != 0) {
        abi->log(abi->host, wad_path);
    }
    return 0;
}

static void core_tick(const mpos_core_abi_t *abi, uint32_t now_ms) {
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
    abi->log(abi->host, "hello_core: stop");
}

// At offset 0 of the blob: the loader reads this before anything else.
__attribute__((section(".core_entry")))
const mpos_core_entry_t mpos_core_entry = {
    .abi_version = MPOS_CORE_ABI_VERSION,
    .flags = MPOS_CORE_FLAG_FRAMEBUFFER_PALETTED,
    .init = core_init,
    .tick = core_tick,
    .stop = core_stop,
};
