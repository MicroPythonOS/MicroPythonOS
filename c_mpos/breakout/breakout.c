// Breakout native module renderer. Draws into a framebuffer that may be
// smaller than the full display (partial framebuffer). Rendering is done
// per-slice using a y-offset/row count so MicroPythonOS can refresh displays
// larger than 320x230 without allocating a full-size framebuffer. This keeps
// the simulation state global while allowing sequential chunk flushes.

// Include the header file to get access to the MicroPython API
#include "py/dynruntime.h"
#include <stdbool.h>

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
size_t g_framebuffer_max_pixels;
size_t g_render_y_offset;
size_t g_render_height;

int g_paddle_x;
int g_paddle_width;
int g_paddle_height;
float g_ball_x;
float g_ball_y;
float g_ball_vx;
float g_ball_vy;
float g_ball_speed;
uint32_t g_last_tick_ms;

uint32_t g_fps_last_ms;
uint32_t g_fps_frames;

int g_score;
int g_highscore;
int g_level;
int g_lives;
int g_game_over;
uint32_t g_game_over_until;

#define BRICK_ROWS 12
#define BRICK_COLS 8
#define BALL_SIZE 3
#define MAX_STRENGTH 5
uint8_t g_brick_max[BRICK_ROWS][BRICK_COLS];
uint8_t g_brick_hits[BRICK_ROWS][BRICK_COLS];
int g_bricks_remaining;

// Per-strength base colors (RGB565). Hue encodes the original strength.
#define COLOR_1 0xF800  // red
#define COLOR_2 0xFC00  // orange
#define COLOR_3 0xFFE0  // yellow
#define COLOR_4 0x07E0  // green
#define COLOR_5 0x001F  // blue

#define BASE_BALL_SPEED 120.0f
#define SPEED_STEP 6.0f
#define MAX_BALL_SPEED 240.0f
#define BASE_PADDLE_DIV 5
#define MIN_PADDLE_DIV 8
#define PADDLE_STEP_DIV 40

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
    return g_framebuffer_max_pixels;
}

static void draw_rect(int x, int y, int w, int h, uint16_t color) {
    if (w <= 0 || h <= 0 || g_framebuffer == NULL) {
        return;
    }

    const int x0 = (x < 0) ? 0 : x;
    const int y0 = (y < 0) ? 0 : y;
    const int x1 = x + w;
    const int y1 = y + h;

    const int max_x = (int)g_framebuffer_width;
    const int max_y = (int)g_framebuffer_height;

    int clip_x0 = x0;
    int clip_y0 = y0;
    int clip_x1 = (x1 > max_x) ? max_x : x1;
    int clip_y1 = (y1 > max_y) ? max_y : y1;

    const int slice_y0 = (int)g_render_y_offset;
    const int slice_y1 = (int)(g_render_y_offset + g_render_height);
    if (clip_y0 < slice_y0) {
        clip_y0 = slice_y0;
    }
    if (clip_y1 > slice_y1) {
        clip_y1 = slice_y1;
    }

    if (clip_x0 >= clip_x1 || clip_y0 >= clip_y1) {
        return;
    }

    const size_t width = g_framebuffer_width;
    const size_t fill_width = (size_t)(clip_x1 - clip_x0);

    for (int yy = clip_y0; yy < clip_y1; yy++) {
        const size_t local_y = (size_t)(yy - (int)g_render_y_offset);
        uint16_t *row = g_framebuffer + local_y * width + (size_t)clip_x0;
        for (size_t xx = 0; xx < fill_width; xx++) {
            row[xx] = color;
        }
    }
}

static uint16_t base_color_for_strength(uint8_t strength) {
    switch (strength) {
        case 1:
            return COLOR_1;
        case 2:
            return COLOR_2;
        case 3:
            return COLOR_3;
        case 4:
            return COLOR_4;
        default:
            return COLOR_5;
    }
}

static uint16_t dim_color(uint16_t base, uint8_t hits, uint8_t max_hits) {
    if (max_hits == 0 || hits == 0) {
        return base;
    }
    uint8_t r = (base >> 11) & 0x1F;
    uint8_t g = (base >> 5) & 0x3F;
    uint8_t b = base & 0x1F;
    r = (uint8_t)((r * hits) / max_hits);
    g = (uint8_t)((g * hits) / max_hits);
    b = (uint8_t)((b * hits) / max_hits);
    return (uint16_t)((r << 11) | (g << 5) | b);
}

static uint16_t brick_color(uint8_t max_hits, uint8_t remaining_hits) {
    uint16_t base = base_color_for_strength(max_hits);
    return dim_color(base, remaining_hits, max_hits);
}

static void reset_ball(void) {
    if (g_framebuffer_width == 0 || g_framebuffer_height == 0) {
        return;
    }
    g_ball_x = (float)((int)g_framebuffer_width / 2);
    g_ball_y = (float)((int)g_framebuffer_height / 2);
    g_ball_vx = g_ball_speed;
    g_ball_vy = -g_ball_speed;
}

// Simple linear congruential generator.
static uint32_t lcg_next(uint32_t *state) {
    *state = *state * 1103515245u + 12345u;
    return *state;
}

#define PATTERN_FULL 0
#define PATTERN_HSTRIPES 1
#define PATTERN_VSTRIPES 2
#define PATTERN_X 3
#define PATTERN_CIRCLE 4
#define PATTERN_CHECKER 5
#define PATTERN_BORDER 6
#define PATTERN_RANDOM 7
#define NUM_PATTERNS 8

static bool pattern_present(int row, int col, int pattern, uint32_t *rng_state) {
    switch (pattern) {
        case PATTERN_FULL:
            return true;
        case PATTERN_HSTRIPES:
            return (row % 2) == 0;
        case PATTERN_VSTRIPES:
            return (col % 2) == 0;
        case PATTERN_X:
            return (row == col) || (row + col == BRICK_COLS - 1);
        case PATTERN_CIRCLE: {
            const int cx = BRICK_COLS / 2;
            const int cy = BRICK_ROWS / 2;
            int dx = col - cx;
            int dy = row - cy;
            return (dx * dx + dy * dy) <= 7;
        }
        case PATTERN_CHECKER:
            return ((row + col) % 2) == 0;
        case PATTERN_BORDER:
            return (row == 0) || (row == BRICK_ROWS - 1) || (col == 0) || (col == BRICK_COLS - 1);
        case PATTERN_RANDOM:
        default:
            return (lcg_next(rng_state) & 0x1) != 0;
    }
}

static void generate_level(int level) {
    if (g_framebuffer_width == 0 || g_framebuffer_height == 0) {
        return;
    }

    g_level = level;
    g_game_over = 0;
    g_game_over_until = 0;

    g_ball_speed = BASE_BALL_SPEED + ((float)(level - 1)) * SPEED_STEP;
    if (g_ball_speed > MAX_BALL_SPEED) {
        g_ball_speed = MAX_BALL_SPEED;
    }

    int base_width = (int)g_framebuffer_width / BASE_PADDLE_DIV;
    int min_width = (int)g_framebuffer_width / MIN_PADDLE_DIV;
    int step = (int)g_framebuffer_width / PADDLE_STEP_DIV;
    g_paddle_width = base_width - (level - 1) * step;
    if (g_paddle_width < min_width) {
        g_paddle_width = min_width;
    }
    g_paddle_height = 4;
    g_paddle_x = ((int)g_framebuffer_width - g_paddle_width) / 2;

    // Seed from level and current time for variety.
    uint32_t rng_state = (uint32_t)ticks_ms() ^ ((uint32_t)level * 0x9E3779B9u);
    int pattern = (int)(lcg_next(&rng_state) % NUM_PATTERNS);

    memset(g_brick_max, 0, sizeof(g_brick_max));
    memset(g_brick_hits, 0, sizeof(g_brick_hits));
    g_bricks_remaining = 0;

    for (int row = 0; row < BRICK_ROWS; row++) {
        for (int col = 0; col < BRICK_COLS; col++) {
            if (!pattern_present(row, col, pattern, &rng_state)) {
                continue;
            }
            uint8_t strength = (uint8_t)(1 + (row / 4) + ((level - 1) / 3));
            if (strength > MAX_STRENGTH) {
                strength = MAX_STRENGTH;
            } else if (strength < 1) {
                strength = 1;
            }
            g_brick_max[row][col] = strength;
            g_brick_hits[row][col] = strength;
            g_bricks_remaining++;
        }
    }

    reset_ball();
}

static void level_up(void) {
    g_score += g_level * 50 + g_lives * 20;
    g_level++;
    g_lives = 5;
    generate_level(g_level);
}

static mp_obj_t new_game(void);

// init(framebuffer, width, height): store a reference to the framebuffer and dimensions.
static mp_obj_t init(mp_obj_t framebuffer_obj, mp_obj_t width_obj, mp_obj_t height_obj) {
    mp_buffer_info_t bufinfo;
    mp_get_buffer_raise(framebuffer_obj, &bufinfo, MP_BUFFER_WRITE);

    g_framebuffer = (uint16_t *)bufinfo.buf;
    g_framebuffer_len = bufinfo.len;
    g_framebuffer_width = (size_t)mp_obj_get_int(width_obj);
    g_framebuffer_height = (size_t)mp_obj_get_int(height_obj);
    const size_t max_pixels = g_framebuffer_len / sizeof(uint16_t);
    const size_t total_pixels = g_framebuffer_width * g_framebuffer_height;
    g_framebuffer_max_pixels = (max_pixels < total_pixels) ? max_pixels : total_pixels;
    g_render_y_offset = 0;
    g_render_height = g_framebuffer_height;

    g_score = 0;
    g_level = 1;
    g_lives = 5;
    g_game_over = 0;
    g_game_over_until = 0;

    generate_level(1);

    g_fps_last_ms = ticks_ms();
    g_fps_frames = 0;
    g_last_tick_ms = g_fps_last_ms;

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_3(init_obj, init);

// render([y_offset, rows, advance]): draw a Breakout frame slice and optionally advance simulation.
static mp_obj_t render(size_t n_args, const mp_obj_t *args) {
    if (g_framebuffer == NULL || g_framebuffer_width == 0 || g_framebuffer_height == 0) {
        return mp_const_none;
    }

    const size_t width = g_framebuffer_width;
    const size_t height = g_framebuffer_height;

    size_t render_y_offset = 0;
    size_t render_rows = height;
    bool advance = true;
    if (n_args >= 1) {
        int y_offset_arg = mp_obj_get_int(args[0]);
        if (y_offset_arg > 0) {
            render_y_offset = (size_t)y_offset_arg;
        }
    }
    if (n_args >= 2) {
        int rows_arg = mp_obj_get_int(args[1]);
        if (rows_arg > 0) {
            render_rows = (size_t)rows_arg;
        }
    }
    if (n_args >= 3) {
        advance = mp_obj_is_true(args[2]);
    } else {
        advance = (render_y_offset == 0);
    }

    if (render_y_offset >= height) {
        return mp_const_none;
    }

    const size_t max_rows_by_buf = (width > 0) ? (framebuffer_max_pixels() / width) : 0;
    const size_t max_rows_by_height = height - render_y_offset;
    if (render_rows > max_rows_by_height) {
        render_rows = max_rows_by_height;
    }
    if (max_rows_by_buf > 0 && render_rows > max_rows_by_buf) {
        render_rows = max_rows_by_buf;
    }
    if (render_rows == 0) {
        return mp_const_none;
    }

    g_render_y_offset = render_y_offset;
    g_render_height = render_rows;

    // Clear to black.
    const size_t fill_pixels = width * render_rows;
    memset(g_framebuffer, 0, fill_pixels * sizeof(uint16_t));

    const int paddle_y = (int)height - g_paddle_height - 4;

    if (advance && !g_game_over && g_lives > 0) {
        g_fps_frames++;
        const uint32_t now_ms = ticks_ms();
        const uint32_t elapsed_ms = now_ms - g_fps_last_ms;
        if (elapsed_ms >= 1000) {
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
            g_ball_vx = g_ball_speed;
        } else if (g_ball_x >= (float)width - 1.0f) {
            g_ball_x = (float)width - 1.0f;
            g_ball_vx = -g_ball_speed;
        }

        if (g_ball_y <= 0.0f) {
            g_ball_y = 0.0f;
            g_ball_vy = g_ball_speed;
        }

        // Brick collision.
        const int brick_gap = 2;
        const int brick_height = 6;
        const int brick_area_width = (int)width - (brick_gap * (BRICK_COLS + 1));
        const int brick_width = (brick_area_width > 0) ? (brick_area_width / BRICK_COLS) : 0;
        const int brick_offset_y = 10;

        if (brick_width > 0 && g_ball_y <= (float)(brick_offset_y + BRICK_ROWS * (brick_height + brick_gap))) {
            for (int row = 0; row < BRICK_ROWS; row++) {
                for (int col = 0; col < BRICK_COLS; col++) {
                    if (g_brick_hits[row][col] == 0) {
                        continue;
                    }
                    const int bx = brick_gap + col * (brick_width + brick_gap);
                    const int by = brick_offset_y + row * (brick_height + brick_gap);
                    if (g_ball_x >= (float)bx && g_ball_x < (float)(bx + brick_width) &&
                            g_ball_y >= (float)by && g_ball_y < (float)(by + brick_height)) {
                        // Weaken the brick.
                        g_brick_hits[row][col]--;
                        g_score += 5;
                        if (g_brick_hits[row][col] == 0) {
                            uint8_t max_hits = g_brick_max[row][col];
                            if (max_hits > MAX_STRENGTH) {
                                max_hits = MAX_STRENGTH;
                            }
                            g_score += (int)max_hits * 10;
                            g_bricks_remaining--;
                        }
                        g_ball_vy = -g_ball_vy;
                        row = BRICK_ROWS;
                        break;
                    }
                }
            }
        }

        // Paddle collision with angle control based on hit position.
        if (g_ball_y >= (float)(paddle_y - 1) && g_ball_y <= (float)(paddle_y + g_paddle_height)) {
            if (g_ball_x >= (float)g_paddle_x && g_ball_x <= (float)(g_paddle_x + g_paddle_width)) {
                g_ball_y = (float)(paddle_y - 1);
                g_ball_vy = -g_ball_speed;
                float hit_offset = (g_ball_x - ((float)g_paddle_x + (float)g_paddle_width / 2.0f)) /
                                  ((float)g_paddle_width / 2.0f);
                if (hit_offset < -1.0f) {
                    hit_offset = -1.0f;
                } else if (hit_offset > 1.0f) {
                    hit_offset = 1.0f;
                }
                g_ball_vx = hit_offset * g_ball_speed;
            }
        }

        // Ball fell below paddle.
        if (g_ball_y >= (float)((int)height - 1)) {
            g_lives--;
            if (g_lives > 0) {
                reset_ball();
            } else {
                g_game_over = 1;
                g_game_over_until = ticks_ms() + 5000;
                g_ball_vx = 0.0f;
                g_ball_vy = 0.0f;
            }
        }

        if (g_bricks_remaining <= 0) {
            level_up();
        }
    }

    // Auto-restart a few seconds after game over.
    if (g_game_over) {
        uint32_t now_ms = ticks_ms();
        if ((int32_t)(now_ms - g_game_over_until) >= 0) {
            new_game();
        }
    }

    // Brick layout.
    const int brick_gap = 2;
    const int brick_height = 6;
    const int brick_area_width = (int)width - (brick_gap * (BRICK_COLS + 1));
    const int brick_width = (brick_area_width > 0) ? (brick_area_width / BRICK_COLS) : 0;
    const int brick_offset_y = 10;

    // Draw bricks.
    if (brick_width > 0) {
        for (int row = 0; row < BRICK_ROWS; row++) {
            for (int col = 0; col < BRICK_COLS; col++) {
                uint8_t remaining = g_brick_hits[row][col];
                if (remaining == 0) {
                    continue;
                }
                uint8_t max_hits = g_brick_max[row][col];
                if (max_hits == 0) {
                    continue;
                }
                const int bx = brick_gap + col * (brick_width + brick_gap);
                const int by = brick_offset_y + row * (brick_height + brick_gap);
                draw_rect(bx, by, brick_width, brick_height, brick_color(max_hits, remaining));
            }
        }
    }

    // Draw paddle and ball.
    draw_rect(g_paddle_x, paddle_y, g_paddle_width, g_paddle_height, 0xFFFF); // RGB565 white
    const int ball_draw_x = (int)g_ball_x - (BALL_SIZE / 2);
    const int ball_draw_y = (int)g_ball_y - (BALL_SIZE / 2);
    draw_rect(ball_draw_x, ball_draw_y, BALL_SIZE, BALL_SIZE, 0xFFFF);

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(render_obj, 0, 3, render);

// move_paddle(delta): move the paddle horizontally by delta.
static mp_obj_t move_paddle(mp_obj_t delta_obj) {
    int delta = mp_obj_get_int(delta_obj);
    if (g_framebuffer_width > 0 && !g_game_over) {
        g_paddle_x = clamp_int(g_paddle_x + delta, 0, (int)g_framebuffer_width - g_paddle_width);
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(move_paddle_obj, move_paddle);

static mp_obj_t get_score(void) { return mp_obj_new_int(g_score); }
static MP_DEFINE_CONST_FUN_OBJ_0(get_score_obj, get_score);

static mp_obj_t get_highscore(void) { return mp_obj_new_int(g_highscore); }
static MP_DEFINE_CONST_FUN_OBJ_0(get_highscore_obj, get_highscore);

static mp_obj_t set_highscore(mp_obj_t value_obj) {
    g_highscore = mp_obj_get_int(value_obj);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(set_highscore_obj, set_highscore);

static mp_obj_t get_level(void) { return mp_obj_new_int(g_level); }
static MP_DEFINE_CONST_FUN_OBJ_0(get_level_obj, get_level);

static mp_obj_t get_lives(void) { return mp_obj_new_int(g_lives); }
static MP_DEFINE_CONST_FUN_OBJ_0(get_lives_obj, get_lives);

static mp_obj_t is_game_over(void) { return mp_obj_new_bool(g_game_over); }
static MP_DEFINE_CONST_FUN_OBJ_0(is_game_over_obj, is_game_over);

static mp_obj_t set_score(mp_obj_t value_obj) {
    g_score = mp_obj_get_int(value_obj);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(set_score_obj, set_score);

static mp_obj_t set_lives(mp_obj_t value_obj) {
    g_lives = mp_obj_get_int(value_obj);
    if (g_lives < 0) {
        g_lives = 0;
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(set_lives_obj, set_lives);

static mp_obj_t new_game(void) {
    g_score = 0;
    g_level = 1;
    g_lives = 5;
    g_game_over = 0;
    g_game_over_until = 0;
    generate_level(1);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(new_game_obj, new_game);

static mp_obj_t set_level(mp_obj_t value_obj) {
    int level = mp_obj_get_int(value_obj);
    if (level < 1) {
        level = 1;
    }
    g_game_over = 0;
    generate_level(level);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(set_level_obj, set_level);

// This is the entry point and is called when the module is imported
mp_obj_t mpy_init(mp_obj_fun_bc_t *self, size_t n_args, size_t n_kw, mp_obj_t *args) {
    // This must be first, it sets up the globals dict and other things
    MP_DYNRUNTIME_INIT_ENTRY

    // Make the function available in the module's namespace
    mp_store_global(MP_QSTR_init, MP_OBJ_FROM_PTR(&init_obj));
    mp_store_global(MP_QSTR_render, MP_OBJ_FROM_PTR(&render_obj));
    mp_store_global(MP_QSTR_move_paddle, MP_OBJ_FROM_PTR(&move_paddle_obj));
    mp_store_global(MP_QSTR_get_score, MP_OBJ_FROM_PTR(&get_score_obj));
    mp_store_global(MP_QSTR_get_highscore, MP_OBJ_FROM_PTR(&get_highscore_obj));
    mp_store_global(MP_QSTR_set_highscore, MP_OBJ_FROM_PTR(&set_highscore_obj));
    mp_store_global(MP_QSTR_get_level, MP_OBJ_FROM_PTR(&get_level_obj));
    mp_store_global(MP_QSTR_get_lives, MP_OBJ_FROM_PTR(&get_lives_obj));
    mp_store_global(MP_QSTR_is_game_over, MP_OBJ_FROM_PTR(&is_game_over_obj));
    mp_store_global(MP_QSTR_set_score, MP_OBJ_FROM_PTR(&set_score_obj));
    mp_store_global(MP_QSTR_set_lives, MP_OBJ_FROM_PTR(&set_lives_obj));
    mp_store_global(MP_QSTR_new_game, MP_OBJ_FROM_PTR(&new_game_obj));
    mp_store_global(MP_QSTR_set_level, MP_OBJ_FROM_PTR(&set_level_obj));

    // This must be last, it restores the globals dict
    MP_DYNRUNTIME_INIT_EXIT
}
