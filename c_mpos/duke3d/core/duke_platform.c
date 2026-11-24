// The platform services the engine still asks for by their retro-go names.
//
// Nothing here is a real retro-go: the launcher, the settings store, the SD
// card, the display driver and the audio sinks all live outside a core. Each
// call is answered from the core ABI, or degrades to a harmless value. The
// engine's own "Retro-Go options" screen is therefore inert, which is right:
// those settings belong to MicroPythonOS, not to the engine.

#include <stdarg.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "duke_platform.h"
#include "rg_system.h"
#include "../doom/core/core_console.h"
#include "duke_libc.h"
#include "../../core_abi.h"

static const mpos_core_abi_t *s_abi;
static int s_running;

static uint32_t s_frames;
static uint32_t s_present_ms;
static uint32_t s_convert_ms;
static uint32_t s_engine_ms;
static uint32_t s_wait_ms;
static uint32_t s_frame_start_ms;
static uint32_t s_profile_start_ms;
static uint32_t s_last_log_ms;
static int s_log_lines;
static unsigned long s_stack_min;

// Engine-side counter (tiles.c), reset whenever the frame profile is printed.
extern int mpos_duke_tile_decodes;

// The host's log takes a MicroPython string, and the engine's console carries
// arbitrary DOS bytes (a high-bit character in a message, a binary blob in a
// debug line). An invalid UTF-8 byte raises UnicodeError inside the ABI call,
// which surfaces as a failed frame, so the text is made ASCII first.
static void sanitize_ascii(char *text) {
    for (; *text != '\0'; text++) {
        if ((unsigned char)*text >= 0x80) {
            *text = '?';
        }
    }
}


static unsigned long current_sp(void) {
    unsigned long sp = 0;
#if defined(__xtensa__)
    __asm__ volatile("mov %0, a1" : "=r"(sp));
#endif
    return sp;
}

void duke_platform_stack_mark(const char *tag) {
    const unsigned long sp = current_sp();
    // A host build has no a1; there is no meaningful mark to take.
    if (sp == 0) {
        return;
    }
    if (s_stack_min == 0 || sp + 32 < s_stack_min) {
        s_stack_min = sp;
        char line[96];
        snprintf(line, sizeof(line), "stack low 0x%lx at %s", sp,
                 tag != NULL ? tag : "?");
        mpos_duke_log("%s", line);
    }
}

void duke_platform_init(const mpos_core_abi_t *abi) {
    s_abi = abi;
    s_stack_min = current_sp();
    s_frames = 0;
    s_present_ms = 0;
    s_frame_start_ms = abi->now_ms(abi->host);
    s_profile_start_ms = s_frame_start_ms;
    s_last_log_ms = s_frame_start_ms;
}

const mpos_core_abi_t *duke_platform_abi(void) {
    return s_abi;
}

void duke_platform_set_running(int running) {
    s_running = running;
}

int duke_platform_running(void) {
    return s_running;
}

void duke_platform_frame_started(void) {
    if (s_abi != NULL) {
        s_frame_start_ms = s_abi->now_ms(s_abi->host);
    }
}

void duke_platform_add_convert(uint32_t ms) {
    s_convert_ms += ms;
}

void duke_platform_add_present(uint32_t ms) {
    s_present_ms += ms;
}

void duke_platform_add_engine(uint32_t ms) {
    s_engine_ms += ms;
}

// Time the engine spent waiting for the host to finish with a buffer: that is
// the part of the frame the panel owns, not the renderer.
void duke_platform_add_wait(uint32_t ms) {
    s_wait_ms += ms;
}

void duke_platform_frame_presented(void) {
    if (s_abi == NULL) {
        return;
    }
    duke_platform_stack_mark("present");
    const uint32_t now = s_abi->now_ms(s_abi->host);
    s_frames++;
    if (s_frames == 1) {
        s_profile_start_ms = now;
    }
    const uint32_t elapsed = now - s_profile_start_ms;
    if (elapsed >= 5000 && s_frames > 1) {
        char line[120];
        snprintf(line, sizeof(line),
                 "duke: %u frames in %u ms (%.1f fps), engine %.1f, convert %.1f, present %.1f, wait %.1f",
                 (unsigned)s_frames, (unsigned)elapsed,
                 (double)s_frames * 1000.0 / (double)elapsed,
                 (double)s_engine_ms / (double)s_frames,
                 (double)s_convert_ms / (double)s_frames,
                 (double)s_present_ms / (double)s_frames,
                 (double)s_wait_ms / (double)s_frames);
        int decodes = mpos_duke_tile_decodes;
        mpos_duke_tile_decodes = 0;
        snprintf(line + strlen(line), sizeof(line) - strlen(line),
                 ", tile decodes %d", decodes);
        s_abi->log(s_abi->host, line);
        s_frames = 0;
        s_present_ms = 0;
        s_convert_ms = 0;
        s_engine_ms = 0;
        s_wait_ms = 0;
        s_profile_start_ms = now;
    }
}

void duke_platform_idle(void) {
    // The engine calls this from SDL_Delay and around file reads. A core has
    // no scheduler of its own, so the ABI is the one place a yield can happen:
    // on its own task it is a direct vTaskDelay, and on the MicroPython task
    // it is the ABI 8 log sentinel, which the loader honours in C. Sleeping
    // from a callback would re-enter the interpreter on a deep engine stack.
    static uint32_t last_yield;
    if (s_abi == NULL) {
        return;
    }
    // The interrupt watchdog tolerates 300 ms between idle runs. One tick
    // every 100 ms is plenty of margin and keeps the cost off the frame path:
    // a burst of tile reads pays a yield at most ten times a second.
    const uint32_t now = s_abi->now_ms(s_abi->host);
    // The watchdog tolerates 300 ms. Start-up yields every 50 ms (it is one
    // long C run and the watchdog must be fed); the game every 100 ms, which
    // keeps a burst of cache misses from pacing normal frames.
    const uint32_t interval = s_running ? 100 : 50;
    if (last_yield != 0 && (uint32_t)(now - last_yield) < interval) {
        return;
    }
    last_yield = now == 0 ? 1 : now;
    if (s_abi->yield != NULL) {
        s_abi->yield(s_abi->host);
        return;
    }
    s_abi->log(s_abi->host, "\x01yield");
}

void duke_platform_request_exit(void) {
    extern void rg_system_request_exit(void);
    rg_system_request_exit();
}

int duke_platform_exit_requested(void) {
    extern bool rg_system_should_exit(void);
    return rg_system_should_exit();
}

// -- logging -----------------------------------------------------------------

// mpos_printf.c writes one character at a time; lines are collected and handed
// to the host's log, which keeps a console round-trip off the engine's load
// path for every partial line.
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
                sanitize_ascii(line);
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

const mp_print_t mp_plat_print = {mpos_core_console_write, NULL};

void mpos_duke_log(const char *fmt, ...) {
    if (s_abi == NULL || fmt == NULL) {
        return;
    }
    char line[220];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(line, sizeof(line), fmt, ap);
    va_end(ap);
    sanitize_ascii(line);
    // The engine logs a lot during start-up; a console round-trip per line is
    // what costs time there, not the formatting.
    s_abi->log(s_abi->host, line);
    s_log_lines++;
    if (s_abi != NULL) {
        s_last_log_ms = s_abi->now_ms(s_abi->host);
    }
}

// -- retro-go names ----------------------------------------------------------

void *rg_alloc(size_t size, uint32_t flags) {
    (void)flags;
    return malloc(size);
}

void *rg_calloc(size_t nmemb, size_t size) {
    return calloc(nmemb, size);
}

void rg_free(void *ptr) {
    free(ptr);
}

static const rg_app_t s_app = {"duke3d.grp"};

const rg_app_t *rg_system_get_app(void) {
    return &s_app;
}

void rg_system_tick(uint32_t micros) {
    (void)micros;
}

int rg_system_get_cpu_speed(void) {
    return 240;
}

int rg_system_get_overclock(void) {
    return 0;
}

void rg_system_set_overclock(int level) {
    (void)level;
}

void rg_system_reinit(int sample_rate, void *handlers, void *config) {
    (void)sample_rate;
    (void)handlers;
    (void)config;
}

void rg_system_set_log_level(int level) {
    (void)level;
}

const int RG_LOG_WARN = 1;

bool rg_storage_exists(const char *path) {
    (void)path;
    return false;
}

bool rg_storage_mkdir(const char *path) {
    (void)path;
    return false;
}

void rg_storage_commit(void) {}

bool rg_storage_unzip_file(const char *path, const char *filename,
                           void **data, size_t *size, int flags) {
    (void)path;
    (void)filename;
    (void)data;
    (void)size;
    (void)flags;
    return false;
}

char *rg_emu_get_path(rg_path_type_t type, const char *arg) {
    (void)type;
    (void)arg;
    return NULL;
}

char *rg_dirname(char *path) {
    if (path == NULL) {
        return path;
    }
    char *slash = strrchr(path, '/');
    if (slash != NULL) {
        *slash = '\0';
    }
    return path;
}

bool rg_extension_match(const char *path, const char *extension) {
    if (path == NULL || extension == NULL) {
        return false;
    }
    const char *dot = strrchr(path, '.');
    if (dot == NULL) {
        return false;
    }
    return strcasecmp(dot + 1, extension) == 0;
}

bool rg_settings_exists(const char *ns, const char *key) {
    (void)ns;
    (void)key;
    return false;
}

void rg_settings_commit(void) {}

static const rg_audio_sink_t *const s_no_sinks = NULL;

const rg_audio_sink_t *rg_audio_get_sinks(size_t *count) {
    if (count != NULL) {
        *count = 0;
    }
    return s_no_sinks;
}

const rg_audio_sink_t *rg_audio_get_sink(void) {
    return NULL;
}

void rg_audio_set_sink(const char *driver_name, int device) {
    (void)driver_name;
    (void)device;
}

int rg_audio_get_volume(void) {
    return 100;
}

void rg_audio_set_volume(int percent) {
    (void)percent;
}

bool rg_audio_get_mute(void) {
    return true;
}

void rg_audio_set_mute(bool mute) {
    (void)mute;
}

int rg_audio_get_sample_rate(void) {
    return 11025;
}

void rg_audio_set_sample_rate(int sample_rate) {
    (void)sample_rate;
}

static display_scaling_t s_scaling = RG_DISPLAY_SCALING_FULL;

void rg_display_set_scaling(display_scaling_t scaling) {
    s_scaling = scaling;
}

display_scaling_t rg_display_get_scaling(void) {
    return s_scaling;
}

void rg_display_set_backlight(display_backlight_t percent) {
    (void)percent;
}

display_backlight_t rg_display_get_backlight(void) {
    return RG_DISPLAY_BACKLIGHT_MAX;
}

void mpos_duke_delay_ms(uint32_t ms) {
    (void)ms;
}

void audio_shutdown(void) {}

// network.c is not built: the engine's lobby code is replaced by mmulti.c's
// STUB_NETWORKING branch, and these two are all display.c calls.
void Setup_UnstableNetworking(void) {}
void Setup_StableNetworking(void) {}
