// framecore_probe: the smallest thing that behaves like a legacy framebuffer
// engine inside MicroPythonOS, for measuring the path before committing to a
// Doom-sized port.
//
// The shape it imitates is what Doom/Duke3D-style engines expect:
//
//   * the engine owns one 320x200 framebuffer and redraws all of it per frame;
//   * it is handed a surface and writes pixels into it, never calls the display;
//   * it needs libc (string.h/stdlib.h/stdio.h) that a natmod does not link;
//   * it polls a key queue (DG_GetKey) and reads lumps from a file;
//   * it never reads the clock: `now_ms` comes from Python.
//
// Functions:
//   init(buffer, width, height, y_offset)
//   draw(now_ms)                        full redraw of the engine frame
//   key(code, pressed)                  push an input event
//   poll_key()                          (pressed<<8)|code, or -1
//   expand8(src, palette, dst)          8-bit + RGB888 palette -> RGB565
//   set_palette(palette) / expand8_lut  8-bit through a prepared RGB565 table
//   expand32(src, dst)                  32-bit RGBX -> RGB565
//   fill_index(src) / fill_rgbx(src)    test sources for the conversions
//   alloc_framebuffer(width, height)    the engine owns its pixels (m_malloc)
//   free_framebuffer()
//   set_file_reader(reader) / read_file(path, offset, into)
//   get_frames(), get_box_x(), get_box_y()

#include "py/dynruntime.h"
#include <stdbool.h>
#include "libc_shim.h"

#ifdef FRAMECORE_BIG
// The Doom-sized variant: a quarter megabyte of const tables and the same again
// of BSS. Native modules are loaded into the MicroPython heap at import, so
// this is here to measure whether such a module fits and what it costs.
const uint32_t g_big_rodata[65536] = {
    [0 ... 65535] = 0x9E3779B9u,
};
unsigned char g_big_bss[256 * 1024];
#endif

#define MAX_KEYS 32

// ---- state (global BSS: a native module has no data section) --------------

uint16_t *g_frame;
size_t g_frame_pixels;
int g_width;
int g_height;
int g_y_offset;

uint32_t g_frames;
int g_box_x;
int g_box_y;

uint16_t g_keys[MAX_KEYS];
int g_key_head;
int g_key_tail;

uint16_t g_palette_lut[256];
uint8_t g_palette_valid;

uint8_t *g_owned;
size_t g_owned_bytes;

mp_obj_t g_file_reader;

// ---- the probe's own little font ------------------------------------------

#define GLYPH_COLUMNS 5
#define GLYPH_ROWS 7

// Column-major 5x7 glyphs, bit 0 is the top row.
static const uint8_t g_glyph_digit[10][GLYPH_COLUMNS] = {
    {0x3E, 0x51, 0x49, 0x45, 0x3E},  // 0
    {0x00, 0x42, 0x7F, 0x40, 0x00},  // 1
    {0x42, 0x61, 0x51, 0x49, 0x46},  // 2
    {0x21, 0x41, 0x45, 0x4B, 0x31},  // 3
    {0x18, 0x14, 0x12, 0x7F, 0x10},  // 4
    {0x27, 0x45, 0x45, 0x45, 0x39},  // 5
    {0x3C, 0x4A, 0x49, 0x49, 0x30},  // 6
    {0x01, 0x71, 0x09, 0x05, 0x03},  // 7
    {0x36, 0x49, 0x49, 0x49, 0x36},  // 8
    {0x06, 0x49, 0x49, 0x29, 0x1E},  // 9
};

static const uint8_t g_glyph_space[GLYPH_COLUMNS] = {0, 0, 0, 0, 0};
static const uint8_t g_glyph_colon[GLYPH_COLUMNS] = {0x00, 0x36, 0x36, 0x00, 0x00};

static const uint8_t *glyph_for(char c) {
    static const uint8_t glyph_a[GLYPH_COLUMNS] = {0x7E, 0x11, 0x11, 0x11, 0x7E};
    static const uint8_t glyph_e[GLYPH_COLUMNS] = {0x7F, 0x49, 0x49, 0x49, 0x41};
    static const uint8_t glyph_f[GLYPH_COLUMNS] = {0x7F, 0x09, 0x09, 0x09, 0x01};
    static const uint8_t glyph_m[GLYPH_COLUMNS] = {0x7F, 0x02, 0x0C, 0x02, 0x7F};
    static const uint8_t glyph_r[GLYPH_COLUMNS] = {0x7F, 0x09, 0x19, 0x29, 0x46};
    static const uint8_t glyph_s[GLYPH_COLUMNS] = {0x46, 0x49, 0x49, 0x49, 0x31};
    if (c >= '0' && c <= '9') {
        return g_glyph_digit[c - '0'];
    }
    switch (c) {
        case 'A': return glyph_a;
        case 'E': return glyph_e;
        case 'F': return glyph_f;
        case 'M': return glyph_m;
        case 'R': return glyph_r;
        case 'S': return glyph_s;
        case ':': return g_glyph_colon;
        default: return g_glyph_space;
    }
}

// ---- drawing helpers ------------------------------------------------------

static void fill_rect(int x, int y, int w, int h, uint16_t color) {
    if (g_frame == NULL || w <= 0 || h <= 0) {
        return;
    }
    if (x < 0) {
        w += x;
        x = 0;
    }
    if (y < 0) {
        h += y;
        y = 0;
    }
    if (x + w > g_width) {
        w = g_width - x;
    }
    if (y + h > g_height) {
        h = g_height - y;
    }
    if (w <= 0 || h <= 0) {
        return;
    }
    for (int yy = y; yy < y + h; yy++) {
        uint16_t *row = g_frame + (size_t)(g_y_offset + yy) * (size_t)g_width + x;
        for (int xx = 0; xx < w; xx++) {
            row[xx] = color;
        }
    }
}

// Scale 2: each font pixel is a 2x2 square, so the counter is readable at 320
// pixels wide and the string still costs almost nothing to draw.
static void draw_text(int x, int y, const char *text) {
    const int cell = 6 * 2;
    int cursor = x;
    for (const char *p = text; *p; p++) {
        const uint8_t *glyph = glyph_for(*p);
        for (int col = 0; col < GLYPH_COLUMNS; col++) {
            const uint8_t bits = glyph[col];
            for (int row = 0; row < GLYPH_ROWS; row++) {
                if (bits & (1u << row)) {
                    fill_rect(cursor + col * 2, y + row * 2, 2, 2, 0xFFFF);
                }
            }
        }
        cursor += cell;
    }
}

static const uint16_t g_bar_colors[8] = {
    0xF800, 0xFC00, 0xFFE0, 0x07E0, 0x07FF, 0x001F, 0xF81F, 0xFFFF,
};

// ---- module functions -----------------------------------------------------

// init(buffer, width, height, y_offset): take the surface the engine draws into.
static mp_obj_t probe_init(size_t n_args, const mp_obj_t *args) {
    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(args[0], &bufinfo, MP_BUFFER_WRITE);
    g_frame = (uint16_t *)bufinfo.buf;
    g_frame_pixels = bufinfo.len / sizeof(uint16_t);

    g_width = (int)mp_obj_get_int(args[1]);
    g_height = (int)mp_obj_get_int(args[2]);
    g_y_offset = (int)mp_obj_get_int(args[3]);
    if (g_width < 1 || g_height < 1 || g_y_offset < 0) {
        mp_raise_ValueError("bad surface geometry");
    }
    if ((size_t)(g_y_offset + g_height) * (size_t)g_width > g_frame_pixels) {
        mp_raise_ValueError("buffer too small");
    }

    g_frames = 0;
    g_box_x = g_width / 2 - 8;
    g_box_y = g_height / 2 - 8;
    g_key_head = 0;
    g_key_tail = 0;
    g_palette_valid = 0;
    // A fresh engine has no file callback: a reader from a previous session
    // would otherwise still be called (or keep its file open).
    g_file_reader = mp_const_none;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(probe_init_obj, 4, 4, probe_init);

// draw(now_ms): one whole engine frame, the way Doom's I_FinishUpdate does it.
static mp_obj_t draw(mp_obj_t now_obj) {
    (void)now_obj;  // The engine is handed the clock; it never asks for it.
    if (g_frame == NULL) {
        return mp_const_none;
    }

    const int bar_width = g_width / 8;
    for (int y = 0; y < g_height; y++) {
        uint16_t *row = g_frame + (size_t)(g_y_offset + y) * (size_t)g_width;
        for (int x = 0; x < g_width; x++) {
            int bar = x / (bar_width > 0 ? bar_width : 1);
            if (bar > 7) {
                bar = 7;
            }
            row[x] = g_bar_colors[bar];
        }
    }

    // A slab of the frame is darker, so a full-frame redraw is visibly a full
    // frame and not a stale surface.
    fill_rect(0, g_height / 2, g_width, g_height / 2, 0x2104);

    // Something that moves: driven by key()/poll_key(), so it also proves the
    // input path from the badge buttons.
    fill_rect(g_box_x, g_box_y, 16, 16, 0xFFFF);
    fill_rect(g_box_x + 2, g_box_y + 2, 12, 12, 0xF800);

    // Text formatted through the shim's vsnprintf. If the shim is wrong the
    // screen says so, which is cheaper than a serial log.
    char text[24];
    snprintf(text, sizeof(text), "FRAME %05u", (unsigned int)g_frames);
    fill_rect(2, 2, 11 * 12 + 4, GLYPH_ROWS * 2 + 4, 0x0000);
    draw_text(4, 4, text);

    g_frames++;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(draw_obj, draw);

// ---- input ----------------------------------------------------------------

// key(code, pressed): the badge button path. Kept in a ring so the engine can
// poll at its own pace, which is the shape DG_GetKey expects.
static mp_obj_t key(mp_obj_t code_obj, mp_obj_t pressed_obj) {
    int code = (int)mp_obj_get_int(code_obj);
    int pressed = mp_obj_is_true(pressed_obj);

    // The box is the probe's own feedback, so it moves even while the queue is
    // full: an engine polling too slowly loses events, not the picture.
    if (pressed) {
        const int step = 8;
        if (code == 1) {
            g_box_x -= step;
            if (g_box_x < 0) {
                g_box_x = 0;
            }
        } else if (code == 2) {
            g_box_x += step;
            if (g_box_x > g_width - 16) {
                g_box_x = g_width - 16;
            }
        } else if (code == 3) {
            g_box_y -= step;
            if (g_box_y < 0) {
                g_box_y = 0;
            }
        } else if (code == 4) {
            g_box_y += step;
            if (g_box_y > g_height - 16) {
                g_box_y = g_height - 16;
            }
        }
    }

    int next = (g_key_head + 1) % MAX_KEYS;
    if (next == g_key_tail) {
        return mp_const_false;  // queue full: drop rather than overwrite
    }
    g_keys[g_key_head] = (uint16_t)((pressed ? 0x100 : 0) | (code & 0xFF));
    g_key_head = next;
    return mp_const_true;
}
static MP_DEFINE_CONST_FUN_OBJ_2(key_obj, key);

// poll_key(): (pressed<<8)|code, or -1 when the queue is empty.
static mp_obj_t poll_key(void) {
    if (g_key_tail == g_key_head) {
        return mp_obj_new_int(-1);
    }
    const int value = (int)g_keys[g_key_tail];
    g_key_tail = (g_key_tail + 1) % MAX_KEYS;
    return mp_obj_new_int(value);
}
static MP_DEFINE_CONST_FUN_OBJ_0(poll_key_obj, poll_key);

// ---- palette and pixel format conversion ----------------------------------

static inline uint16_t rgb888_to_rgb565(uint8_t r, uint8_t g, uint8_t b) {
    return (uint16_t)(((uint16_t)(r & 0xF8) << 8) |
                      ((uint16_t)(g & 0xFC) << 3) |
                      (b >> 3));
}

// expand8(src, palette, dst): 8-bit paletted frame, RGB888 palette, converted
// per pixel. This is the worst case an engine can hand a port.
static mp_obj_t expand8(mp_obj_t src_obj, mp_obj_t palette_obj, mp_obj_t dst_obj) {
    mp_buffer_info_t src;
    mp_buffer_info_t palette;
    mp_buffer_info_t dst;
    mp_get_buffer_raise(src_obj, &src, MP_BUFFER_READ);
    mp_get_buffer_raise(palette_obj, &palette, MP_BUFFER_READ);
    mp_get_buffer_raise(dst_obj, &dst, MP_BUFFER_WRITE);
    if (palette.len < 768) {
        mp_raise_ValueError("palette needs 768 bytes");
    }
    const size_t count = src.len / sizeof(uint8_t);
    if (dst.len / sizeof(uint16_t) < count) {
        mp_raise_ValueError("destination too small");
    }
    const uint8_t *pal = (const uint8_t *)palette.buf;
    const uint8_t *in = (const uint8_t *)src.buf;
    uint16_t *out = (uint16_t *)dst.buf;
    for (size_t i = 0; i < count; i++) {
        const uint8_t *rgb = pal + (size_t)in[i] * 3;
        out[i] = rgb888_to_rgb565(rgb[0], rgb[1], rgb[2]);
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_3(expand8_obj, expand8);

// set_palette(palette): build the RGB565 lookup table once, the way a ported
// renderer would when the palette changes.
static mp_obj_t set_palette(mp_obj_t palette_obj) {
    mp_buffer_info_t palette;
    mp_get_buffer_raise(palette_obj, &palette, MP_BUFFER_READ);
    if (palette.len < 768) {
        mp_raise_ValueError("palette needs 768 bytes");
    }
    const uint8_t *pal = (const uint8_t *)palette.buf;
    for (int i = 0; i < 256; i++) {
        g_palette_lut[i] = rgb888_to_rgb565(pal[i * 3], pal[i * 3 + 1],
                                            pal[i * 3 + 2]);
    }
    g_palette_valid = 1;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(set_palette_obj, set_palette);

// expand8_lut(src, dst): the same conversion through the prepared table.
static mp_obj_t expand8_lut(mp_obj_t src_obj, mp_obj_t dst_obj) {
    mp_buffer_info_t src;
    mp_buffer_info_t dst;
    mp_get_buffer_raise(src_obj, &src, MP_BUFFER_READ);
    mp_get_buffer_raise(dst_obj, &dst, MP_BUFFER_WRITE);
    if (!g_palette_valid) {
        mp_raise_ValueError("set_palette first");
    }
    const size_t count = src.len / sizeof(uint8_t);
    if (dst.len / sizeof(uint16_t) < count) {
        mp_raise_ValueError("destination too small");
    }
    const uint8_t *in = (const uint8_t *)src.buf;
    uint16_t *out = (uint16_t *)dst.buf;
    for (size_t i = 0; i < count; i++) {
        out[i] = g_palette_lut[in[i]];
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(expand8_lut_obj, expand8_lut);

// expand8_band(src, dst, band, rows): the same conversion for one band of rows.
//
// Presenting band by band means the SPI transfer of one band overlaps the
// conversion of the next, which a whole-frame conversion cannot do: the engine
// converts everything, then LVGL spends the whole frame pushing it out.
static mp_obj_t expand8_band(size_t n_args, const mp_obj_t *args) {
    (void)n_args;
    mp_buffer_info_t src;
    mp_buffer_info_t dst;
    mp_get_buffer_raise(args[0], &src, MP_BUFFER_READ);
    mp_get_buffer_raise(args[1], &dst, MP_BUFFER_WRITE);
    if (!g_palette_valid) {
        mp_raise_ValueError("set_palette first");
    }
    const size_t total = src.len;
    // `rows` is a row count: a band is rows*width pixels.
    const size_t width = (size_t)mp_obj_get_int(args[4]);
    const size_t start = (size_t)mp_obj_get_int(args[2]) *
                         (size_t)mp_obj_get_int(args[3]) * width;
    if (start >= total) {
        return mp_const_none;
    }
    size_t count = (size_t)mp_obj_get_int(args[3]) * width;
    if (start + count > total) {
        count = total - start;
    }
    if (dst.len / sizeof(uint16_t) < start + count) {
        mp_raise_ValueError("destination too small");
    }
    const uint8_t *in = (const uint8_t *)src.buf + start;
    uint16_t *out = (uint16_t *)dst.buf + start;
    for (size_t i = 0; i < count; i++) {
        out[i] = g_palette_lut[in[i]];
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(expand8_band_obj, 5, 5, expand8_band);

// expand32(src, dst): RGBA pixels, which is doomgeneric's default pixel_t.
static mp_obj_t expand32(mp_obj_t src_obj, mp_obj_t dst_obj) {
    mp_buffer_info_t src;
    mp_buffer_info_t dst;
    mp_get_buffer_raise(src_obj, &src, MP_BUFFER_READ);
    mp_get_buffer_raise(dst_obj, &dst, MP_BUFFER_WRITE);
    const size_t count = src.len / 4;
    if (dst.len / sizeof(uint16_t) < count) {
        mp_raise_ValueError("destination too small");
    }
    const uint8_t *in = (const uint8_t *)src.buf;
    uint16_t *out = (uint16_t *)dst.buf;
    for (size_t i = 0; i < count; i++) {
        out[i] = rgb888_to_rgb565(in[0], in[1], in[2]);
        in += 4;
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_2(expand32_obj, expand32);

// expand32_band(src, dst, band, rows): RGBA for one band of rows.
static mp_obj_t expand32_band(size_t n_args, const mp_obj_t *args) {
    (void)n_args;
    mp_buffer_info_t src;
    mp_buffer_info_t dst;
    mp_get_buffer_raise(args[0], &src, MP_BUFFER_READ);
    mp_get_buffer_raise(args[1], &dst, MP_BUFFER_WRITE);
    const size_t pixels = src.len / 4;
    const size_t width = (size_t)mp_obj_get_int(args[4]);
    const size_t start = (size_t)mp_obj_get_int(args[2]) *
                         (size_t)mp_obj_get_int(args[3]) * width;
    if (start >= pixels) {
        return mp_const_none;
    }
    size_t count = (size_t)mp_obj_get_int(args[3]) * width;
    if (start + count > pixels) {
        count = pixels - start;
    }
    if (dst.len / sizeof(uint16_t) < start + count) {
        mp_raise_ValueError("destination too small");
    }
    const uint8_t *in = (const uint8_t *)src.buf + start * 4;
    uint16_t *out = (uint16_t *)dst.buf + start;
    for (size_t i = 0; i < count; i++) {
        out[i] = rgb888_to_rgb565(in[0], in[1], in[2]);
        in += 4;
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(expand32_band_obj, 5, 5, expand32_band);

// fill_index(src): a paletted test source with every palette entry used.
static mp_obj_t fill_index(mp_obj_t src_obj) {
    mp_buffer_info_t src;
    mp_get_buffer_raise(src_obj, &src, MP_BUFFER_WRITE);
    uint8_t *p = (uint8_t *)src.buf;
    for (size_t i = 0; i < src.len; i++) {
        p[i] = (uint8_t)(i * 37u + (i >> 8));
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(fill_index_obj, fill_index);

// fill_rgbx(src): a 32-bit test source with a gradient.
static mp_obj_t fill_rgbx(mp_obj_t src_obj) {
    mp_buffer_info_t src;
    mp_get_buffer_raise(src_obj, &src, MP_BUFFER_WRITE);
    uint8_t *p = (uint8_t *)src.buf;
    for (size_t i = 0; i < src.len; i += 4) {
        p[0] = (uint8_t)i;
        p[1] = (uint8_t)(i >> 3);
        p[2] = (uint8_t)(i >> 6);
        p[3] = 0xFF;
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(fill_rgbx_obj, fill_rgbx);

// ---- the engine owning its framebuffer ------------------------------------

// alloc_framebuffer(width, height): the pixels live in the MicroPython heap and
// are handed to Python as a bytearray by reference, so NativeDisplay can wrap
// them with no copy. Engines that insist on their own framebuffer use this.
static mp_obj_t free_framebuffer(void);

static mp_obj_t alloc_framebuffer(mp_obj_t width_obj, mp_obj_t height_obj) {
    const size_t width = (size_t)mp_obj_get_int(width_obj);
    const size_t height = (size_t)mp_obj_get_int(height_obj);
    const size_t bytes = width * height * sizeof(uint16_t);
    if (bytes == 0) {
        mp_raise_ValueError("bad size");
    }
    if (g_owned != NULL) {
        // Freeing here would leave any bytearray Python already holds pointing
        // at released memory, so the previous buffer has to go first.
        mp_raise_ValueError("free_framebuffer first");
    }
    g_owned = (uint8_t *)m_malloc(bytes);
    g_owned_bytes = bytes;
    return mp_obj_new_bytearray_by_ref(bytes, g_owned);
}
static MP_DEFINE_CONST_FUN_OBJ_2(alloc_framebuffer_obj, alloc_framebuffer);

static mp_obj_t free_framebuffer(void) {
    if (g_owned != NULL) {
        m_free(g_owned);
        g_owned = NULL;
        g_owned_bytes = 0;
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(free_framebuffer_obj, free_framebuffer);

// ---- file access through Python ------------------------------------------

// The module cannot open a file: no filesystem API and no libc. A Python
// callable is passed once and implements "read n bytes at offset", so the app
// keeps one cached open/seek/readinto triple and the engine sees a lump read.
static mp_obj_t set_file_reader(mp_obj_t reader_obj) {
    g_file_reader = reader_obj;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(set_file_reader_obj, set_file_reader);

static mp_obj_t read_file(mp_obj_t path_obj, mp_obj_t offset_obj, mp_obj_t into_obj) {
    if (g_file_reader == NULL || g_file_reader == mp_const_none) {
        mp_raise_ValueError("no file reader set");
    }
    mp_buffer_info_t into;
    mp_get_buffer_raise(into_obj, &into, MP_BUFFER_WRITE);
    mp_obj_t args[3];
    args[0] = path_obj;
    args[1] = offset_obj;
    args[2] = into_obj;
    mp_obj_t result = mp_call_function_n_kw(g_file_reader, 3, 0, args);
    return result;
}
static MP_DEFINE_CONST_FUN_OBJ_3(read_file_obj, read_file);

// ---- observability --------------------------------------------------------

static mp_obj_t get_frames(void) {
    return mp_obj_new_int_from_uint(g_frames);
}
static MP_DEFINE_CONST_FUN_OBJ_0(get_frames_obj, get_frames);

static mp_obj_t get_box_x(void) {
    return mp_obj_new_int(g_box_x);
}
static MP_DEFINE_CONST_FUN_OBJ_0(get_box_x_obj, get_box_x);

static mp_obj_t get_box_y(void) {
    return mp_obj_new_int(g_box_y);
}
static MP_DEFINE_CONST_FUN_OBJ_0(get_box_y_obj, get_box_y);

static mp_obj_t big_checksum(void) {
    uint32_t sum = 0;
    uint32_t rodata_bytes = 0;
    uint32_t bss_bytes = 0;
#ifdef FRAMECORE_BIG
    // Touch both tables so neither can be dropped by the linker and so the
    // first frame after import pays for the pages being resident.
    for (size_t i = 0; i < sizeof(g_big_rodata) / sizeof(g_big_rodata[0]); i += 1024) {
        sum = (sum * 31u) + g_big_rodata[i];
        rodata_bytes += sizeof(g_big_rodata[0]);
    }
    for (size_t i = 0; i < sizeof(g_big_bss); i += 4096) {
        g_big_bss[i] = (unsigned char)(i & 0xFF);
        sum += g_big_bss[i];
        bss_bytes++;
    }
#else
    (void)sum;
#endif
    (void)rodata_bytes;
    (void)bss_bytes;
    return mp_obj_new_int_from_uint(sum);
}
static MP_DEFINE_CONST_FUN_OBJ_0(big_checksum_obj, big_checksum);

// This is the entry point and is called when the module is imported.
mp_obj_t mpy_init(mp_obj_fun_bc_t *self, size_t n_args, size_t n_kw, mp_obj_t *args) {
    // This must be first, it sets up the globals dict and other things
    MP_DYNRUNTIME_INIT_ENTRY

    mp_store_global(MP_QSTR_init, MP_OBJ_FROM_PTR(&probe_init_obj));
    mp_store_global(MP_QSTR_draw, MP_OBJ_FROM_PTR(&draw_obj));
    mp_store_global(MP_QSTR_key, MP_OBJ_FROM_PTR(&key_obj));
    mp_store_global(MP_QSTR_poll_key, MP_OBJ_FROM_PTR(&poll_key_obj));
    mp_store_global(MP_QSTR_expand8, MP_OBJ_FROM_PTR(&expand8_obj));
    mp_store_global(MP_QSTR_set_palette, MP_OBJ_FROM_PTR(&set_palette_obj));
    mp_store_global(MP_QSTR_expand8_lut, MP_OBJ_FROM_PTR(&expand8_lut_obj));
    mp_store_global(MP_QSTR_expand32, MP_OBJ_FROM_PTR(&expand32_obj));
    mp_store_global(MP_QSTR_expand8_band, MP_OBJ_FROM_PTR(&expand8_band_obj));
    mp_store_global(MP_QSTR_expand32_band, MP_OBJ_FROM_PTR(&expand32_band_obj));
    mp_store_global(MP_QSTR_fill_index, MP_OBJ_FROM_PTR(&fill_index_obj));
    mp_store_global(MP_QSTR_fill_rgbx, MP_OBJ_FROM_PTR(&fill_rgbx_obj));
    mp_store_global(MP_QSTR_alloc_framebuffer, MP_OBJ_FROM_PTR(&alloc_framebuffer_obj));
    mp_store_global(MP_QSTR_free_framebuffer, MP_OBJ_FROM_PTR(&free_framebuffer_obj));
    mp_store_global(MP_QSTR_set_file_reader, MP_OBJ_FROM_PTR(&set_file_reader_obj));
    mp_store_global(MP_QSTR_read_file, MP_OBJ_FROM_PTR(&read_file_obj));
    mp_store_global(MP_QSTR_get_frames, MP_OBJ_FROM_PTR(&get_frames_obj));
    mp_store_global(MP_QSTR_get_box_x, MP_OBJ_FROM_PTR(&get_box_x_obj));
    mp_store_global(MP_QSTR_get_box_y, MP_OBJ_FROM_PTR(&get_box_y_obj));
    mp_store_global(MP_QSTR_big_checksum, MP_OBJ_FROM_PTR(&big_checksum_obj));

    mp_store_global(MP_QSTR_KEY_LEFT, MP_OBJ_NEW_SMALL_INT(1));
    mp_store_global(MP_QSTR_KEY_RIGHT, MP_OBJ_NEW_SMALL_INT(2));
    mp_store_global(MP_QSTR_KEY_UP, MP_OBJ_NEW_SMALL_INT(3));
    mp_store_global(MP_QSTR_KEY_DOWN, MP_OBJ_NEW_SMALL_INT(4));

    // This must be last, it restores the globals dict
    MP_DYNRUNTIME_INIT_EXIT
}
