// Include the header file to get access to the MicroPython API
#include "py/dynruntime.h"

// Provide a local memset for xtensawin native modules (libc isn't linked).
void *memset(void *s, int c, size_t n) {
    unsigned char *p = (unsigned char *)s;
    while (n--) {
        *p++ = (unsigned char)c;
    }
    return s;
}

// Global BSS (non-static) state is required for native modules.
uint16_t *g_framebuffer;
size_t g_framebuffer_len;
size_t g_framebuffer_width;
size_t g_framebuffer_height;

int g_paddle_x;
int g_paddle_width;
int g_paddle_height;
float g_ball_x;
float g_ball_y;
float g_ball_vx;
float g_ball_vy;
uint32_t g_last_tick_ms;

uint32_t g_fps_last_ms;
uint32_t g_fps_frames;

#define BRICK_ROWS 4
#define BRICK_COLS 8
uint8_t g_bricks[BRICK_ROWS][BRICK_COLS];

// readfile(filename): return first 10 bytes of a file as bytes
static mp_obj_t readfile(mp_obj_t filename_obj) {
    mp_obj_t open_fun = mp_load_global(MP_QSTR_open);
    mp_obj_t open_args[2] = { filename_obj, mp_obj_new_str("rb", 2) };
    mp_obj_t file_obj = mp_call_function_n_kw(open_fun, 2, 0, open_args);

    mp_obj_t read_fun = mp_load_attr(file_obj, MP_QSTR_read);
    mp_obj_t read_args[1] = { mp_obj_new_int(10) };
    mp_obj_t data_obj = mp_call_function_n_kw(read_fun, 1, 0, read_args);

    mp_obj_t close_fun = mp_load_attr(file_obj, MP_QSTR_close);
    mp_obj_t close_args[1];
    mp_call_function_n_kw(close_fun, 0, 0, close_args);

    return data_obj;
}
static MP_DEFINE_CONST_FUN_OBJ_1(readfile_obj, readfile);

static uint32_t ticks_ms(void) {
    mp_obj_t time_mod = mp_import_name(MP_QSTR_time, mp_const_none, MP_OBJ_NEW_SMALL_INT(0));
    mp_obj_t ticks_fun = mp_load_attr(time_mod, MP_QSTR_ticks_ms);
    mp_obj_t ticks_val = mp_call_function_n_kw(ticks_fun, 0, 0, NULL);
    return (uint32_t)mp_obj_get_int(ticks_val);
}

static inline int clamp_int(int value, int min_value, int max_value) {
    if (value < min_value) {
        return min_value;
    }
    if (value > max_value) {
        return max_value;
    }
    return value;
}

static inline size_t framebuffer_max_pixels(void) {
    const size_t max_pixels = g_framebuffer_len / sizeof(uint16_t);
    const size_t total_pixels = g_framebuffer_width * g_framebuffer_height;
    return (max_pixels < total_pixels) ? max_pixels : total_pixels;
}

static void draw_pixel(int x, int y, uint16_t color) {
    if (x < 0 || y < 0) {
        return;
    }
    if ((size_t)x >= g_framebuffer_width || (size_t)y >= g_framebuffer_height) {
        return;
    }
    const size_t idx = (size_t)y * g_framebuffer_width + (size_t)x;
    const size_t max_pixels = framebuffer_max_pixels();
    if (idx >= max_pixels) {
        return;
    }
    g_framebuffer[idx] = color;
}

static void draw_rect(int x, int y, int w, int h, uint16_t color) {
    if (w <= 0 || h <= 0) {
        return;
    }
    for (int yy = 0; yy < h; yy++) {
        for (int xx = 0; xx < w; xx++) {
            draw_pixel(x + xx, y + yy, color);
        }
    }
}

static void reset_ball(void) {
    g_ball_x = (float)((int)g_framebuffer_width / 2);
    g_ball_y = (float)((int)g_framebuffer_height / 2);
    g_ball_vx = 120.0f;
    g_ball_vy = -120.0f;
}

static void reset_bricks(void) {
    for (int row = 0; row < BRICK_ROWS; row++) {
        for (int col = 0; col < BRICK_COLS; col++) {
            g_bricks[row][col] = 1;
        }
    }
}

// init(framebuffer, width, height): store a reference to the framebuffer and dimensions.
static mp_obj_t init(mp_obj_t framebuffer_obj, mp_obj_t width_obj, mp_obj_t height_obj) {
    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(framebuffer_obj, &bufinfo, MP_BUFFER_WRITE);

    g_framebuffer = (uint16_t *)bufinfo.buf;
    g_framebuffer_len = bufinfo.len;
    g_framebuffer_width = (size_t)mp_obj_get_int(width_obj);
    g_framebuffer_height = (size_t)mp_obj_get_int(height_obj);

    g_paddle_width = (int)g_framebuffer_width / 5;
    g_paddle_height = 4;
    g_paddle_x = ((int)g_framebuffer_width - g_paddle_width) / 2;

    reset_ball();
    reset_bricks();

    g_fps_last_ms = ticks_ms();
    g_fps_frames = 0;
    g_last_tick_ms = g_fps_last_ms;

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_3(init_obj, init);

// render(): draw a simple Breakout-style frame and advance the game simulation.
static mp_obj_t render(void) {
    if (g_framebuffer == NULL || g_framebuffer_width == 0 || g_framebuffer_height == 0) {
        return mp_const_none;
    }

    const size_t width = g_framebuffer_width;
    const size_t height = g_framebuffer_height;
    const size_t fill_pixels = framebuffer_max_pixels();

    // Clear to black.
    for (size_t i = 0; i < fill_pixels; i++) { g_framebuffer[i] = 0x0000; } // RGB565 black

    g_fps_frames++;
    const uint32_t now_ms = ticks_ms();
    const uint32_t elapsed_ms = now_ms - g_fps_last_ms;
    if (elapsed_ms >= 1000) {
        const uint32_t fps = (g_fps_frames * 1000) / elapsed_ms;
        mp_printf(&mp_plat_print, "mpong fps: %lu\n", (unsigned long)fps);
        g_fps_last_ms = now_ms;
        g_fps_frames = 0;
    }

    uint32_t tick_delta_ms = now_ms - g_last_tick_ms;
    g_last_tick_ms = now_ms;
    if (tick_delta_ms > 50) {
        tick_delta_ms = 50;
    }
    const float dt = (float)tick_delta_ms / 1000.0f;

    // Update ball position.
    g_ball_x += g_ball_vx * dt;
    g_ball_y += g_ball_vy * dt;

    // Wall collisions.
    if (g_ball_x <= 0.0f) {
        g_ball_x = 0.0f;
        g_ball_vx = 120.0f;
    } else if (g_ball_x >= (float)width - 1.0f) {
        g_ball_x = (float)width - 1.0f;
        g_ball_vx = -120.0f;
    }

    if (g_ball_y <= 0.0f) {
        g_ball_y = 0.0f;
        g_ball_vy = 120.0f;
    }

    // Brick layout.
    const int brick_gap = 2;
    const int brick_rows = BRICK_ROWS;
    const int brick_cols = BRICK_COLS;
    const int brick_height = 6;
    const int brick_area_width = (int)width - (brick_gap * (brick_cols + 1));
    const int brick_width = (brick_area_width > 0) ? (brick_area_width / brick_cols) : 0;
    const int brick_offset_y = 8;

    // Brick collision.
    if (brick_width > 0 && g_ball_y <= (float)(brick_offset_y + brick_rows * (brick_height + brick_gap))) {
        for (int row = 0; row < brick_rows; row++) {
            for (int col = 0; col < brick_cols; col++) {
                if (!g_bricks[row][col]) {
                    continue;
                }
                const int bx = brick_gap + col * (brick_width + brick_gap);
                const int by = brick_offset_y + row * (brick_height + brick_gap);
                if (g_ball_x >= (float)bx && g_ball_x < (float)(bx + brick_width) && g_ball_y >= (float)by && g_ball_y < (float)(by + brick_height)) {
                    g_bricks[row][col] = 0;
                    g_ball_vy = -g_ball_vy;
                    row = brick_rows;
                    break;
                }
            }
        }
    }

    // Paddle collision.
    const int paddle_y = (int)height - g_paddle_height - 4;
    if (g_ball_y >= (float)(paddle_y - 1) && g_ball_y <= (float)(paddle_y + g_paddle_height)) {
        if (g_ball_x >= (float)g_paddle_x && g_ball_x <= (float)(g_paddle_x + g_paddle_width)) {
            g_ball_y = (float)(paddle_y - 1);
            g_ball_vy = -120.0f;
            const int paddle_center = g_paddle_x + g_paddle_width / 2;
            if (g_ball_x < (float)paddle_center) {
                g_ball_vx = -120.0f;
            } else if (g_ball_x > (float)paddle_center) {
                g_ball_vx = 120.0f;
            }
        }
    }

    // Ball fell below paddle: reset.
    if (g_ball_y >= (float)((int)height - 1)) {
        reset_ball();
    }

    // Draw bricks.
    if (brick_width > 0) {
        for (int row = 0; row < brick_rows; row++) {
            for (int col = 0; col < brick_cols; col++) {
                if (!g_bricks[row][col]) {
                    continue;
                }
                const int bx = brick_gap + col * (brick_width + brick_gap);
                const int by = brick_offset_y + row * (brick_height + brick_gap);
                draw_rect(bx, by, brick_width, brick_height, 0xF800); // RGB565 red
            }
        }
    }

    // Draw paddle and ball.
    draw_rect(g_paddle_x, paddle_y, g_paddle_width, g_paddle_height, 0xFFFF); // RGB565 white
    draw_pixel((int)g_ball_x, (int)g_ball_y, 0xFFFF);

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(render_obj, render);

// move_paddle(delta): move the paddle horizontally by delta.
static mp_obj_t move_paddle(mp_obj_t delta_obj) {
    int delta = mp_obj_get_int(delta_obj);
    //mp_printf(&mp_plat_print, "delta: %d\n", delta);
    if (g_framebuffer_width > 0) {
        g_paddle_x = clamp_int(g_paddle_x + delta, 0, (int)g_framebuffer_width - g_paddle_width);
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(move_paddle_obj, move_paddle);

// This is the entry point and is called when the module is imported
mp_obj_t mpy_init(mp_obj_fun_bc_t *self, size_t n_args, size_t n_kw, mp_obj_t *args) {
    // This must be first, it sets up the globals dict and other things
    MP_DYNRUNTIME_INIT_ENTRY

    // Make the function available in the module's namespace
    mp_store_global(MP_QSTR_init, MP_OBJ_FROM_PTR(&init_obj));
    mp_store_global(MP_QSTR_render, MP_OBJ_FROM_PTR(&render_obj));
    mp_store_global(MP_QSTR_move_paddle, MP_OBJ_FROM_PTR(&move_paddle_obj));
    mp_store_global(MP_QSTR_readfile, MP_OBJ_FROM_PTR(&readfile_obj));

    // This must be last, it restores the globals dict
    MP_DYNRUNTIME_INIT_EXIT
}
