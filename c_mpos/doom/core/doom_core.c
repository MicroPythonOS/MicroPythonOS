// Doom as a flash-resident core (see c_mpos/core_abi.h).
//
// This is the same engine as the native-module port, but with the platform
// layer written against the core ABI instead of MicroPython's runtime: the
// engine runs from the retro-core partition, its read-only data is mapped in
// the data window, its globals live in the host's arena, and everything it
// needs from the OS (console, files, memory, input) is an ABI callback.
//
// The frame path is the part that differs most from the natmod: the engine
// keeps 320x200 palette indices, and this file converts each finished frame to
// RGB565 *and rotates it* into the surface the host shows (200x320, which fits
// the portrait panel). The host then only has to copy the bands into its
// framebuffer, so no per-pixel work is left to Python.

#include <stddef.h>
#include <stdint.h>

#include "doomdef.h"
#include "doomgeneric.h"
#include "doomkeys.h"
#include "i_video.h"
#include "doomstat.h"

#include "doom_data_init.h"

#include "../../core_abi.h"
#include "core_console.h"
#include "core_libc.h"

// Where the blob is linked (must match doom_core.ld, which also states them in
// the entry table below).
#define DOOM_CORE_TEXT_ADDR 0x43000000u
#define DOOM_CORE_DATA_ADDR 0x3DF00000u
#define DOOM_CORE_ARENA_ADDR 0x3DC00000u
#define DOOM_CORE_ARENA_SIZE 0x80000u

// Rows of the host surface presented per callback: one callback per band keeps
// the host's copies big and the call overhead small.
#define PRESENT_BAND_ROWS 40

#define MAX_KEYS 64

static const mpos_core_abi_t *s_abi;

static uint32_t s_now_ms;
static uint32_t s_start_ms;
static int s_have_start;
static int s_created;
static int s_frame_ready;
static int s_stopped;

static uint16_t s_keys[MAX_KEYS];
static int s_key_head;
static int s_key_tail;

static uint16_t s_palette[256];
static uint16_t s_surface[DOOMGENERIC_RESY * DOOMGENERIC_RESX];  // rotated, RGB565
// One 32x32 tile of the transpose. Static, not on the stack: the task stack is
// a few KB and the engine is already deep inside it when a frame is presented.
static uint16_t s_tile[32][32];

static char s_wad_path[128];
static char s_zone_buf[8];
static char *s_argv[8];

// -- console -----------------------------------------------------------------

// printf() output arrives one character at a time from mpos_printf.c; lines are
// handed to the host's log, which is what keeps this out of the engine's
// performance path.
void mpos_core_console_write(void *data, const char *str, size_t len) {
    (void)data;
    static char line[200];
    static size_t used;
    for (size_t i = 0; i < len; i++) {
        const char c = str[i];
        if (c == '\r') {
            continue;
        }
        if (c == '\n' || used + 1 >= sizeof(line)) {
            line[used] = '\0';
            if (used > 0 && s_abi != NULL) {
                s_abi->log(s_abi->host, line);
            }
            used = 0;
            if (c == '\n') {
                continue;
            }
        }
        line[used++] = c;
    }
}

const mp_print_t mp_plat_print = { mpos_core_console_write, NULL };

// -- doomgeneric platform layer ----------------------------------------------

void DG_Init(void) {
    // doomgeneric allocates four bytes per pixel before calling us; with an
    // 8-bit pixel_t that is four times too much, so take it back and keep one
    // byte per pixel.
    if (DG_ScreenBuffer != NULL) {
        free(DG_ScreenBuffer);
    }
    DG_ScreenBuffer = malloc((size_t)DOOMGENERIC_RESX * DOOMGENERIC_RESY);
}

void DG_DrawFrame(void) {
    s_frame_ready = 1;
}

void DG_SleepMs(uint32_t ms) {
    // The host drives time; this only keeps TryRunTics from spinning.
    s_now_ms += ms;
}

uint32_t DG_GetTicksMs(void) {
    return s_now_ms - s_start_ms;
}

int DG_GetKey(int *pressed, unsigned char *key) {
    if (s_key_tail == s_key_head) {
        return 0;
    }
    const uint16_t event = s_keys[s_key_tail];
    s_key_tail = (s_key_tail + 1) % MAX_KEYS;
    *pressed = event >> 8;
    *key = (unsigned char)(event & 0xFF);
    return 1;
}

void DG_SetWindowTitle(const char *title) {
    (void)title;
}

// -- frame presentation ------------------------------------------------------

static uint16_t rgb565(int r, int g, int b) {
    return (uint16_t)(((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3));
}

// Rotate the engine's 320x200 frame into the 200x320 surface the panel shows.
// The device is used lying on its long side, so the portrait panel displays the
// landscape picture upright; DOOM_CORE_ROTATE_CCW selects the direction.
static void build_surface(const mpos_core_abi_t *abi) {
    const uint8_t *src = (const uint8_t *)DG_ScreenBuffer;
    const int src_w = DOOMGENERIC_RESX;
    const int src_h = DOOMGENERIC_RESY;
    const int out_w = abi->frame_width;
    const int out_h = abi->frame_height;
    if (out_w != src_h || out_h != src_w) {
        // Not the rotated surface we expect: just letterbox what we can.
        const int rows = out_h < src_h ? out_h : src_h;
        const int cols = out_w < src_w ? out_w : src_w;
        for (int y = 0; y < rows; y++) {
            for (int x = 0; x < cols; x++) {
                s_surface[y * out_w + x] = s_palette[src[y * src_w + x]];
            }
        }
        return;
    }

    // Transpose in tiles, not pixel by pixel: an output row is a source
    // *column*, so the naive loop reads one byte per 320-byte stride and the
    // cache thrashes (measured: the whole frame took ~40ms that way). A 32x32
    // tile keeps both the reads and the writes contiguous.
    for (int dy0 = 0; dy0 < out_h; dy0 += 32) {
        const int rows = (out_h - dy0) < 32 ? (out_h - dy0) : 32;
        for (int dx0 = 0; dx0 < out_w; dx0 += 32) {
            const int cols = (out_w - dx0) < 32 ? (out_w - dx0) : 32;
            for (int sy = 0; sy < cols; sy++) {
                const int sx = src_w - 1 - (dy0 + rows - 1);
                const uint8_t *src_row = src + (dx0 + sy) * src_w + sx;
                for (int ry = 0; ry < rows; ry++) {
                    s_tile[ry][sy] = s_palette[src_row[rows - 1 - ry]];
                }
            }
            for (int ry = 0; ry < rows; ry++) {
                uint16_t *row = &s_surface[(dy0 + ry) * out_w + dx0];
                for (int sy = 0; sy < cols; sy++) {
                    row[sy] = s_tile[ry][sy];
                }
            }
        }
    }
}

static void present_frame(const mpos_core_abi_t *abi) {
    if (DG_ScreenBuffer == NULL) {
        return;
    }
    for (int i = 0; i < 256; i++) {
        s_palette[i] = rgb565((int)colors[i].r, (int)colors[i].g,
                              (int)colors[i].b);
    }
    palette_changed = false;
    build_surface(abi);

    const int height = abi->frame_height;
    for (int y = 0; y < height; y += PRESENT_BAND_ROWS) {
        int rows = height - y;
        if (rows > PRESENT_BAND_ROWS) {
            rows = PRESENT_BAND_ROWS;
        }
        abi->present_band(abi->host, y, rows,
                          (const uint8_t *)&s_surface[y * abi->frame_width]);
    }
}

// -- core entry points -------------------------------------------------------

static int core_init(const mpos_core_abi_t *abi, const char *wad_path) {
    mpos_libc_init(abi);
    s_abi = abi;
    if (wad_path == NULL || wad_path[0] == '\0') {
        return -1;
    }
    size_t len = strlen(wad_path);
    if (len >= sizeof(s_wad_path)) {
        return -1;
    }
    memcpy(s_wad_path, wad_path, len + 1);

    s_argv[0] = "doom";
    s_argv[1] = "-iwad";
    s_argv[2] = s_wad_path;
    s_argv[3] = "-mb";
    s_argv[4] = s_zone_buf;
    s_argv[5] = "-nosound";
    s_argv[6] = NULL;
    s_argv[4][0] = '3';  // megabytes of zone: the rest of PSRAM stays with the OS
    s_argv[4][1] = '\0';

    s_now_ms = 0;
    s_start_ms = 0;
    s_have_start = 0;
    s_key_head = 0;
    s_key_tail = 0;
    s_frame_ready = 0;

    // The dataless build moves every initialised global into code; this copies
    // them into the arena before the engine reads anything.
    doom_init_all_data();
    doomgeneric_Create(6, s_argv);
    s_created = 1;
    return 0;
}

static void core_tick(const mpos_core_abi_t *abi, uint32_t now_ms) {
    if (!s_created || s_stopped || mpos_libc_exit_requested()) {
        return;
    }
    if (!s_have_start) {
        s_start_ms = now_ms;
        s_have_start = 1;
    }
    s_now_ms = now_ms;

    int pressed = 0;
    int code = abi->poll_key(abi->host, &pressed);
    while (code >= 0) {
        const int next = (s_key_head + 1) % MAX_KEYS;
        if (next != s_key_tail) {
            s_keys[s_key_head] = (uint16_t)((pressed ? 0x100 : 0) | (code & 0xFF));
            s_key_head = next;
        }
        code = abi->poll_key(abi->host, &pressed);
    }

    doomgeneric_Tick();

    if (s_frame_ready) {
        s_frame_ready = 0;
        present_frame(abi);
    }
}

static void core_stop(const mpos_core_abi_t *abi) {
    (void)abi;
    s_stopped = 1;
    s_created = 0;
}

__attribute__((section(".core_entry")))
const mpos_core_entry_t mpos_core_entry = {
    .abi_version = MPOS_CORE_ABI_VERSION,
    .flags = MPOS_CORE_FLAG_BAND_RGB565,
    .load_addr = DOOM_CORE_TEXT_ADDR,
    .data_addr = DOOM_CORE_DATA_ADDR,
    .data_offset = 0,  // patched by build_doom_core.sh from the linked sections
    .data_size = 0,
    .arena_addr = DOOM_CORE_ARENA_ADDR,
    .arena_size = DOOM_CORE_ARENA_SIZE,
    .init = core_init,
    .tick = core_tick,
    .stop = core_stop,
};
