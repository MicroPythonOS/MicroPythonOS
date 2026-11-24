// The SDL video surface, backed by the core ABI.
//
// The engine keeps a 320x200 8-bit paletted framebuffer and writes into
// surface->pixels; nothing here changes that. What changes is the flush: the
// original port copied the frame into retro-go's surface, which converted it
// and pushed it through SPI. Here SDL_Flip converts the engine's palette
// directly into the host's RGB565 surface, one display band at a time, and
// announces each band so the panel transfer overlaps the next band's
// conversion. That is the same shape as the Doom core's frame path.

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "SDL.h"
#include "../../core_abi.h"
#include "duke_platform.h"

// The engine's own resolution: 320x200, letterboxed in the 320x240 panel. The
// menu's resolution screen is accepted but ignored - a core presents one
// surface, and the classic 320x200 is the cheapest full view of the level.
#define SURFACE_WIDTH 320
#define SURFACE_HEIGHT 200

static SDL_Surface s_surface;
static SDL_PixelFormat s_format;
static SDL_Palette s_palette;
static SDL_Color s_colors[256];
static uint8_t s_pixels[SURFACE_WIDTH * SURFACE_HEIGHT];
static uint16_t s_palette565[256];

SDL_Surface *primary_surface;
static int s_video_ready;

static uint16_t rgb565(int r, int g, int b) {
    return (uint16_t)(((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3));
}

int SDL_LockSurface(SDL_Surface *surface) {
    (void)surface;
    return 0;
}

void SDL_UnlockSurface(SDL_Surface *surface) {
    (void)surface;
}

void SDL_LockDisplay(void) {}
void SDL_UnlockDisplay(void) {
    // A display operation is a natural place to let the host's frame loop
    // breathe: the engine calls this around file reads and long setup steps.
    duke_platform_idle();
}

SDL_VideoInfo *SDL_GetVideoInfo(void) {
    static SDL_VideoInfo info;
    info.vfmt = &s_format;
    info.vfmt->BitsPerPixel = 8;
    return &info;
}

char *SDL_VideoDriverName(char *namebuf, int maxlen) {
    (void)namebuf;
    (void)maxlen;
    return "MPOS-CORE";
}

SDL_Rect **SDL_ListModes(SDL_PixelFormat *format, Uint32 flags) {
    (void)format;
    (void)flags;
    static SDL_Rect modes_data[] = {
        {0, 0, SURFACE_WIDTH, SURFACE_HEIGHT},
        {0, 0, 240, 160},
        {0, 0, 0, 0}
    };
    static SDL_Rect *modes[] = {&modes_data[0], &modes_data[1], NULL};
    return modes;
}

void SDL_WM_SetCaption(const char *title, const char *icon) {
    (void)title;
    (void)icon;
}

char *SDL_GetKeyName(SDLKey key) {
    (void)key;
    return (char *)"";
}

Uint32 SDL_WasInit(Uint32 flags) {
    (void)flags;
    return s_video_ready ? SDL_INIT_VIDEO : 0;
}

static void surface_init(void) {
    if (s_video_ready) {
        return;
    }
    memset(&s_surface, 0, sizeof(s_surface));
    s_palette.ncolors = 256;
    s_palette.colors = s_colors;
    s_format.palette = &s_palette;
    s_format.BitsPerPixel = 8;
    s_format.BytesPerPixel = 1;
    s_format.alpha = 255;
    s_surface.format = &s_format;
    s_surface.w = SURFACE_WIDTH;
    s_surface.h = SURFACE_HEIGHT;
    s_surface.pitch = SURFACE_WIDTH;
    s_surface.pixels = s_pixels;
    s_surface.clip_rect.x = 0;
    s_surface.clip_rect.y = 0;
    s_surface.clip_rect.w = SURFACE_WIDTH;
    s_surface.clip_rect.h = SURFACE_HEIGHT;
    s_surface.refcount = 1;
    primary_surface = &s_surface;
    for (int i = 0; i < 256; i++) {
        s_colors[i].r = i;
        s_colors[i].g = i;
        s_colors[i].b = i;
        s_palette565[i] = rgb565(i, i, i);
    }
    extern uint8_t *frameplace;
    extern uint8_t *frameoffset;
    frameplace = s_pixels;
    frameoffset = s_pixels;
    s_video_ready = 1;
}

int SDL_InitSubSystem(Uint32 flags) {
    if (flags & SDL_INIT_VIDEO) {
        surface_init();
    }
    return 0;
}

SDL_Surface *SDL_CreateRGBSurface(Uint32 flags, int width, int height, int depth,
                                  Uint32 Rmask, Uint32 Gmask, Uint32 Bmask,
                                  Uint32 Amask) {
    (void)flags; (void)Rmask; (void)Gmask; (void)Bmask; (void)Amask;
    // The engine creates one extra surface in some capture paths; give it its
    // own pixels rather than aliasing the screen.
    SDL_Surface *surface = (SDL_Surface *)calloc(1, sizeof(SDL_Surface));
    if (surface == NULL) {
        return NULL;
    }
    SDL_PixelFormat *format = (SDL_PixelFormat *)calloc(1, sizeof(SDL_PixelFormat));
    SDL_Palette *palette = (SDL_Palette *)calloc(1, sizeof(SDL_Palette));
    if (format == NULL || palette == NULL) {
        free(surface);
        free(format);
        free(palette);
        return NULL;
    }
    palette->ncolors = 256;
    palette->colors = (SDL_Color *)calloc(256, sizeof(SDL_Color));
    format->palette = palette;
    format->BitsPerPixel = depth;
    format->BytesPerPixel = depth / 8;
    format->alpha = 255;
    surface->flags = flags;
    surface->format = format;
    surface->w = width;
    surface->h = height;
    surface->pitch = width * (depth / 8);
    surface->pixels = calloc((size_t)width * height * (depth / 8), 1);
    surface->clip_rect.x = 0;
    surface->clip_rect.y = 0;
    surface->clip_rect.w = width;
    surface->clip_rect.h = height;
    surface->refcount = 1;
    if (surface->pixels == NULL) {
        free(surface);
        return NULL;
    }
    if (primary_surface == NULL) {
        primary_surface = surface;
        extern uint8_t *frameplace;
        extern uint8_t *frameoffset;
        frameplace = frameoffset = (uint8_t *)surface->pixels;
    }
    return surface;
}

int SDL_FillRect(SDL_Surface *dst, SDL_Rect *dstrect, Uint32 color) {
    if (dst == NULL) {
        return -1;
    }
    if (dstrect != NULL) {
        for (int y = dstrect->y; y < dstrect->y + dstrect->h; y++) {
            memset((unsigned char *)dst->pixels + y * dst->w + dstrect->x,
                   (unsigned char)color, dstrect->w);
        }
    } else {
        memset(dst->pixels, (unsigned char)color, (size_t)dst->pitch * dst->h);
    }
    return 0;
}

SDL_Surface *SDL_GetVideoSurface(void) {
    surface_init();
    return primary_surface;
}

Uint32 SDL_MapRGB(SDL_PixelFormat *fmt, Uint8 r, Uint8 g, Uint8 b) {
    if (fmt != NULL && fmt->BitsPerPixel == 16) {
        return rgb565(r, g, b);
    }
    return 0;
}

int SDL_SetColors(SDL_Surface *surface, SDL_Color *colors, int firstcolor,
                  int ncolors) {
    (void)surface;
    for (int i = firstcolor; i < firstcolor + ncolors && i < 256; i++) {
        s_colors[i] = colors[i];
        s_palette565[i] = rgb565(colors[i].r, colors[i].g, colors[i].b);
    }
    return 1;
}

// Duke's 6-bit palette, packed B,G,R,unused. Fill-expand to 8 bits and
// ceiling-round: (255 + 4) >> 3 would be 32, so clamp instead of masking, or
// white wraps to black.
int SDL_SetPalette565(const uint8_t *pal6) {
    if (pal6 == NULL) {
        return 0;
    }
    for (int i = 0; i < 256; i++) {
        const uint16_t r8 = (pal6[i * 4 + 2] << 2) | (pal6[i * 4 + 2] >> 4);
        const uint16_t g8 = (pal6[i * 4 + 1] << 2) | (pal6[i * 4 + 1] >> 4);
        const uint16_t b8 = (pal6[i * 4 + 0] << 2) | (pal6[i * 4 + 0] >> 4);
        uint16_t r5 = (r8 + 4) >> 3;
        uint16_t g6 = (g8 + 2) >> 2;
        uint16_t b5 = (b8 + 4) >> 3;
        if (r5 > 31) r5 = 31;
        if (g6 > 63) g6 = 63;
        if (b5 > 31) b5 = 31;
        s_palette565[i] = (uint16_t)((r5 << 11) | (g6 << 5) | b5);
    }
    return 1;
}

SDL_Surface *SDL_SetVideoMode(int width, int height, int bpp, Uint32 flags) {
    (void)width;
    (void)height;
    (void)bpp;
    (void)flags;
    surface_init();
    return primary_surface;
}

void SDL_FreeSurface(SDL_Surface *surface) {
    if (surface == NULL || surface == &s_surface) {
        return;
    }
    if (surface->format != NULL) {
        if (surface->format->palette != NULL) {
            free(surface->format->palette->colors);
            free(surface->format->palette);
        }
        free(surface->format);
    }
    free(surface->pixels);
    free(surface);
}

void SDL_QuitSubSystem(Uint32 flags) {
    (void)flags;
}

void SDL_UpdateRect(SDL_Surface *screen, Sint32 x, Sint32 y, Sint32 w, Sint32 h) {
    (void)x; (void)y; (void)w; (void)h;
    SDL_Flip(screen);
}

// A landscape panel takes the frame as it is: dst(x, y) = src(x, y).
static void convert_band_direct(const mpos_core_abi_t *abi, uint16_t *dst,
                                int y0, int rows) {
    const int out_w = abi->frame_width;
    for (int y = y0; y < y0 + rows; y++) {
        const uint8_t *src_row = s_pixels + (size_t)y * SURFACE_WIDTH;
        uint16_t *dst_row = dst + (size_t)y * out_w;
        for (int x = 0; x < SURFACE_WIDTH && x < out_w; x++) {
            dst_row[x] = s_palette565[src_row[x]];
        }
    }
}

// A portrait panel (240x320 logical, held sideways) gets the frame turned a
// quarter turn: dst(dx, dy) = src(dy, 199 - dx). An output row is a source
// column, so the transpose is tiled to keep the reads and writes contiguous.
static uint16_t s_tile[32][32];

static void convert_band_rotated(const mpos_core_abi_t *abi, uint16_t *dst,
                                 int y0, int rows) {
    const int out_w = abi->frame_width;
    for (int ty = 0; ty < rows; ty += 32) {
        const int tile_rows = (rows - ty) < 32 ? (rows - ty) : 32;
        const int dy0 = y0 + ty;
        for (int dx0 = 0; dx0 < out_w; dx0 += 32) {
            const int cols = (out_w - dx0) < 32 ? (out_w - dx0) : 32;
            for (int c = 0; c < cols; c++) {
                const int sy = SURFACE_HEIGHT - 1 - (dx0 + c);
                const uint8_t *src_row = s_pixels
                    + (size_t)sy * SURFACE_WIDTH + (size_t)dy0;
                for (int r = 0; r < tile_rows; r++) {
                    s_tile[r][c] = s_palette565[src_row[r]];
                }
            }
            for (int r = 0; r < tile_rows; r++) {
                uint16_t *row = dst + (size_t)(dy0 + r) * out_w + dx0;
                for (int c = 0; c < cols; c++) {
                    row[c] = s_tile[r][c];
                }
            }
        }
    }
}

int SDL_Flip(SDL_Surface *screen) {
    (void)screen;
    const mpos_core_abi_t *abi = duke_platform_abi();
    if (abi == NULL || abi->frame == NULL) {
        return 0;
    }
    // The start-up fades and the loading screen are not shown: the activity is
    // still in start_engine(), its surface is not live, and every present is a
    // Python callback on a stack that is already deep in the engine.
    if (!duke_platform_running()) {
        return 0;
    }
    // The host's surface says how to present it, exactly as the Doom core
    // does: a 200x320 surface is the frame turned a quarter turn, a 320x200
    // one is the engine's own landscape frame.
    const int rotate = (abi->frame_width == SURFACE_HEIGHT
                        && abi->frame_height == SURFACE_WIDTH);
    const int height = rotate
        ? abi->frame_height
        : (SURFACE_HEIGHT < abi->frame_height ? SURFACE_HEIGHT
                                              : abi->frame_height);
    int band = abi->band_rows > 0 ? abi->band_rows : height;
    if (band > height) {
        band = height;
    }
    duke_platform_frame_started();
    for (int y = 0; y < height; y += band) {
        int rows = height - y;
        if (rows > band) {
            rows = band;
        }
        uint32_t started = abi->now_ms(abi->host);
        if (rotate) {
            convert_band_rotated(abi, abi->frame, y, rows);
        } else {
            convert_band_direct(abi, abi->frame, y, rows);
        }
        uint32_t converted = abi->now_ms(abi->host);
        duke_platform_add_convert(converted - started);
        // The host flushes these rows now; its SPI transfer runs while the
        // next band is converted.
        abi->present_band(abi->host, y, rows, NULL);
        duke_platform_add_present(abi->now_ms(abi->host) - converted);
    }
    // On a core that runs on its own task the host shows the whole frame: the
    // bands above went into a buffer nobody is reading, and the transfer
    // happens on the other task while this one draws the next frame. This call
    // also waits for the buffer the next frame needs, which is the panel's
    // share of the frame and is profiled separately.
    if (abi->frame_ready != NULL) {
        const uint32_t waiting = abi->now_ms(abi->host);
        abi->frame_ready(abi->host);
        duke_platform_add_wait(abi->now_ms(abi->host) - waiting);
    }
    duke_platform_frame_presented();
    return 0;
}

int SDL_VideoModeOK(int width, int height, int bpp, Uint32 flags) {
    (void)width; (void)height; (void)flags;
    return bpp == 8 ? 1 : 0;
}
