// Doom in MicroPythonOS: the platform layer doomgeneric asks a port for, as a
// MicroPython native module.
//
// The engine is built with CMAP256, so it keeps an 8-bit paletted framebuffer
// (pixel_t is uint8_t) and this module hands that buffer and its palette to
// Python. The app converts it to RGB565 one band at a time while LVGL feeds the
// panel, which is where the conversion is free (see
// docs/apps/native-apps.md, "Converting a legacy format, band by band").
//
// The contract with Python:
//
//   create(wad_path, mb)   boot the engine (doomgeneric_Create) and draw one frame
//   tick(now_ms)           run one engine frame; now_ms is the wall clock
//   frame()                bytearray (by reference) holding the 320x200 pixels
//   palette()              bytearray (by reference) of 256 RGB565 entries
//   key(code, pressed)     queue a Doom key event for DG_GetKey
//   width() / height()     engine resolution
//
// No file names, no time, no display: everything OS-like is passed in.

#include "py/dynruntime.h"

// Doom defines `true`/`false` as enumerators, MicroPython's headers get them
// from <stdbool.h>: drop the macros before the engine headers are parsed.
#ifdef true
#undef true
#endif
#ifdef false
#undef false
#endif

#include "doomdef.h"
#include "doomgeneric.h"
#include "doomkeys.h"
#include "i_video.h"
#include "doomstat.h"

#include "doom_data_init.h"

#define MAX_KEYS 64

// Global BSS only: a native module has no data section and no static BSS.
uint32_t g_now_ms;
uint32_t g_start_ms;
int g_have_start;
int g_created;

uint16_t g_keys[MAX_KEYS];
int g_key_head;
int g_key_tail;

uint16_t g_palette[256];
int g_palette_ready;

char *g_argv[8];
char g_mb_buf[8];
mp_obj_t g_wad_obj;

uint32_t mpos_get_clock_ms(void);
void mpos_libc_init(void);
void mpos_set_clock_ms(uint32_t now_ms);

static uint16_t rgb565(int r, int g, int b) {
    return (uint16_t)(((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3));
}

// ---- doomgeneric platform functions ---------------------------------------

void DG_Init(void) {
    // doomgeneric.c allocates four bytes per pixel before calling us. With an
    // 8-bit pixel_t that is four times too much, and on the badge the zone
    // wants that RAM, so take the buffer back and keep one byte per pixel.
    if (DG_ScreenBuffer != NULL) {
        m_free(DG_ScreenBuffer);
    }
    DG_ScreenBuffer = m_malloc((size_t)DOOMGENERIC_RESX * DOOMGENERIC_RESY *
                               sizeof(pixel_t));
}

uint32_t g_draw_frames;

void DG_DrawFrame(void) {
    g_draw_frames++;
    // The engine finished a frame in I_VideoBuffer; that is the buffer Python
    // should read, so drop the extra copy target doomgeneric allocated. From
    // here on I_FinishUpdate's copy is a no-op (source == destination).
    if (I_VideoBuffer != NULL && DG_ScreenBuffer != I_VideoBuffer) {
        if (DG_ScreenBuffer != NULL) {
            m_free(DG_ScreenBuffer);
        }
        DG_ScreenBuffer = I_VideoBuffer;
    }
}

void DG_SleepMs(uint32_t ms) {
    // The engine is driven from Python: time only moves when it asks to sleep.
    // A real sleep here would stop the app's frame loop (and a no-op would
    // spin TryRunTics forever, which waits for I_GetTime() to advance).
    g_now_ms += ms;
}

uint32_t DG_GetTicksMs(void) {
    return g_now_ms - g_start_ms;
}

int DG_GetKey(int *pressed, unsigned char *key) {
    if (g_key_tail == g_key_head) {
        return 0;
    }
    const uint16_t event = g_keys[g_key_tail];
    g_key_tail = (g_key_tail + 1) % MAX_KEYS;
    *pressed = event >> 8;
    *key = (unsigned char)(event & 0xFF);
    return 1;
}

void DG_SetWindowTitle(const char *title) {
    (void)title;
}

// ---- module functions -----------------------------------------------------

static mp_obj_t create(mp_obj_t wad_obj, mp_obj_t mb_obj) {
    if (g_created) {
        return mp_const_none;
    }
    // Doom keeps the argv pointers for the whole session, so the string has to
    // stay alive: hold a reference to the Python object.
    g_wad_obj = wad_obj;
    g_argv[0] = "doom";
    g_argv[1] = "-iwad";
    g_argv[2] = (char *)mp_obj_str_get_str(wad_obj);
    g_argv[3] = "-mb";
    snprintf(g_mb_buf, sizeof(g_mb_buf), "%d", (int)mp_obj_get_int(mb_obj));
    g_argv[4] = g_mb_buf;
    g_argv[5] = "-nosound";
    g_argv[6] = NULL;

    g_now_ms = 0;
    g_start_ms = 0;
    g_have_start = 0;
    g_key_head = 0;
    g_key_tail = 0;
    g_palette_ready = 0;
    g_created = 1;

    // libc tables (ctype) and the generated initialised data, before the
    // engine reads anything.
    mpos_libc_init();
    doom_init_all_data();
    doomgeneric_Create(6, g_argv);
    return mp_const_none;
}static MP_DEFINE_CONST_FUN_OBJ_2(create_obj, create);

static mp_obj_t tick(mp_obj_t now_obj) {
    if (!g_created) {
        return mp_const_none;
    }
    const uint32_t now_ms = (uint32_t)mp_obj_get_int(now_obj);
    // Never move the clock backwards, but follow the real one: the engine's
    // own sleeps only keep TryRunTics from spinning.
    if (!g_have_start) {
        g_start_ms = now_ms;
        g_have_start = 1;
    }
    g_now_ms = now_ms;
    mpos_set_clock_ms(g_now_ms - g_start_ms);
    doomgeneric_Tick();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(tick_obj, tick);

static mp_obj_t frame(void) {
    if (DG_ScreenBuffer == NULL) {
        return mp_const_none;
    }
    return mp_obj_new_bytearray_by_ref(
        (size_t)DOOMGENERIC_RESX * DOOMGENERIC_RESY, DG_ScreenBuffer);
}
static MP_DEFINE_CONST_FUN_OBJ_0(frame_obj, frame);

// palette(): 256 RGB565 entries, refreshed when the engine changed the
// palette. i_video.c fills colors[] with the gamma-corrected RGB values.
static mp_obj_t palette(void) {
    if (palette_changed || !g_palette_ready) {
        for (int i = 0; i < 256; i++) {
            g_palette[i] = rgb565((int)colors[i].r, (int)colors[i].g,
                                  (int)colors[i].b);
        }
        g_palette_ready = 1;
        palette_changed = false;
    }
    return mp_obj_new_bytearray_by_ref(512, g_palette);
}
static MP_DEFINE_CONST_FUN_OBJ_0(palette_obj, palette);

// blit_band(dst, band, rows): convert one band of the paletted frame into an
// RGB565 destination at the same row offset.
//
// Doing this per band, from the render callback, lets the conversion of one
// band overlap the SPI transfer of the previous one (see
// docs/apps/native-apps.md): a whole-frame conversion costs a frame's worth of
// SPI on top of the transfer instead of underneath it.
static mp_obj_t blit_band(mp_obj_t dst_obj, mp_obj_t band_obj, mp_obj_t rows_obj) {
    if (DG_ScreenBuffer == NULL) {
        return mp_const_none;
    }
    if (!g_palette_ready || palette_changed) {
        for (int i = 0; i < 256; i++) {
            g_palette[i] = rgb565((int)colors[i].r, (int)colors[i].g,
                                  (int)colors[i].b);
        }
        g_palette_ready = 1;
        palette_changed = false;
    }
    mp_buffer_info_t dst;
    mp_get_buffer_raise(dst_obj, &dst, MP_BUFFER_WRITE);
    const int band = (int)mp_obj_get_int(band_obj);
    const int rows = (int)mp_obj_get_int(rows_obj);
    const size_t width = (size_t)DOOMGENERIC_RESX;
    const size_t total = width * (size_t)DOOMGENERIC_RESY;
    const size_t start = (size_t)band * (size_t)rows * width;
    if (start >= total) {
        return mp_const_none;
    }
    size_t count = (size_t)rows * width;
    if (start + count > total) {
        count = total - start;
    }
    if (dst.len / 2 < start + count) {
        mp_raise_ValueError("destination too small");
    }
    const unsigned char *src = (const unsigned char *)DG_ScreenBuffer + start;
    uint16_t *out = (uint16_t *)dst.buf + start;
    for (size_t i = 0; i < count; i++) {
        out[i] = g_palette[src[i]];
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_3(blit_band_obj, blit_band);

static mp_obj_t key(mp_obj_t code_obj, mp_obj_t pressed_obj) {
    const int code = (int)mp_obj_get_int(code_obj);
    const int pressed = mp_obj_is_true(pressed_obj);
    const int next = (g_key_head + 1) % MAX_KEYS;
    if (next == g_key_tail) {
        return mp_const_false;
    }
    g_keys[g_key_head] = (uint16_t)((pressed ? 0x100 : 0) | (code & 0xFF));
    g_key_head = next;
    return mp_const_true;
}
static MP_DEFINE_CONST_FUN_OBJ_2(key_obj, key);

static mp_obj_t debug_state(void) {
    mp_printf(&mp_plat_print, "[dbg] draws=%u gamestate=%d gametic=%d wipe=%d ticks=%u\n",
              (unsigned)g_draw_frames, (int)gamestate, (int)gametic,
              (int)wipegamestate, (unsigned)DG_GetTicksMs());
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(debug_state_obj, debug_state);

static mp_obj_t width(void) {
    return mp_obj_new_int(DOOMGENERIC_RESX);
}
static MP_DEFINE_CONST_FUN_OBJ_0(width_obj, width);

static mp_obj_t height(void) {
    return mp_obj_new_int(DOOMGENERIC_RESY);
}
static MP_DEFINE_CONST_FUN_OBJ_0(height_obj, height);

mp_obj_t mpy_init(mp_obj_fun_bc_t *self, size_t n_args, size_t n_kw, mp_obj_t *args) {
    MP_DYNRUNTIME_INIT_ENTRY

    mp_store_global(MP_QSTR_create, MP_OBJ_FROM_PTR(&create_obj));
    mp_store_global(MP_QSTR_tick, MP_OBJ_FROM_PTR(&tick_obj));
    mp_store_global(MP_QSTR_frame, MP_OBJ_FROM_PTR(&frame_obj));
    mp_store_global(MP_QSTR_palette, MP_OBJ_FROM_PTR(&palette_obj));
    mp_store_global(MP_QSTR_key, MP_OBJ_FROM_PTR(&key_obj));
    mp_store_global(MP_QSTR_blit_band, MP_OBJ_FROM_PTR(&blit_band_obj));
    mp_store_global(MP_QSTR_width, MP_OBJ_FROM_PTR(&width_obj));
    mp_store_global(MP_QSTR_debug_state, MP_OBJ_FROM_PTR(&debug_state_obj));
    mp_store_global(MP_QSTR_height, MP_OBJ_FROM_PTR(&height_obj));

    mp_store_global(MP_QSTR_KEY_LEFT, MP_OBJ_NEW_SMALL_INT(KEY_LEFTARROW));
    mp_store_global(MP_QSTR_KEY_RIGHT, MP_OBJ_NEW_SMALL_INT(KEY_RIGHTARROW));
    mp_store_global(MP_QSTR_KEY_UP, MP_OBJ_NEW_SMALL_INT(KEY_UPARROW));
    mp_store_global(MP_QSTR_KEY_DOWN, MP_OBJ_NEW_SMALL_INT(KEY_DOWNARROW));
    mp_store_global(MP_QSTR_KEY_ENTER, MP_OBJ_NEW_SMALL_INT(KEY_ENTER));
    mp_store_global(MP_QSTR_KEY_ESCAPE, MP_OBJ_NEW_SMALL_INT(KEY_ESCAPE));
    mp_store_global(MP_QSTR_KEY_USE, MP_OBJ_NEW_SMALL_INT(KEY_USE));
    mp_store_global(MP_QSTR_KEY_FIRE, MP_OBJ_NEW_SMALL_INT(KEY_FIRE));
    mp_store_global(MP_QSTR_KEY_YES, MP_OBJ_NEW_SMALL_INT('y'));
    mp_store_global(MP_QSTR_KEY_NO, MP_OBJ_NEW_SMALL_INT('n'));

    MP_DYNRUNTIME_INIT_EXIT
}
