// Host harness for the Duke3D core: the same engine and the same platform
// shims, linked as an ordinary Linux executable.
//
// A core blob cannot run here (it is Xtensa code linked for fixed addresses),
// but everything *above* the ABI can: this harness supplies the callbacks with
// glibc (malloc, a real file for the GRP) and a fake clock, calls the engine's
// start-up exactly as core_init would, and then ticks it. It exists to debug
// start-up and gameplay logic quickly: gdb works, every printf lands on the
// terminal, and a frame can be dumped to a PPM.
//
// Build with ./build_host.sh; run from a directory containing duke3d.grp.

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "../../core_abi.h"
#include "../core/duke_platform.h"

// Renamed at compile time on the engine sources (-Dmain=duke_engine_main).
int duke_engine_main(int argc, char **argv);
int duke_run_frame(void);

#define WIDTH 320
#define HEIGHT 200

static uint16_t s_frame[WIDTH * HEIGHT];
static uint32_t s_now;
static uint32_t s_frames;
static int s_dump_at;
static const char *s_dump_path;

static void present_band(void *host, int band, int rows, const uint8_t *pixels) {
    (void)host;
    (void)band;
    (void)rows;
    (void)pixels;
}

static void palette(void *host, uint16_t *out, int entries) {
    (void)host;
    for (int i = 0; i < entries; i++) {
        out[i] = 0;
    }
}

static int poll_key(void *host, int *pressed) {
    (void)host;
    (void)pressed;
    return -1;
}

static uint32_t now_ms(void *host) {
    (void)host;
    return s_now;
}

static int read_file(void *host, const char *path, uint32_t offset, void *dst,
                     uint32_t len) {
    (void)host;
    FILE *file = fopen(path, "rb");
    if (file == NULL) {
        return -1;
    }
    fseek(file, offset, SEEK_SET);
    size_t got = fread(dst, 1, len, file);
    fclose(file);
    return (int)got;
}

static int file_size(void *host, const char *path) {
    (void)host;
    FILE *file = fopen(path, "rb");
    if (file == NULL) {
        return -1;
    }
    fseek(file, 0, SEEK_END);
    long size = ftell(file);
    fclose(file);
    return (int)size;
}

static void *core_alloc(void *host, uint32_t bytes) {
    (void)host;
    return calloc(1, bytes);
}

static void core_dealloc(void *host, void *ptr) {
    (void)host;
    free(ptr);
}

static void log_line(void *host, const char *text) {
    (void)host;
    if (text[0] == '\x01') {
        return;
    }
    printf("%s\n", text);
}

// The engine's tile cache sizes itself from these.
size_t heap_caps_get_free_size(unsigned caps) {
    (void)caps;
    return 2 * 1024 * 1024;
}

size_t heap_caps_get_largest_free_block(unsigned caps) {
    (void)caps;
    return 1536 * 1024;
}

void *heap_caps_malloc(size_t size, unsigned caps) {
    (void)caps;
    return malloc(size);
}

void heap_caps_free(void *ptr) {
    free(ptr);
}

static void dump_ppm(const char *path) {
    FILE *file = fopen(path, "wb");
    if (file == NULL) {
        return;
    }
    fprintf(file, "P6\n%d %d\n255\n", WIDTH, HEIGHT);
    for (int i = 0; i < WIDTH * HEIGHT; i++) {
        const uint16_t p = s_frame[i];
        const unsigned char rgb[3] = {
            (unsigned char)(((p >> 11) & 0x1F) * 255 / 31),
            (unsigned char)(((p >> 5) & 0x3F) * 255 / 63),
            (unsigned char)((p & 0x1F) * 255 / 31)};
        fwrite(rgb, 1, 3, file);
    }
    fclose(file);
    printf("harness: wrote %s\n", path);
}

int main(int argc, char **argv) {
    int frames = 300;
    if (argc > 1) {
        frames = atoi(argv[1]);
    }
    s_dump_at = frames;
    s_dump_path = argc > 2 ? argv[2] : "frame.ppm";

    static mpos_core_abi_t abi;
    abi.version = MPOS_CORE_ABI_VERSION;
    abi.present_band = present_band;
    abi.palette = palette;
    abi.poll_key = poll_key;
    abi.now_ms = now_ms;
    abi.read_file = read_file;
    abi.file_size = file_size;
    abi.alloc = core_alloc;
    abi.dealloc = core_dealloc;
    abi.log = log_line;
    abi.frame_width = WIDTH;
    abi.frame_height = HEIGHT;
    abi.frame = s_frame;
    abi.band_rows = 45;

    duke_platform_init(&abi);

    char *engine_argv[] = {(char *)"duke3d", NULL};
    int result = duke_engine_main(1, engine_argv);
    printf("harness: init returned %d\n", result);

    for (int i = 0; i < frames; i++) {
        s_now += 33;
        s_frames++;
        if (!duke_run_frame()) {
            printf("harness: engine ended at frame %d\n", i);
            break;
        }
        if (i + 1 == s_dump_at && s_dump_path != NULL) {
            dump_ppm(s_dump_path);
        }
    }
    printf("harness: %u frames, now=%u ms\n", (unsigned)s_frames,
           (unsigned)s_now);
    return 0;
}
