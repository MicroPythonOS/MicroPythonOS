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
//   create_from_memory(buffer, mb)  the same, with the WAD already in RAM
//   clear_wad()            drop the memory WAD reference (before freeing it)
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
#include "d_main.h"
#include "m_config.h"
#include "m_menu.h"
#include "w_file.h"

#include "doom_data_init.h"
#include "mpos_engine.h"

/* core/core_sound.c: the engine's own mixer, also used by the core build. */
void mpos_sound_mix(int16_t *dst, int frames);
void mpos_sound_module_init(void);
void mpos_sound_report(void);
void mpos_music_module_init(void);

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
// The engine keeps M_SetConfigDir's pointer for the whole session, so the
// Python string it came from has to stay alive too.
mp_obj_t g_config_obj;

// Presentation target: the host's RGB565 surface, and the Python callback that
// flushes each band. A borrowed reference - the app holds the bound method for
// as long as the surface is set, and clears it on stop.
uint16_t *g_target;
int g_target_width;
int g_target_height;
int g_band_rows;
mp_obj_t g_present_cb;

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

// A touchscreen or a two-button badge has no keyboard, and the button a player
// calls "fire" should also mean "select": while a menu is up, fire confirms.
// Everything else passes through - the four arrow keys already steer a Doom
// menu (up/down move the cursor, left/right adjust a slider), and dropping or
// remapping them is how up/down ended up doing nothing in menus. The core build
// maps the same way (c_mpos/doom/core/doom_core.c) - keep the two in step.
static int menu_key(int code) {
    if (menuactive) {
        return code == KEY_FIRE ? KEY_ENTER : code;
    }
    if (gamestate == GS_INTERMISSION || gamestate == GS_FINALE) {
        return code == KEY_FIRE ? KEY_ENTER : code;
    }
    return code;
}

int DG_GetKey(int *pressed, unsigned char *key) {
    if (g_key_tail == g_key_head) {
        return 0;
    }
    const uint16_t event = g_keys[g_key_tail];
    g_key_tail = (g_key_tail + 1) % MAX_KEYS;
    *pressed = event >> 8;
    *key = (unsigned char)menu_key((int)(event & 0xFF));
    return 1;
}

void DG_SetWindowTitle(const char *title) {
    (void)title;
}

// ---- module functions -----------------------------------------------------

static void engine_config(const mp_obj_t *args, size_t n_args) {
    if (n_args > 2 && args[2] != mp_const_none) {
        // Where .default.cfg and .savegame/ go, absolute: the host does not
        // change the process working directory for the engine.
        g_config_obj = args[2];
        M_SetConfigDir((char *)mp_obj_str_get_str(args[2]));
    }
}

// 1 when the engine has to boot, 0 when it is already loaded (the module
// outlives the activity, so a second start goes back to the title screen).
static int engine_prepare(mp_obj_t mb_obj) {
    if (g_created) {
        // Clear the request and put it back on the title screen instead of
        // booting a second copy of Doom.
        mpos_quit_requested = 0;
        M_ClearMenus();
        D_StartTitle();
        return 0;
    }
    mpos_quit_requested = 0;
    mpos_sound_module_init();
    mpos_music_module_init();
    snprintf(g_mb_buf, sizeof(g_mb_buf), "%d", (int)mp_obj_get_int(mb_obj));

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
    return 1;
}

static void engine_boot(const char *wad_name) {
    // Doom keeps the argv pointers for the whole session, so the strings have
    // to stay alive: the caller holds g_wad_obj for that.
    g_argv[0] = "doom";
    g_argv[1] = "-iwad";
    g_argv[2] = (char *)wad_name;
    g_argv[3] = "-mb";
    g_argv[4] = g_mb_buf;
    g_argv[5] = NULL;
    doomgeneric_Create(5, g_argv);
    mpos_sound_report();
}

static mp_obj_t create(size_t n_args, const mp_obj_t *args) {
    engine_config(args, n_args);
    W_ClearMemoryFile();
    if (engine_prepare(args[1])) {
        g_wad_obj = args[0];
        engine_boot((char *)mp_obj_str_get_str(args[0]));
    }
    return mp_const_none;
}static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(create_obj, 2, 3, create);

// The WAD is already in RAM (the host inflated the bundled zip). Nothing is
// written to storage and no file is opened for it.
static mp_obj_t create_from_memory(size_t n_args, const mp_obj_t *args) {
    mp_buffer_info_t wad;
    mp_get_buffer_raise(args[0], &wad, MP_BUFFER_READ);
    engine_config(args, n_args);
    W_SetMemoryFile(wad.buf, wad.len);
    if (engine_prepare(args[1])) {
        // Borrowed: the app keeps the buffer alive for as long as it is set.
        g_wad_obj = args[0];
        engine_boot(W_MEMORY_WAD_NAME);
    }
    return mp_const_none;
}static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(create_from_memory_obj, 2, 3,
                                           create_from_memory);

// Drop the engine's reference to the buffer, so the host can free it without
// leaving a dangling WAD behind (the engine still has lumps cached in its zone
// until the next boot).
static mp_obj_t clear_wad(void) {
    W_ClearMemoryFile();
    return mp_const_none;
}static MP_DEFINE_CONST_FUN_OBJ_0(clear_wad_obj, clear_wad);

static void present_frame(void);

static mp_obj_t tick(mp_obj_t now_obj) {
    if (!g_created || mpos_quit_requested) {
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
    present_frame();
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
// One band of the paletted frame -> RGB565, at the same row offset.
static void convert_pixels(uint16_t *out, const unsigned char *src,
                           size_t count) {
    if (!g_palette_ready || palette_changed) {
        for (int i = 0; i < 256; i++) {
            g_palette[i] = rgb565((int)colors[i].r, (int)colors[i].g,
                                  (int)colors[i].b);
        }
        g_palette_ready = 1;
        palette_changed = false;
    }
    for (size_t i = 0; i < count; i++) {
        out[i] = g_palette[src[i]];
    }
}

static mp_obj_t blit_band(mp_obj_t dst_obj, mp_obj_t band_obj, mp_obj_t rows_obj) {
    if (DG_ScreenBuffer == NULL) {
        return mp_const_none;
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
    convert_pixels((uint16_t *)dst.buf + start, src, count);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_3(blit_band_obj, blit_band);

// surface(buffer, width, height, band_rows, present): where this frame goes.
//
// Same contract as a flash-resident core: the engine draws RGB565 into the
// host's buffer one display band at a time and calls present(y, rows) for each
// finished band, so the panel transfer of one band overlaps the conversion of
// the next. buffer=None (or present=None) stops presenting.
static mp_obj_t surface(size_t n_args, const mp_obj_t *args) {
    if (n_args != 5) {
        mp_raise_TypeError("surface() takes 5 arguments");
    }
    if (args[0] == mp_const_none || args[4] == mp_const_none) {
        g_target = NULL;
        g_present_cb = mp_const_none;
        return mp_const_none;
    }
    const int width = (int)mp_obj_get_int(args[1]);
    const int height = (int)mp_obj_get_int(args[2]);
    const int band_rows = (int)mp_obj_get_int(args[3]);
    if (width != DOOMGENERIC_RESX || height != DOOMGENERIC_RESY) {
        // The module presents the engine's own frame; it cannot transpose it
        // for a portrait panel the way the core does.
        mp_raise_ValueError("surface must be the engine resolution");
    }
    if (band_rows < 1) {
        mp_raise_ValueError("band_rows must be positive");
    }
    mp_buffer_info_t dst;
    mp_get_buffer_raise(args[0], &dst, MP_BUFFER_WRITE);
    if (dst.len / 2 < (size_t)width * (size_t)height) {
        mp_raise_ValueError("destination too small");
    }
    g_target = (uint16_t *)dst.buf;
    g_target_width = width;
    g_target_height = height;
    g_band_rows = band_rows;
    g_present_cb = args[4];
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(surface_obj, 5, 5, surface);

// Convert and announce one frame's bands. Called from tick(), after the engine
// has drawn, so the whole frame path lives in C except the flush itself.
static void present_frame(void) {
    if (g_target == NULL || g_present_cb == mp_const_none || DG_ScreenBuffer == NULL) {
        return;
    }
    const size_t width = (size_t)g_target_width;
    const size_t height = (size_t)g_target_height;
    for (size_t y = 0; y < height; y += (size_t)g_band_rows) {
        size_t rows = (size_t)g_band_rows;
        if (y + rows > height) {
            rows = height - y;
        }
        const size_t start = y * width;
        convert_pixels(g_target + start,
                       (const unsigned char *)DG_ScreenBuffer + start,
                       rows * width);
        mp_obj_t call_args[2];
        call_args[0] = mp_obj_new_int((int)y);
        call_args[1] = mp_obj_new_int((int)rows);
        mp_call_function_n_kw(g_present_cb, 2, 0, call_args);
    }
}

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

extern short itemOn;

static mp_obj_t debug_state(void) {
    mp_printf(&mp_plat_print,
              "[dbg] draws=%u gamestate=%d menu=%d item=%d gametic=%d wipe=%d ticks=%u\n",
              (unsigned)g_draw_frames, (int)gamestate, menuactive ? 1 : 0,
              (int)itemOn, (int)gametic, (int)wipegamestate,
              (unsigned)DG_GetTicksMs());
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

static mp_obj_t audio_mix(mp_obj_t buf_obj) {
    mp_buffer_info_t view;
    mp_get_buffer_raise(buf_obj, &view, MP_BUFFER_WRITE);
    const int frames = (int)(view.len / 2);
    mpos_sound_mix((int16_t *)view.buf, frames);
    return mp_obj_new_int(frames);
}
static MP_DEFINE_CONST_FUN_OBJ_1(audio_mix_obj, audio_mix);

static mp_obj_t quit_requested(void) {
    return mpos_quit_requested ? mp_const_true : mp_const_false;
}
static MP_DEFINE_CONST_FUN_OBJ_0(quit_requested_obj, quit_requested);

mp_obj_t mpy_init(mp_obj_fun_bc_t *self, size_t n_args, size_t n_kw, mp_obj_t *args) {
    MP_DYNRUNTIME_INIT_ENTRY

    mp_store_global(MP_QSTR_create, MP_OBJ_FROM_PTR(&create_obj));
    mp_store_global(MP_QSTR_create_from_memory,
                    MP_OBJ_FROM_PTR(&create_from_memory_obj));
    mp_store_global(MP_QSTR_clear_wad, MP_OBJ_FROM_PTR(&clear_wad_obj));
    mp_store_global(MP_QSTR_tick, MP_OBJ_FROM_PTR(&tick_obj));
    mp_store_global(MP_QSTR_frame, MP_OBJ_FROM_PTR(&frame_obj));
    mp_store_global(MP_QSTR_palette, MP_OBJ_FROM_PTR(&palette_obj));
    mp_store_global(MP_QSTR_key, MP_OBJ_FROM_PTR(&key_obj));
    mp_store_global(MP_QSTR_blit_band, MP_OBJ_FROM_PTR(&blit_band_obj));
    mp_store_global(MP_QSTR_surface, MP_OBJ_FROM_PTR(&surface_obj));
    mp_store_global(MP_QSTR_width, MP_OBJ_FROM_PTR(&width_obj));
    mp_store_global(MP_QSTR_debug_state, MP_OBJ_FROM_PTR(&debug_state_obj));
    mp_store_global(MP_QSTR_height, MP_OBJ_FROM_PTR(&height_obj));
    mp_store_global(MP_QSTR_quit_requested, MP_OBJ_FROM_PTR(&quit_requested_obj));
    mp_store_global(MP_QSTR_audio_mix, MP_OBJ_FROM_PTR(&audio_mix_obj));

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
