// Breakout native module: gameplay state and a dirty-band 2D renderer.
//
// The display is driven by mpos.ui.native_display.NativeDisplay: this module
// owns one RGB565 buffer and draws the bands of rows whose pixels changed into
// it. LVGL then blits and flushes exactly those bands, so a frame that moves
// the ball and the paddle costs two bands instead of a full screen.
//
// The contract with the Python side is:
//   tick(now_ms)        advance the simulation to now_ms and mark dirty bands
//   next_dirty()        first band that still needs drawing, or -1
//   render_band(b)      draw band b into the buffer; clears its dirty flag
//
// Nothing here reads the clock itself: the caller owns the clock, which keeps a
// frame's cost independent of how long a module-level `import` happens to take.

#include "py/dynruntime.h"
#include <stdbool.h>

// libc isn't linked into xtensawin native modules, so the two functions the
// compiler emits calls to are provided here. Word-wise is a lot cheaper than
// byte-wise for the band clear, which runs once per drawn band.
void *memset(void *s, int c, size_t n) {
    unsigned char *p = (unsigned char *)s;
    uint32_t word = (uint32_t)c & 0xFF;
    word |= word << 8;
    word |= word << 16;
    while (n >= 4) {
        *(uint32_t *)p = word;
        p += 4;
        n -= 4;
    }
    while (n--) {
        *p++ = (unsigned char)c;
    }
    return s;
}

void *memcpy(void *dst, const void *src, size_t n) {
    unsigned char *d = (unsigned char *)dst;
    const unsigned char *s = (const unsigned char *)src;
    while (n--) {
        *d++ = *s++;
    }
    return dst;
}

#define MAX_BANDS 64

// Global BSS (non-static) state is required for native modules.
uint16_t *g_target;
size_t g_target_pixels;
size_t g_render_y_offset;
size_t g_render_rows;
size_t g_framebuffer_width;
size_t g_framebuffer_height;
size_t g_band_rows;
size_t g_band_count;
uint32_t g_band_dirty[MAX_BANDS];

int g_paddle_x;
int g_paddle_width;
int g_paddle_height;
float g_ball_x;
float g_ball_y;
float g_ball_vx;
float g_ball_vy;
float g_ball_speed;
bool g_has_clock;
uint32_t g_last_tick_ms;

int g_score;
int g_highscore;
int g_level;
int g_lives;
int g_game_over;
uint32_t g_game_over_until;

// Events raised since the last poll_events(), for the sound layer.
#define EVENT_PADDLE 0x01
#define EVENT_BRICK 0x02
#define EVENT_WALL 0x04
#define EVENT_LOST_LIFE 0x08
#define EVENT_LEVEL_UP 0x10
#define EVENT_GAME_OVER 0x20
int g_events;

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

// Brick geometry, shared by collision and drawing.
#define BRICK_GAP 2
#define BRICK_HEIGHT 6
#define BRICK_OFFSET_Y 10

static inline int clamp_int(int value, int min_value, int max_value) {
    if (value < min_value) {
        return min_value;
    }
    if (value > max_value) {
        return max_value;
    }
    return value;
}

static inline int brick_width(void) {
    const int area = (int)g_framebuffer_width - (BRICK_GAP * (BRICK_COLS + 1));
    return (area > 0) ? (area / BRICK_COLS) : 0;
}

static inline int brick_y(int row) {
    return BRICK_OFFSET_Y + row * (BRICK_HEIGHT + BRICK_GAP);
}

static inline int paddle_y(void) {
    return (int)g_framebuffer_height - g_paddle_height - 4;
}

// ---- dirty bands ----------------------------------------------------------

static void mark_all_dirty(void) {
    for (size_t i = 0; i < g_band_count; i++) {
        g_band_dirty[i] = true;
    }
}

static void mark_rect(int x, int y, int w, int h) {
    if (w <= 0 || h <= 0 || g_band_rows == 0) {
        return;
    }
    int first = y / (int)g_band_rows;
    int last = (y + h - 1) / (int)g_band_rows;
    if (first < 0) {
        first = 0;
    }
    if (last >= (int)g_band_count) {
        last = (int)g_band_count - 1;
    }
    for (int band = first; band <= last; band++) {
        g_band_dirty[band] = true;
    }
}

static void mark_ball(void) {
    const int x = (int)g_ball_x - (BALL_SIZE / 2);
    const int y = (int)g_ball_y - (BALL_SIZE / 2);
    mark_rect(x - 1, y - 1, BALL_SIZE + 2, BALL_SIZE + 2);
}

static void mark_paddle(void) {
    mark_rect(g_paddle_x, paddle_y(), g_paddle_width, g_paddle_height);
}

// ---- drawing -------------------------------------------------------------

static void draw_rect(int x, int y, int w, int h, uint16_t color) {
    uint16_t *buffer = g_target;

    if (w <= 0 || h <= 0 || buffer == NULL) {
        return;
    }
    if (x >= (int)g_framebuffer_width || y >= (int)g_framebuffer_height) {
        return;
    }

    int x0 = (x < 0) ? 0 : x;
    int y0 = (y < 0) ? 0 : y;
    int x1 = x + w;
    int y1 = y + h;
    if (x1 > (int)g_framebuffer_width) {
        x1 = (int)g_framebuffer_width;
    }
    if (y1 > (int)g_framebuffer_height) {
        y1 = (int)g_framebuffer_height;
    }
    if (x0 >= x1 || y0 >= y1) {
        return;
    }

    const int row_offset = (int)g_render_y_offset;
    const int row_end = row_offset + (int)g_render_rows;
    if (y0 < row_offset) {
        y0 = row_offset;
    }
    if (y1 > row_end) {
        y1 = row_end;
    }
    if (y0 >= y1) {
        return;
    }

    // Rows are indexed in the whole surface, not in the band: the buffer is the
    // full screen even though only one band of rows is being drawn.
    const size_t width = g_framebuffer_width;
    const size_t fill = (size_t)(x1 - x0);

    for (int yy = y0; yy < y1; yy++) {
        uint16_t *row = buffer + (size_t)yy * width + (size_t)x0;
        for (size_t xx = 0; xx < fill; xx++) {
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

static void generate_level(int level, uint32_t seed) {
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

    uint32_t rng_state = seed ^ ((uint32_t)level * 0x9E3779B9u);
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
    mark_all_dirty();
    g_has_clock = false;
}

static void level_up(uint32_t seed) {
    g_score += g_level * 50 + g_lives * 20;
    g_level++;
    g_lives = 5;
    generate_level(g_level, seed);
    g_events |= EVENT_LEVEL_UP;
}

// ---- module functions ----------------------------------------------------

// init(buffer, width, height): take the RGB565 buffer render_band() draws into.
static mp_obj_t init(size_t n_args, const mp_obj_t *args) {
    mp_buffer_info_t bufinfo;

    mp_get_buffer_raise(args[0], &bufinfo, MP_BUFFER_WRITE);
    g_target = (uint16_t *)bufinfo.buf;
    g_target_pixels = bufinfo.len / sizeof(uint16_t);

    g_framebuffer_width = (size_t)mp_obj_get_int(args[1]);
    g_framebuffer_height = (size_t)mp_obj_get_int(args[2]);

    g_band_rows = 0;
    g_band_count = 0;
    g_render_y_offset = 0;
    g_render_rows = 0;

    g_score = 0;
    g_level = 1;
    g_lives = 5;
    g_game_over = 0;
    g_game_over_until = 0;
    g_events = 0;
    g_has_clock = false;
    g_last_tick_ms = 0;

    generate_level(1, 0);
    mark_all_dirty();

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(init_obj, 3, 3, init);

// set_band_rows(rows): rows per band, from the size of one framebuffer.
// Returns the number of bands the display is split into.
static mp_obj_t set_band_rows(mp_obj_t rows_obj) {
    int rows = mp_obj_get_int(rows_obj);
    if (rows < 1) {
        rows = 1;
    }
    if (rows > (int)g_framebuffer_height) {
        rows = (int)g_framebuffer_height;
    }
    // The dirty flags are a fixed array, so a screen split into more bands than
    // it can hold would silently never redraw its last rows: widen the bands
    // instead.
    const int min_rows = ((int)g_framebuffer_height + MAX_BANDS - 1) / MAX_BANDS;
    if (rows < min_rows) {
        rows = min_rows;
    }
    g_band_rows = (size_t)rows;
    g_band_count = (g_framebuffer_height + g_band_rows - 1) / g_band_rows;
    if (g_band_count > MAX_BANDS) {
        g_band_count = MAX_BANDS;
    }
    mark_all_dirty();
    return mp_obj_new_int((int)g_band_count);
}
static MP_DEFINE_CONST_FUN_OBJ_1(set_band_rows_obj, set_band_rows);

// next_dirty(): first band that still needs drawing this frame, or -1.
static mp_obj_t next_dirty(void) {
    for (size_t i = 0; i < g_band_count; i++) {
        if (g_band_dirty[i]) {
            return mp_obj_new_int((int)i);
        }
    }
    return mp_obj_new_int(-1);
}
static MP_DEFINE_CONST_FUN_OBJ_0(next_dirty_obj, next_dirty);

// mark_all_dirty(): force a full screen redraw (start, resume, resize).
static mp_obj_t mark_all(void) {
    mark_all_dirty();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(mark_all_dirty_obj, mark_all);

// tick(now_ms): advance the simulation to now_ms and mark what moved.
static mp_obj_t tick(mp_obj_t now_obj) {
    if (g_framebuffer_width == 0 || g_framebuffer_height == 0) {
        return mp_const_none;
    }

    const uint32_t now_ms = (uint32_t)mp_obj_get_int(now_obj);
    uint32_t tick_delta_ms = 0;
    if (g_has_clock) {
        tick_delta_ms = now_ms - g_last_tick_ms;
    }
    g_last_tick_ms = now_ms;
    g_has_clock = true;
    if (tick_delta_ms > 50) {
        tick_delta_ms = 50;
    }

    if (g_game_over) {
        if ((int32_t)(now_ms - g_game_over_until) >= 0) {
            g_score = 0;
            g_level = 1;
            g_lives = 5;
            generate_level(1, now_ms);
        }
        return mp_const_none;
    }

    if (g_lives <= 0 || tick_delta_ms == 0) {
        return mp_const_none;
    }

    // Everything that is about to move has to be repainted where it is now.
    mark_ball();
    mark_paddle();

    const float dt = (float)tick_delta_ms / 1000.0f;
    g_ball_x += g_ball_vx * dt;
    g_ball_y += g_ball_vy * dt;

    if (g_ball_x <= 0.0f) {
        g_ball_x = 0.0f;
        g_ball_vx = g_ball_speed;
        g_events |= EVENT_WALL;
    } else if (g_ball_x >= (float)g_framebuffer_width - 1.0f) {
        g_ball_x = (float)g_framebuffer_width - 1.0f;
        g_ball_vx = -g_ball_speed;
        g_events |= EVENT_WALL;
    }

    if (g_ball_y <= 0.0f) {
        g_ball_y = 0.0f;
        g_ball_vy = g_ball_speed;
        g_events |= EVENT_WALL;
    }

    const int width = (int)g_framebuffer_width;
    const int bw = brick_width();
    if (bw > 0 && g_ball_y <= (float)(brick_y(BRICK_ROWS - 1) + BRICK_HEIGHT)) {
        for (int row = 0; row < BRICK_ROWS; row++) {
            for (int col = 0; col < BRICK_COLS; col++) {
                if (g_brick_hits[row][col] == 0) {
                    continue;
                }
                const int bx = BRICK_GAP + col * (bw + BRICK_GAP);
                const int by = brick_y(row);
                if (g_ball_x >= (float)bx && g_ball_x < (float)(bx + bw) &&
                        g_ball_y >= (float)by && g_ball_y < (float)(by + BRICK_HEIGHT)) {
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
                    mark_rect(bx, by, bw, BRICK_HEIGHT);
                    g_events |= EVENT_BRICK;
                    row = BRICK_ROWS;
                    break;
                }
            }
        }
    }

    const int py = paddle_y();
    if (g_ball_y >= (float)(py - 1) && g_ball_y <= (float)(py + g_paddle_height)) {
        if (g_ball_x >= (float)g_paddle_x && g_ball_x <= (float)(g_paddle_x + g_paddle_width)) {
            g_ball_y = (float)(py - 1);
            g_ball_vy = -g_ball_speed;
            float hit_offset = (g_ball_x - ((float)g_paddle_x + (float)g_paddle_width / 2.0f)) /
                              ((float)g_paddle_width / 2.0f);
            if (hit_offset < -1.0f) {
                hit_offset = -1.0f;
            } else if (hit_offset > 1.0f) {
                hit_offset = 1.0f;
            }
            g_ball_vx = hit_offset * g_ball_speed;
            g_events |= EVENT_PADDLE;
        }
    }

    if (g_ball_y >= (float)((int)g_framebuffer_height - 1)) {
        g_lives--;
        g_events |= EVENT_LOST_LIFE;
        if (g_lives > 0) {
            mark_ball();
            reset_ball();
        } else {
            g_game_over = 1;
            g_game_over_until = now_ms + 5000;
            g_ball_vx = 0.0f;
            g_ball_vy = 0.0f;
            g_events |= EVENT_GAME_OVER;
            mark_all_dirty();
        }
    }

    if (g_bricks_remaining <= 0) {
        level_up(now_ms);
    }

    mark_ball();
    mark_paddle();
    (void)width;

    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(tick_obj, tick);

// render_band(band): draw one band of the current frame. Clears its dirty flag.
static mp_obj_t render_band(mp_obj_t band_obj) {
    const int band = mp_obj_get_int(band_obj);
    if (band < 0 || band >= (int)g_band_count) {
        return mp_const_none;
    }
    if (g_target == NULL) {
        return mp_const_none;
    }

    const size_t y_offset = (size_t)band * g_band_rows;
    size_t rows = g_framebuffer_height - y_offset;
    if (rows > g_band_rows) {
        rows = g_band_rows;
    }

    // Never draw past what the buffer can hold.
    const size_t width = g_framebuffer_width;
    if (width > 0) {
        size_t max_rows = g_target_pixels / width;
        if (rows > max_rows) {
            rows = max_rows;
        }
    }
    if (rows == 0) {
        return mp_const_none;
    }

    g_render_y_offset = y_offset;
    g_render_rows = rows;

    // Clear the band, then draw everything that can reach it.
    memset(g_target + y_offset * width, 0, width * rows * sizeof(uint16_t));

    const int bw = brick_width();
    if (bw > 0) {
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
                draw_rect(BRICK_GAP + col * (bw + BRICK_GAP), brick_y(row),
                          bw, BRICK_HEIGHT, brick_color(max_hits, remaining));
            }
        }
    }

    draw_rect(g_paddle_x, paddle_y(), g_paddle_width, g_paddle_height, 0xFFFF);
    draw_rect((int)g_ball_x - (BALL_SIZE / 2), (int)g_ball_y - (BALL_SIZE / 2),
              BALL_SIZE, BALL_SIZE, 0xFFFF);

    g_band_dirty[band] = false;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(render_band_obj, render_band);

// poll_events(): bitmask of gameplay events since the last call.
static mp_obj_t poll_events(void) {
    const int events = g_events;
    g_events = 0;
    return mp_obj_new_int(events);
}
static MP_DEFINE_CONST_FUN_OBJ_0(poll_events_obj, poll_events);

// move_paddle(delta): move the paddle horizontally; marks both positions dirty.
static mp_obj_t move_paddle(mp_obj_t delta_obj) {
    int delta = mp_obj_get_int(delta_obj);
    if (g_framebuffer_width > 0 && !g_game_over) {
        mark_paddle();
        g_paddle_x = clamp_int(g_paddle_x + delta, 0, (int)g_framebuffer_width - g_paddle_width);
        mark_paddle();
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

static mp_obj_t new_game(size_t n_args, const mp_obj_t *args) {
    uint32_t seed = 0;
    if (n_args >= 1) {
        seed = (uint32_t)mp_obj_get_int(args[0]);
    }
    g_score = 0;
    g_level = 1;
    g_lives = 5;
    g_game_over = 0;
    g_game_over_until = 0;
    generate_level(1, seed);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(new_game_obj, 0, 1, new_game);

static mp_obj_t set_level(mp_obj_t value_obj) {
    int level = mp_obj_get_int(value_obj);
    if (level < 1) {
        level = 1;
    }
    g_game_over = 0;
    generate_level(level, 0);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(set_level_obj, set_level);

// This is the entry point and is called when the module is imported
mp_obj_t mpy_init(mp_obj_fun_bc_t *self, size_t n_args, size_t n_kw, mp_obj_t *args) {
    // This must be first, it sets up the globals dict and other things
    MP_DYNRUNTIME_INIT_ENTRY

    mp_store_global(MP_QSTR_init, MP_OBJ_FROM_PTR(&init_obj));
    mp_store_global(MP_QSTR_set_band_rows, MP_OBJ_FROM_PTR(&set_band_rows_obj));
    mp_store_global(MP_QSTR_tick, MP_OBJ_FROM_PTR(&tick_obj));
    mp_store_global(MP_QSTR_next_dirty, MP_OBJ_FROM_PTR(&next_dirty_obj));
    mp_store_global(MP_QSTR_mark_all_dirty, MP_OBJ_FROM_PTR(&mark_all_dirty_obj));
    mp_store_global(MP_QSTR_render_band, MP_OBJ_FROM_PTR(&render_band_obj));
    mp_store_global(MP_QSTR_poll_events, MP_OBJ_FROM_PTR(&poll_events_obj));
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

    mp_store_global(MP_QSTR_EVENT_PADDLE, MP_OBJ_NEW_SMALL_INT(EVENT_PADDLE));
    mp_store_global(MP_QSTR_EVENT_BRICK, MP_OBJ_NEW_SMALL_INT(EVENT_BRICK));
    mp_store_global(MP_QSTR_EVENT_WALL, MP_OBJ_NEW_SMALL_INT(EVENT_WALL));
    mp_store_global(MP_QSTR_EVENT_LOST_LIFE, MP_OBJ_NEW_SMALL_INT(EVENT_LOST_LIFE));
    mp_store_global(MP_QSTR_EVENT_LEVEL_UP, MP_OBJ_NEW_SMALL_INT(EVENT_LEVEL_UP));
    mp_store_global(MP_QSTR_EVENT_GAME_OVER, MP_OBJ_NEW_SMALL_INT(EVENT_GAME_OVER));

    // This must be last, it restores the globals dict
    MP_DYNRUNTIME_INIT_EXIT
}
