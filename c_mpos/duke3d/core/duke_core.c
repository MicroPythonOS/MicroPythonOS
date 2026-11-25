// Duke Nukem 3D as a flash-resident mpos_core blob.
//
// The engine is the DukeNano3D port of Chocolate Duke3D (retro-go flavour),
// kept as-is apart from two seams: main() stops after its start-up and the
// body of its loop is duke_run_frame(), which the host calls once per display
// frame; and the GRP is read through the core ABI instead of a filesystem.
//
// Layout: text and read-only data are mapped from the app's .xip extent into
// the instruction and data windows (see duke_core.ld); writable state lives in
// the RAM arena the host maps at a fixed address. The arena holds .data (whose
// initial bytes are copied out of the blob's data region once) followed by
// .bss. The engine's own heap is a second block from the host, so a big tile
// cache can be released when the activity stops without touching the globals.
//
// The picture is the engine's 320x200 palette framebuffer. SDL_Flip converts
// it to RGB565 straight into the host's surface, band by band, so no pixel
// work is left to Python (see sdl_video.c).

#include <stddef.h>
#include <stdint.h>
#include <setjmp.h>
#include <string.h>

#include "duke3d.h"
#include "duke_libc.h"
#include "duke_platform.h"
#include "../../core_abi.h"

// The engine's split entry points (game.c).
int main(int argc, char **argv);
int duke_run_frame(void);

// Where the blob is linked; keep in step with duke_core.ld and the entry table.
#define DUKE_CORE_TEXT_ADDR 0x43000000u
#define DUKE_CORE_DATA_ADDR 0x3DF00000u
#define DUKE_CORE_ARENA_ADDR 0x3DC00000u

// The engine's heap. Duke's tile cache is sized from the largest free block, so
// a smaller heap is still playable (just with more tile reloads).
#define HEAP_BYTES (3u * 1024u * 1024u)

// The linker's writable-image symbols: .data's initial bytes live in the
// mapped data region at core_data_init_src, and are copied to __data_start
// before any C code that might read an initialised global runs.
extern char __data_start[];
extern char __data_end[];
extern char core_data_init_src[];

static const mpos_core_abi_t *s_abi;
static int s_initialised;
static int s_finished;
static int s_stopped;
static jmp_buf s_fatal_jmp;
static int s_fatal_armed;
static void *s_heap;
static uint32_t s_heap_bytes;
static int s_quit_logged;

void mpos_fatal_jump(void) {
    if (s_fatal_armed) {
        s_fatal_armed = 0;
        longjmp(s_fatal_jmp, 1);
    }
}

// exit() and Error() end up here: no process to end, and returning into the
// engine after ShutDown() would run on freed memory.
__attribute__((used)) static void copy_data(void) {
    char *dst = __data_start;
    const char *src = core_data_init_src;
    size_t n = (size_t)(__data_end - __data_start);
    while (n-- > 0) {
        *dst++ = *src++;
    }
}

static int core_init(const mpos_core_abi_t *abi, const char *asset_name,
                     const char *config_dir) {
    (void)config_dir;
    s_abi = abi;
    s_initialised = 0;
    s_finished = 0;
    s_stopped = 0;

    // Initialised globals first: the libc's own state is .bss, but the engine
    // has real .data (default tables, key names) and nothing may read it
    // before it is there.
    copy_data();

    mpos_libc_init(abi);
    duke_platform_init(abi);

    // The engine's heap, outside the arena so its globals keep the addresses
    // they were linked at. Try the full size, then smaller: the tile cache
    // adapts to whatever is left, so a fragmented PSRAM should cost texture
    // reloads, not a launch. The ladder goes a long way down on purpose - on a
    // board whose PSRAM is split into 2-3 MB blocks by the host's own heaps,
    // 1.5 MB is often already too much after the arena and the GRP have taken
    // a block each.
    static const uint32_t sizes[] = {HEAP_BYTES, 2560u * 1024u, 2048u * 1024u,
                                     1536u * 1024u, 1024u * 1024u,
                                     768u * 1024u, 640u * 1024u,
                                     512u * 1024u};
    s_heap = NULL;
    for (size_t i = 0; i < sizeof(sizes) / sizeof(sizes[0]); i++) {
        s_heap = abi->alloc(abi->host, sizes[i]);
        if (s_heap != NULL) {
            s_heap_bytes = sizes[i];
            break;
        }
    }
    if (s_heap == NULL) {
        return -10;
    }
    mpos_heap_init(s_heap, s_heap_bytes);
    {
        char line[64];
        snprintf(line, sizeof(line), "core: heap %u KB", (unsigned)(s_heap_bytes / 1024));
        abi->log(abi->host, line);
    }

    char *argv[] = {(char *)"duke3d", NULL};
    s_fatal_armed = 1;
    if (setjmp(s_fatal_jmp) == 0) {
        // main() runs all of the start-up and returns at the point where the
        // engine's own loop would begin; see the split in game.c.
        abi->log(abi->host, "core: engine start-up");
        main(1, argv);
        abi->log(abi->host, "core: engine start-up done");
    } else {
        // A fatal error already asked for the exit; nothing may be ticked.
        s_finished = 1;
    }
    s_fatal_armed = 0;
    s_initialised = !s_finished;
    duke_platform_set_running(s_initialised);
    if (!s_initialised) {
        // The engine's Error() ended the start-up; the host shows this rather
        // than a black screen (the log callback has the reason).
        return -11;
    }
    return 0;
}

static void core_tick(const mpos_core_abi_t *abi, uint32_t now_ms) {
    (void)now_ms;
    if (!s_initialised || s_stopped || s_finished) {
        return;
    }
    {
        static int first_tick;
        if (!first_tick) {
            first_tick = 1;
            abi->log(abi->host, "core: first tick");
        }
    }
    s_fatal_armed = 1;
    const uint32_t engine_started = abi->now_ms(abi->host);
    if (setjmp(s_fatal_jmp) == 0) {
        if (!duke_run_frame()) {
            abi->log(abi->host, "core: the engine ended the frame");
            s_finished = 1;
        }
    } else {
        abi->log(abi->host, "core: a fatal error ended the frame");
        s_finished = 1;
    }
    duke_platform_add_engine(abi->now_ms(abi->host) - engine_started);
    s_fatal_armed = 0;
    if (s_finished) {
        s_initialised = 0;
    }
}

static void core_stop(const mpos_core_abi_t *abi) {
    (void)abi;
    // The host releases the arena and every abi->alloc block when the core
    // stops; there is nothing in the engine worth persisting.
    s_stopped = 1;
    s_initialised = 0;
}

static void core_audio_mix(int16_t *dst, int frames) {
    // No audio output on the panels this engine targets; see duke_audio.c.
    if (dst != NULL && frames > 0) {
        memset(dst, 0, (size_t)frames * sizeof(int16_t));
    }
}

static int core_quit_requested(void) {
    const int finished = s_finished;
    const int libc = mpos_libc_exit_requested();
    const int platform = duke_platform_exit_requested();
    if ((finished || libc || platform) && s_abi != NULL && !s_quit_logged) {
        s_quit_logged = 1;
        char text[64];
        snprintf(text, sizeof(text), "core: quit (%d/%d/%d)",
                 finished, libc, platform);
        s_abi->log(s_abi->host, text);
    }
    return finished || libc || platform;
}

__attribute__((section(".core_entry")))
const mpos_core_entry_t mpos_core_entry = {
    .abi_version = MPOS_CORE_ABI_VERSION,
    .flags = MPOS_CORE_FLAG_BAND_RGB565 | MPOS_CORE_FLAG_WORKER,
    .load_addr = DUKE_CORE_TEXT_ADDR,
    .data_addr = DUKE_CORE_DATA_ADDR,
    .data_offset = 0,  // patched by build_duke_core.sh from the linked sections
    .data_size = 0,
    .arena_addr = DUKE_CORE_ARENA_ADDR,
    .arena_size = 0,   // patched by build_duke_core.sh (.data + .bss)
    .init = core_init,
    .tick = core_tick,
    .stop = core_stop,
    .audio_mix = core_audio_mix,
    .quit_requested = core_quit_requested,
};
