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

// No rodata handed back to the host in this test: a blob's strings live in the
// instruction window, which the data bus cannot read (the loader maps the blob
// as INST at its load address). Passing a rodata pointer to a host callback
// makes the host load it as data and fault. The engine layout fixes that by
// putting rodata in the data window; this core avoids the question so the mmap
// + ABI + trampoline path can be proven on its own.
static int core_init(const mpos_core_abi_t *abi, const char *wad_path) {
    (void)wad_path;
    if (abi->version != MPOS_CORE_ABI_VERSION) {
        return -1;
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
    (void)abi;
}

// At offset 0 of the blob: the loader reads this before anything else.
// Must match the address in core.ld; the loader maps the blob there and the
// blob's absolute jumps only resolve at that address.
#define HELLO_CORE_LOAD_ADDR 0x43000000u

__attribute__((section(".core_entry")))
const mpos_core_entry_t mpos_core_entry = {
    .abi_version = MPOS_CORE_ABI_VERSION,
    .flags = MPOS_CORE_FLAG_FRAMEBUFFER_PALETTED,
    .load_addr = HELLO_CORE_LOAD_ADDR,
    .init = core_init,
    .tick = core_tick,
    .stop = core_stop,
};
