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
#include "d_main.h"
#include "m_config.h"
#include "m_menu.h"



#include "doom_data_init.h"

// Declared inside m_menu.c, not in its header.
void M_ClearMenus(void);

#include "mpos_engine.h"

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
static uint32_t s_profile_frames;
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
// Source column for each column of a scaled surface. A downscale only ever
// samples fewer columns, so one entry per source column is enough.
static uint16_t s_xmap[DOOMGENERIC_RESX];

static char s_wad_path[128];
static char s_config_dir[128];
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

// Rotate the engine's 320x200 frame into the surface the panel shows, one band
// at a time. dst(dx, dy) = src(dy, src_h - 1 - dx): the engine's x axis runs
// down the panel and its y axis left to right, which is what puts the picture
// upright when the device lies on its long side.
//
// The transpose is tiled because an output row is a source *column*: pixel by
// pixel, every read is a 320-byte stride apart and the cache thrashes. A 32x32
// tile keeps the reads and the writes contiguous.
static void convert_band(const mpos_core_abi_t *abi, uint16_t *dst,
                         int dst_y0, int rows) {
    const uint8_t *src = (const uint8_t *)DG_ScreenBuffer;
    const int src_w = DOOMGENERIC_RESX;
    const int src_h = DOOMGENERIC_RESY;
    const int out_w = abi->frame_width;

    for (int ty = 0; ty < rows; ty += 32) {
        const int tile_rows = (rows - ty) < 32 ? (rows - ty) : 32;
        const int dy0 = dst_y0 + ty;
        for (int dx0 = 0; dx0 < out_w; dx0 += 32) {
            const int cols = (out_w - dx0) < 32 ? (out_w - dx0) : 32;
            for (int c = 0; c < cols; c++) {
                const int sy = src_h - 1 - (dx0 + c);
                const uint8_t *src_row = src + sy * src_w + dy0;
                for (int r = 0; r < tile_rows; r++) {
                    s_tile[r][c] = s_palette[src_row[r]];
                }
            }
            for (int r = 0; r < tile_rows; r++) {
                uint16_t *row = dst + (dy0 + r) * out_w + dx0;
                for (int c = 0; c < cols; c++) {
                    row[c] = s_tile[r][c];
                }
            }
        }
    }
}

// A landscape panel takes the frame as it is: dst(x, y) = src(x, y). No
// transpose and no palette indirection beyond the lookup, so this is the
// cheaper of the two paths.
static void convert_band_direct(const mpos_core_abi_t *abi, uint16_t *dst,
                                int dst_y0, int rows) {
    const uint8_t *src = (const uint8_t *)DG_ScreenBuffer;
    const int out_w = abi->frame_width;
    for (int y = dst_y0; y < dst_y0 + rows; y++) {
        const uint8_t *src_row = src + y * DOOMGENERIC_RESX;
        uint16_t *dst_row = dst + y * out_w;
        for (int x = 0; x < DOOMGENERIC_RESX; x++) {
            dst_row[x] = s_palette[src_row[x]];
        }
    }
}

// A surface smaller than the frame is the same landscape picture at a scale
// that keeps its 4:3 shape (240x150 for a 240x240 panel). Nearest neighbour:
// panel pixel (x, y) shows source pixel (round(x * 320 / out_w), round(y * 200
// / out_h)). The rounding matches NativeActivity's touch mapping, so a finger
// lands on the pixel it is over.
static void convert_band_scaled(const mpos_core_abi_t *abi, uint16_t *dst,
                                int dst_y0, int rows) {
    const uint8_t *src = (const uint8_t *)DG_ScreenBuffer;
    const int out_w = abi->frame_width;
    const int out_h = abi->frame_height;
    for (int y = dst_y0; y < dst_y0 + rows; y++) {
        const int sy = (2 * y * DOOMGENERIC_RESY + out_h) / (2 * out_h);
        const uint8_t *src_row = src + sy * DOOMGENERIC_RESX;
        uint16_t *dst_row = dst + y * out_w;
        for (int x = 0; x < out_w; x++) {
            dst_row[x] = s_palette[src_row[s_xmap[x]]];
        }
    }
}

static uint32_t s_engine_ms;
static uint32_t s_convert_ms;
static uint32_t s_present_ms;
static uint32_t s_profile_ms;

static void present_frame(const mpos_core_abi_t *abi) {
    if (DG_ScreenBuffer == NULL) {
        return;
    }
    for (int i = 0; i < 256; i++) {
        s_palette[i] = rgb565((int)colors[i].r, (int)colors[i].g,
                              (int)colors[i].b);
    }
    palette_changed = false;

    const int height = abi->frame_height;
    // The host's surface shape says how to present it: a 200x320 surface is
    // the rotated portrait layout, a 320x200 one is Doom's own landscape frame,
    // and anything smaller is that frame scaled down.
    const int rotate = (abi->frame_width == DOOMGENERIC_RESY
                         && abi->frame_height == DOOMGENERIC_RESX);
    const int scaled = !rotate
        && abi->frame_width <= DOOMGENERIC_RESX
        && abi->frame_height <= DOOMGENERIC_RESY
        && (abi->frame_width != DOOMGENERIC_RESX
            || abi->frame_height != DOOMGENERIC_RESY);
    if (scaled) {
        for (int x = 0; x < abi->frame_width; x++) {
            s_xmap[x] = (uint16_t)((2 * x * DOOMGENERIC_RESX
                                    + abi->frame_width)
                                   / (2 * abi->frame_width));
        }
    }
    uint16_t *target = abi->frame;
    if (target != NULL) {
        int band = abi->band_rows > 0 ? abi->band_rows : height;
        if (band > height) {
            band = height;
        }
        for (int y = 0; y < height; y += band) {
            int rows = height - y;
            if (rows > band) {
                rows = band;
            }
            uint32_t started = abi->now_ms(abi->host);
            if (rotate) {
                convert_band(abi, target, y, rows);
            } else if (scaled) {
                convert_band_scaled(abi, target, y, rows);
            } else {
                convert_band_direct(abi, target, y, rows);
            }
            uint32_t converted = abi->now_ms(abi->host);
            s_convert_ms += converted - started;
            // The host flushes these rows now, so its panel transfer runs while
            // the next band is being converted.
            abi->present_band(abi->host, y, rows, NULL);
            s_present_ms += abi->now_ms(abi->host) - converted;
        }
        return;
    }

    // No surface from the host: keep our own copy and hand bands over.
    if (rotate) {
        convert_band(abi, s_surface, 0, height);
    } else if (scaled) {
        convert_band_scaled(abi, s_surface, 0, height);
    } else {
        convert_band_direct(abi, s_surface, 0, height);
    }
    const int band = abi->band_rows > 0 ? abi->band_rows : height;
    for (int y = 0; y < height; y += band) {
        int rows = height - y;
        if (rows > band) {
            rows = band;
        }
        abi->present_band(abi->host, y, rows,
                          (const uint8_t *)&s_surface[y * abi->frame_width]);
    }
}

// -- core entry points -------------------------------------------------------

/* core_sound.c: mixes the engine's sound effects on demand. */
void mpos_sound_mix(int16_t *dst, int frames);
void mpos_sound_module_init(void);
void mpos_sound_report(void);
void mpos_sound_set_abi(const mpos_core_abi_t *abi);
void mpos_music_module_init(void);

static int core_quit_requested(void) {
    return mpos_quit_requested;
}

static int core_init(const mpos_core_abi_t *abi, const char *wad_path,
                     const char *config_dir) {
    mpos_libc_init(abi);
    mpos_sound_set_abi(abi);
    mpos_sound_module_init();
    mpos_music_module_init();
    s_abi = abi;
    if (wad_path == NULL || wad_path[0] == '\0') {
        return -1;
    }
    size_t len = strlen(wad_path);
    if (len >= sizeof(s_wad_path)) {
        return -1;
    }
    memcpy(s_wad_path, wad_path, len + 1);

    // Where .default.cfg and .savegame/ go. Absolute, because the host keeps
    // the process working directory; d_main only defaults it when it is unset.
    if (config_dir != NULL && config_dir[0] != '\0') {
        size_t dir_len = strlen(config_dir);
        if (dir_len >= sizeof(s_config_dir)) {
            return -2;
        }
        memcpy(s_config_dir, config_dir, dir_len + 1);
        M_SetConfigDir(s_config_dir);
    }

    s_argv[0] = "doom";
    s_argv[1] = "-iwad";
    s_argv[2] = s_wad_path;
    s_argv[3] = "-mb";
    s_argv[4] = s_zone_buf;
    s_argv[5] = NULL;
    s_argv[4][0] = '3';  // megabytes of zone: the rest of PSRAM stays with the OS
    s_argv[4][1] = '\0';

    s_now_ms = 0;
    s_start_ms = 0;
    s_have_start = 0;
    s_key_head = 0;
    s_key_tail = 0;
    s_frame_ready = 0;
    mpos_quit_requested = 0;

    // The dataless build moves every initialised global into code; this copies
    // them into the arena before the engine reads anything.
    doom_init_all_data();
    doomgeneric_Create(5, s_argv);
    s_created = 1;
    mpos_sound_report();
    return 0;
}

// A touchscreen or a two-button badge has no keyboard, and the button a player
// calls "fire" should also mean "select": while a menu is up, fire confirms.
// Everything else passes through - the four arrow keys already steer a Doom
// menu (up/down move the cursor, left/right adjust a slider), and dropping or
// remapping them is how up/down ended up doing nothing in menus. The native
// module maps the same way (c_mpos/doom/doomgeneric_mpos.c) - keep the two in
// step.
static int menu_key(int code) {
    if (menuactive) {
        return code == KEY_FIRE ? KEY_ENTER : code;
    }
    if (gamestate == GS_INTERMISSION || gamestate == GS_FINALE) {
        return code == KEY_FIRE ? KEY_ENTER : code;
    }
    return code;
}

static void core_tick(const mpos_core_abi_t *abi, uint32_t now_ms) {
    if (!s_created || s_stopped || mpos_libc_exit_requested()) {
        return;
    }
    if (mpos_quit_requested) {
        // The player picked "quit" in the menu. A host on ABI 7 or later reads
        // quit_requested() and closes the activity; an older one has no way to
        // hear it, so the engine goes back to its title screen instead of
        // sitting on a frozen frame.
        if (abi->version < 7) {
            mpos_quit_requested = 0;
            M_ClearMenus();
            D_StartTitle();
        }
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
        code = menu_key(code);
        const int next = (s_key_head + 1) % MAX_KEYS;
        if (code >= 0 && next != s_key_tail) {
            s_keys[s_key_head] = (uint16_t)((pressed ? 0x100 : 0) | (code & 0xFF));
            s_key_head = next;
        }
        code = abi->poll_key(abi->host, &pressed);
    }

    uint32_t started = abi->now_ms(abi->host);
    doomgeneric_Tick();
    s_engine_ms += abi->now_ms(abi->host) - started;

    if (s_frame_ready) {
        s_frame_ready = 0;
        present_frame(abi);
    }

    // Where the frame time goes, once every two seconds. Cheap enough to keep,
    // and the only way to tell a slow engine from a slow panel.
    uint32_t now = abi->now_ms(abi->host);
    s_profile_frames++;
    if (now - s_profile_ms >= 2000 && s_profile_frames > 1) {
        char line[112];
        snprintf(line, sizeof(line),
                 "core: engine %.1f ms, convert %.1f ms, present %.1f ms (gs %d menu %d)",
                 (double)s_engine_ms / s_profile_frames,
                 (double)s_convert_ms / s_profile_frames,
                 (double)s_present_ms / s_profile_frames,
                 (int)gamestate, menuactive ? 1 : 0);
        abi->log(abi->host, line);
        s_engine_ms = 0;
        s_convert_ms = 0;
        s_present_ms = 0;
        s_profile_frames = 0;
        s_profile_ms = now;
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
    .audio_mix = mpos_sound_mix,
    .quit_requested = core_quit_requested,
};
