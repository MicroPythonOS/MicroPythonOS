// Duke Nukem 3D as a MicroPython native module (the desktop engine).
//
// The badge runs the same engine as a flash-resident core (core/duke_core.c);
// a desktop has no MMU window to map a flash blob into, so the engine is
// linked as an ordinary native module and driven from the activity. Everything
// above the ABI is shared: this file fills a normal mpos_core_abi_t with
// MicroPython calls (a file is a Python stream, the heap is m_malloc, the log
// is the REPL's stdout), then core_init's work is done here: rewrite the
// generated initialised data into BSS, allocate the engine heap, and call the
// engine's main(), which stops where its own loop would begin.
//
// The picture path is the same as the core's: SDL_Flip converts the engine's
// 320x200 palette framebuffer into the host's RGB565 surface one display band
// at a time and calls present(y, rows) so the panel transfer overlaps the next
// band's conversion (see core/sdl_video.c).
//
// The contract with Python:
//
//   surface(buffer, width, height, band_rows, present)   where a frame goes
//   start(asset, asset_name, config_dir, now_ms)         boot the engine
//   tick(now_ms)                                        run one engine frame
//   key(code, pressed)                                  queue a Duke key event
//   stop()                                              stop presenting
//   quit_requested()                                    the engine wants out
//   width() / height()                                  engine resolution
//   debug_state()                                       one console line
//   pos()                                               player and clock, for tests
//
// `asset` is the inflated GRP buffer (or None when there is no buffer); its
// bytes are read through read_file() without a Python call per lump. The
// engine's config and savegames go to config_dir through MicroPython's io.

#include "py/dynruntime.h"

#include <stdarg.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "duke3d.h"
#include "duke_libc.h"
#include "duke_platform.h"
#include "../../core_abi.h"
#include "duke_data_init.h"

// Split entry points in engine/Game/game.c (the Makefile renames main).
int duke_engine_main(int argc, char **argv);
int duke_run_frame(void);
// Engine/display.c: drops the timer frequency so the next start re-installs it.
void uninittimer(void);

// engine/Game/game.c owns the exit flag and the player state.
extern bool rg_system_should_exit(void);
extern short myconnectindex;

#define NATMOD_MAX_KEYS 64
#define NATMOD_ASSET_NAME 64
#define NATMOD_CONFIG_DIR 160

// A native module has no data section and no static BSS. Every variable here
// is an ordinary global with no initialiser: mpy_ld puts them in the module's
// BSS, which the loader zeroes and the collector scans.
mpos_core_abi_t s_abi;
mp_obj_t g_asset_obj;
mp_obj_t g_present_obj;
mp_obj_t g_open_fun;
mp_obj_t g_io_module;
const uint8_t *g_asset;
size_t g_asset_len;
char g_asset_name[NATMOD_ASSET_NAME];
char g_asset_path[NATMOD_CONFIG_DIR + 200];
char g_config_dir[NATMOD_CONFIG_DIR];
uint16_t *g_frame;
int g_frame_width;
int g_frame_height;
int g_band_rows;
uint16_t g_keys[NATMOD_MAX_KEYS];
int g_key_head;
int g_key_tail;
uint32_t g_now_ms;
int g_created;
int g_running;
int g_quit;
// The engine's own heap and the CON script are mapped below 4 GB (see
// nat_map_low): the Build renderer keeps pointers in 32-bit words. They
// outlive a session and the next start reuses them.
void *g_heap;
uint32_t g_heap_bytes;

static void nat_log(void *host, const char *text);

// -- Python helpers ---------------------------------------------------------

static int nat_try_begin(nlr_buf_t *nlr) {
    if (mp_fun_table.nlr_push(nlr) != 0) {
        return -1;
    }
    return 0;
}

static void nat_try_end(void) {
    mp_fun_table.nlr_pop();
}

static mp_obj_t nat_open(const char *path, const char *mode) {
    nlr_buf_t nlr;
    if (nat_try_begin(&nlr) != 0) {
        return mp_const_none;
    }
    if (g_open_fun == mp_const_none || g_open_fun == NULL) {
        g_io_module = mp_import_name(MP_QSTR_io, mp_const_none,
                                     mp_obj_new_int(0));
        g_open_fun = mp_load_attr(g_io_module, MP_QSTR_open);
    }
    mp_obj_t args[2];
    args[0] = mp_obj_new_str(path, strlen(path));
    args[1] = mp_obj_new_str(mode, strlen(mode));
    mp_obj_t file = mp_call_function_n_kw(g_open_fun, 2, 0, args);
    nat_try_end();
    return file;
}

static mp_obj_t nat_call_0(mp_obj_t object, qstr method) {
    nlr_buf_t nlr;
    if (nat_try_begin(&nlr) != 0) {
        return mp_const_none;
    }
    mp_obj_t dest[2];
    mp_load_method(object, method, dest);
    mp_obj_t result = mp_fun_table.call_method_n_kw(0, 0, dest);
    nat_try_end();
    return result;
}

static mp_obj_t nat_call_1(mp_obj_t object, qstr method, mp_obj_t arg) {
    nlr_buf_t nlr;
    if (nat_try_begin(&nlr) != 0) {
        return mp_const_none;
    }
    mp_obj_t dest[3];
    mp_load_method(object, method, dest);
    dest[2] = arg;
    mp_obj_t result = mp_fun_table.call_method_n_kw(1, 0, dest);
    nat_try_end();
    return result;
}

static mp_obj_t nat_call_2(mp_obj_t object, qstr method, mp_obj_t a, mp_obj_t b) {
    nlr_buf_t nlr;
    if (nat_try_begin(&nlr) != 0) {
        return mp_const_none;
    }
    mp_obj_t dest[4];
    mp_load_method(object, method, dest);
    dest[2] = a;
    dest[3] = b;
    mp_obj_t result = mp_fun_table.call_method_n_kw(2, 0, dest);
    nat_try_end();
    return result;
}

static void nat_close(mp_obj_t file) {
    if (file == mp_const_none) {
        return;
    }
    nlr_buf_t nlr;
    if (nat_try_begin(&nlr) != 0) {
        return;
    }
    mp_obj_t dest[2];
    mp_load_method(file, MP_QSTR_close, dest);
    mp_fun_table.call_method_n_kw(0, 0, dest);
    nat_try_end();
}

// The engine's virtual path (rg_system's /config, /saves) -> a real path under
// the app's prefs directory, exactly as the core activity does it in Python.
static void nat_host_path(const char *path, char *out, size_t size) {
    if (strncmp(path, "/config/", 8) == 0) {
        snprintf(out, size, "%s/%s", g_config_dir, path + 8);
    } else if (strncmp(path, "/saves/", 7) == 0) {
        snprintf(out, size, "%s/%s", g_config_dir, path + 7);
    } else if (path[0] == '/') {
        snprintf(out, size, "%s%s", g_config_dir, path);
    } else {
        snprintf(out, size, "%s/%s", g_config_dir, path);
    }
}

static int nat_size_real(const char *real) {
    mp_obj_t file = nat_open(real, "rb");
    if (file == mp_const_none) {
        return -1;
    }
    nat_call_2(file, MP_QSTR_seek, mp_obj_new_int(0), mp_obj_new_int(2));
    mp_obj_t pos = nat_call_0(file, MP_QSTR_tell);
    nat_close(file);
    if (pos == mp_const_none) {
        return -1;
    }
    return (int)mp_obj_get_int(pos);
}

static int nat_read_real(const char *real, uint32_t offset, void *dst,
                         uint32_t len) {
    if (len == 0) {
        return 0;
    }
    mp_obj_t file = nat_open(real, "rb");
    if (file == mp_const_none) {
        return -1;
    }
    nat_call_2(file, MP_QSTR_seek, mp_obj_new_int((int)offset),
               mp_obj_new_int(0));
    mp_obj_t buffer = mp_obj_new_bytearray_by_ref(len, dst);
    mp_obj_t result = nat_call_1(file, MP_QSTR_readinto, buffer);
    nat_close(file);
    if (result == mp_const_none) {
        return -1;
    }
    return (int)mp_obj_get_int(result);
}

static int nat_file_size(const char *path) {
    char real[NATMOD_CONFIG_DIR + 200];
    nat_host_path(path, real, sizeof(real));
    return nat_size_real(real);
}

static int nat_file_read(const char *path, uint32_t offset, void *dst,
                         uint32_t len) {
    char real[NATMOD_CONFIG_DIR + 200];
    nat_host_path(path, real, sizeof(real));
    return nat_read_real(real, offset, dst, len);
}

static int nat_file_write(const char *path, uint32_t offset, const void *src,
                          uint32_t len) {
    char real[NATMOD_CONFIG_DIR + 200];
    nat_host_path(path, real, sizeof(real));
    const char *mode = offset == 0 ? "wb" : "r+b";
    mp_obj_t file = nat_open(real, mode);
    if (file == mp_const_none) {
        nat_log(NULL, "duke3d: cannot open save file for writing");
        return -1;
    }
    if (offset != 0) {
        nat_call_2(file, MP_QSTR_seek, mp_obj_new_int((int)offset),
                   mp_obj_new_int(0));
    }
    if (len == 0) {
        nat_close(file);
        return 0;
    }
    mp_obj_t buffer = mp_obj_new_bytearray_by_ref(len, (void *)src);
    mp_obj_t result = nat_call_1(file, MP_QSTR_write, buffer);
    nat_close(file);
    if (result == mp_const_none) {
        nat_log(NULL, "duke3d: save write failed");
        return -1;
    }
    return (int)mp_obj_get_int(result);
}

// -- the core ABI, filled with MicroPython calls ---------------------------

static void nat_present_band(void *host, int band, int rows,
                             const uint8_t *pixels) {
    (void)host;
    (void)pixels;
    if (g_present_obj == mp_const_none || g_present_obj == NULL) {
        return;
    }
    mp_obj_t args[2];
    args[0] = mp_obj_new_int(band);
    args[1] = mp_obj_new_int(rows);
    mp_call_function_n_kw(g_present_obj, 2, 0, args);
}

static void nat_palette(void *host, uint16_t *out, int entries) {
    (void)host;
    for (int i = 0; i < entries; i++) {
        out[i] = 0;
    }
}

static int nat_poll_key(void *host, int *pressed) {
    (void)host;
    if (g_key_head == g_key_tail) {
        return -1;
    }
    const uint16_t event = g_keys[g_key_tail];
    g_key_tail = (g_key_tail + 1) % NATMOD_MAX_KEYS;
    *pressed = event >> 8;
    return event & 0xFF;
}

static uint32_t nat_now_ms(void *host) {
    (void)host;
    return g_now_ms;
}

static int nat_read_file(void *host, const char *path, uint32_t offset,
                         void *dst, uint32_t len) {
    (void)host;
    if (strcmp(path, g_asset_name) == 0) {
        if (g_asset != NULL) {
            if (offset >= g_asset_len) {
                return 0;
            }
            size_t count = g_asset_len - offset;
            if (count > len) {
                count = len;
            }
            memcpy(dst, g_asset + offset, count);
            return (int)count;
        }
        if (g_asset_path[0] != '\0') {
            return nat_read_real(g_asset_path, offset, dst, len);
        }
    }
    // A savegame or the engine's config: duke_libc.c falls back to
    // file_request() when this returns -1, which is the path that knows the
    // /config and /saves layout.
    return -1;
}

static int nat_file_size_cb(void *host, const char *path) {
    (void)host;
    if (strcmp(path, g_asset_name) == 0) {
        if (g_asset != NULL) {
            return (int)g_asset_len;
        }
        if (g_asset_path[0] != '\0') {
            return nat_size_real(g_asset_path);
        }
    }
    return -1;
}

static void *nat_alloc(void *host, uint32_t bytes) {
    (void)host;
    return mp_fun_table.realloc_(NULL, bytes, false);
}

static void nat_dealloc(void *host, void *ptr) {
    (void)host;
    if (ptr != NULL) {
        mp_fun_table.realloc_(ptr, 0, false);
    }
}

static void nat_log(void *host, const char *text) {
    (void)host;
    mp_printf(&mp_plat_print, "%s\n", text);
}

static void nat_yield(void *host) {
    (void)host;
}

static int nat_file_request(void *host, int op, const char *path,
                            uint32_t offset, uint32_t len, void *data) {
    (void)host;
    if (op == MPOS_CORE_FILE_READ) {
        return nat_file_read(path, offset, data, len);
    }
    if (op == MPOS_CORE_FILE_WRITE) {
        return nat_file_write(path, offset, data, len);
    }
    return nat_file_size(path);
}

// The engine's fatal-error path (Error()/exit()/abort()) cannot return into
// freed state and there is no process to end. MicroPython's raise unwinds to
// the Python caller, which treats it as the engine quitting.
void mpos_fatal_jump(void) {
    mp_obj_t exc_type = mp_load_global(MP_QSTR_SystemExit);
    mp_obj_t args[1];
    args[0] = mp_obj_new_str("duke3d engine ended", 20);
    mp_obj_t exc = mp_call_function_n_kw(exc_type, 1, 0, args);
    mp_fun_table.raise(exc);
}

// -- module functions -------------------------------------------------------

static mp_obj_t nat_surface(size_t n_args, const mp_obj_t *args) {
    if (n_args != 5) {
        mp_raise_TypeError("surface() takes 5 arguments");
    }
    if (args[0] == mp_const_none || args[4] == mp_const_none) {
        g_frame = NULL;
        g_present_obj = mp_const_none;
        return mp_const_none;
    }
    mp_buffer_info_t buffer;
    mp_get_buffer_raise(args[0], &buffer, MP_BUFFER_WRITE);
    const int width = (int)mp_obj_get_int(args[1]);
    const int height = (int)mp_obj_get_int(args[2]);
    const int band_rows = (int)mp_obj_get_int(args[3]);
    if (width < 1 || height < 1 || band_rows < 1) {
        mp_raise_ValueError("surface size and band width must be positive");
    }
    if (buffer.len / 2 < (size_t)width * (size_t)height) {
        mp_raise_ValueError("destination too small");
    }
    g_frame = (uint16_t *)buffer.buf;
    g_frame_width = width;
    g_frame_height = height;
    g_band_rows = band_rows;
    g_present_obj = args[4];
    s_abi.frame = g_frame;
    s_abi.frame_width = width;
    s_abi.frame_height = height;
    s_abi.band_rows = band_rows;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(nat_surface_obj, 5, 5, nat_surface);

static void nat_setup_abi(void) {
    memset(&s_abi, 0, sizeof(s_abi));
    s_abi.version = MPOS_CORE_ABI_VERSION;
    s_abi.present_band = nat_present_band;
    s_abi.palette = nat_palette;
    s_abi.poll_key = nat_poll_key;
    s_abi.now_ms = nat_now_ms;
    s_abi.read_file = nat_read_file;
    s_abi.file_size = nat_file_size_cb;
    s_abi.alloc = nat_alloc;
    s_abi.dealloc = nat_dealloc;
    s_abi.log = nat_log;
    s_abi.frame = g_frame;
    s_abi.frame_width = g_frame_width;
    s_abi.frame_height = g_frame_height;
    s_abi.band_rows = g_band_rows;
    s_abi.yield = nat_yield;
    s_abi.file_request = nat_file_request;
}

// The engine's script keeps addresses as 32-bit words (`(int32_t)scriptptr`),
// which is correct where a pointer is 32 bits. A 64-bit host has to put that
// one array below 4 GB or every stored actor/state address is truncated. A
// raw mmap(MAP_32BIT) syscall does that; a non-x86 host falls back to the
// ordinary module allocator (where 32-bit pointers are the native size).
static void *nat_map_low(size_t bytes) {
#if defined(__x86_64__) && defined(__linux__)
    register long r10 __asm__("r10") = 0x02 | 0x20 | 0x40;  // PRIVATE|ANON|32BIT
    register long r8 __asm__("r8") = -1;
    register long r9 __asm__("r9") = 0;
    long result;
    __asm__ volatile("syscall"
                     : "=a"(result)
                     : "a"(9L)  // SYS_mmap
                     , "D"(0L), "S"(bytes), "d"(3L)  // PROT_READ|PROT_WRITE
                     , "r"(r10), "r"(r8), "r"(r9)
                     : "rcx", "r11", "memory");
    if (result < 0 && result > -4096) {
        return NULL;
    }
    return (void *)result;
#else
    return mp_fun_table.realloc_(NULL, bytes, false);
#endif
}

static mp_uint_t nat_copy_str(char *dst, size_t size, mp_obj_t object) {
    size_t len = 0;
    const char *text = mp_obj_str_get_data(object, &len);
    if (len >= size) {
        len = size - 1;
    }
    memcpy(dst, text, len);
    dst[len] = '\0';
    return len;
}

static mp_obj_t nat_start(size_t n_args, const mp_obj_t *args) {
    if (n_args != 4) {
        mp_raise_TypeError("start() takes 4 arguments");
    }
    g_quit = 0;
    g_key_head = 0;
    g_key_tail = 0;
    // The engine's timer is installed during start-up and takes its base from
    // SDL_GetTicks() (= this clock). Leaving it at 0 here makes the first
    // tick() look like the whole host uptime elapsed at once: totalclock jumps
    // ahead of ototalclock for good, and every faketimerhandler() call in the
    // renderer then counts as a game tic, so a held key moves the player at
    // hundreds of frames a second. The host passes its clock so start-up and
    // ticks are on the same timeline.
    g_now_ms = (uint32_t)mp_obj_get_int(args[3]);
    nat_copy_str(g_asset_name, sizeof(g_asset_name), args[1]);
    nat_copy_str(g_config_dir, sizeof(g_config_dir), args[2]);
    g_asset = NULL;
    g_asset_len = 0;
    g_asset_path[0] = '\0';
    g_asset_obj = args[0];
    if (args[0] != mp_const_none && mp_obj_is_str(args[0])) {
        // A real file (a full/Atomic GRP on a desktop or the SD card): the
        // engine reads it through read_file(), not through storage.
        nat_copy_str(g_asset_path, sizeof(g_asset_path), args[0]);
    } else if (args[0] != mp_const_none) {
        mp_buffer_info_t asset;
        mp_get_buffer_raise(args[0], &asset, MP_BUFFER_READ);
        g_asset = (const uint8_t *)asset.buf;
        g_asset_len = asset.len;
    }
    mpos_duke_asset_data = g_asset;
    mpos_duke_asset_size = (uint32_t)g_asset_len;
    nat_setup_abi();
    mpos_libc_init(&s_abi);
    duke_platform_init(&s_abi);
    duke_platform_set_running(0);
    // The CON script's stored addresses are 32-bit words; see nat_map_low.
    if (script == NULL) {
        script = (int32_t *)nat_map_low(MAXSCRIPTSIZE * sizeof(int32_t));
        if (script == NULL) {
            mp_raise_msg(&mp_type_RuntimeError,
                         "Duke3D cannot map its script below 4 GB");
        }
    }
    // Initialised engine data lives in BSS in a native module; the build
    // generated one copy function per file.
    duke_init_all_data();

    // A second session in the same process reuses the engine's globals: main()
    // re-initialises the caches and returns at its loop, which is how the core
    // gets a fresh arena each time.
    g_running = 0;

    if (g_heap == NULL) {
        const uint32_t wanted[7] = {
            8u * 1024u * 1024u, 6u * 1024u * 1024u, 4u * 1024u * 1024u,
            3u * 1024u * 1024u, 2u * 1024u * 1024u, 1536u * 1024u,
            1024u * 1024u,
        };
        for (int i = 0; i < 7; i++) {
            g_heap = nat_map_low(wanted[i]);
            if (g_heap != NULL) {
                g_heap_bytes = wanted[i];
                break;
            }
        }
    }
    if (g_heap == NULL) {
        mp_raise_msg(&mp_type_RuntimeError, "Duke3D needs at least 768 KB");
    }
    // A restart reuses the mapping but starts the allocator from scratch.
    mpos_heap_init(g_heap, g_heap_bytes);
    {
        char line[64];
        snprintf(line, sizeof(line), "natmod: heap %u KB",
                 (unsigned)(g_heap_bytes / 1024));
        nat_log(NULL, line);
    }

    char *argv[2];
    argv[0] = (char *)"duke3d";
    argv[1] = NULL;
    duke_platform_set_running(0);
    duke_engine_main(1, argv);
    duke_platform_set_running(1);
    g_created = 1;
    g_running = 1;
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(nat_start_obj, 4, 4, nat_start);

static mp_obj_t nat_tick(mp_obj_t now_obj) {
    if (!g_created || !g_running) {
        return mp_const_none;
    }
    g_now_ms = (uint32_t)mp_obj_get_int(now_obj);
    if (!duke_run_frame()) {
        g_quit = 1;
    }
    if (rg_system_should_exit() || mpos_libc_exit_requested()) {
        g_quit = 1;
    }
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(nat_tick_obj, nat_tick);

static mp_obj_t nat_key(mp_obj_t code_obj, mp_obj_t pressed_obj) {
    const int next = (g_key_head + 1) % NATMOD_MAX_KEYS;
    if (next == g_key_tail) {
        return mp_const_false;
    }
    const int code = (int)mp_obj_get_int(code_obj);
    const int pressed = mp_obj_is_true(pressed_obj);
    g_keys[g_key_head] = (uint16_t)((pressed ? 0x100 : 0) | (code & 0xFF));
    g_key_head = next;
    return mp_const_true;
}
static MP_DEFINE_CONST_FUN_OBJ_2(nat_key_obj, nat_key);

static mp_obj_t nat_stop(void) {
    g_running = 0;
    duke_platform_set_running(0);
    g_key_head = 0;
    g_key_tail = 0;
    // The engine's timer keeps the base it was installed with, and keeps it in
    // the module's BSS across sessions. A later start() would then neither
    // re-install it nor take the clock it is given as its base: a test that
    // simulates a clock gets a dead one, and a relaunched app drags the old
    // session's base along. Dropping it here makes every start its own.
    uninittimer();
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(nat_stop_obj, nat_stop);

static mp_obj_t nat_quit_requested(void) {
    if (g_quit || rg_system_should_exit() || mpos_libc_exit_requested()) {
        return mp_const_true;
    }
    return mp_const_false;
}
static MP_DEFINE_CONST_FUN_OBJ_0(nat_quit_requested_obj, nat_quit_requested);

static mp_obj_t nat_width(void) {
    return mp_obj_new_int(320);
}
static MP_DEFINE_CONST_FUN_OBJ_0(nat_width_obj, nat_width);

static mp_obj_t nat_height(void) {
    return mp_obj_new_int(200);
}
static MP_DEFINE_CONST_FUN_OBJ_0(nat_height_obj, nat_height);

// The menu's save/load actions are ordinary engine functions; exposing them
// lets a desktop test exercise the real file path (the /saves mapping and the
// host's writes) without walking the menu with a pointer.
extern int saveplayer(int8_t spot);
extern int loadplayer(int8_t spot);

static mp_obj_t nat_save_slot(mp_obj_t spot_obj) {
    return mp_obj_new_int(saveplayer((int8_t)mp_obj_get_int(spot_obj)));
}
static MP_DEFINE_CONST_FUN_OBJ_1(nat_save_slot_obj, nat_save_slot);

static mp_obj_t nat_load_slot(mp_obj_t spot_obj) {
    return mp_obj_new_int(loadplayer((int8_t)mp_obj_get_int(spot_obj)));
}
static MP_DEFINE_CONST_FUN_OBJ_1(nat_load_slot_obj, nat_load_slot);

// Player position, angle and the engine's two clocks, so a host test can
// measure movement and tic pacing instead of guessing from a picture.
extern struct player_struct ps[MAXPLAYERS];
static mp_obj_t nat_pos(void) {
    const int i = myconnectindex;
    if (i < 0 || i >= MAXPLAYERS) {
        return mp_const_none;
    }
    mp_obj_t items[10];
    items[0] = mp_obj_new_int(ps[i].posx);
    items[1] = mp_obj_new_int(ps[i].posy);
    items[2] = mp_obj_new_int(ps[i].ang);
    items[3] = mp_obj_new_int(totalclock);
    items[4] = mp_obj_new_int(ps[i].cursectnum);
    items[5] = mp_obj_new_int(ototalclock);
    items[6] = mp_obj_new_int(movefifoend[i] - movefifoplc);
    items[7] = mp_obj_new_int(KB_KeyDown[sc_UpArrow] ? 1 : 0);
    items[8] = mp_obj_new_int(ps[i].posxv + ps[i].posyv);
    items[9] = mp_obj_new_int(ps[i].posz);
    return mp_obj_new_tuple(10, items);
}
static MP_DEFINE_CONST_FUN_OBJ_0(nat_pos_obj, nat_pos);

static mp_obj_t nat_debug_state(void) {
    mp_printf(&mp_plat_print,
              "[duke] created=%d running=%d quit=%d connect=%d ticks=%u\n",
              g_created, g_running, g_quit, (int)myconnectindex,
              (unsigned)g_now_ms);
    return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_0(nat_debug_state_obj, nat_debug_state);

mp_obj_t mpy_init(mp_obj_fun_bc_t *self, size_t n_args, size_t n_kw,
                  mp_obj_t *args) {
    MP_DYNRUNTIME_INIT_ENTRY

    g_asset_obj = mp_const_none;
    g_present_obj = mp_const_none;
    g_open_fun = mp_const_none;
    g_io_module = mp_const_none;
    nat_setup_abi();

    mp_store_global(MP_QSTR_surface, MP_OBJ_FROM_PTR(&nat_surface_obj));
    mp_store_global(MP_QSTR_start, MP_OBJ_FROM_PTR(&nat_start_obj));
    mp_store_global(MP_QSTR_tick, MP_OBJ_FROM_PTR(&nat_tick_obj));
    mp_store_global(MP_QSTR_key, MP_OBJ_FROM_PTR(&nat_key_obj));
    mp_store_global(MP_QSTR_stop, MP_OBJ_FROM_PTR(&nat_stop_obj));
    mp_store_global(MP_QSTR_quit_requested,
                    MP_OBJ_FROM_PTR(&nat_quit_requested_obj));
    mp_store_global(MP_QSTR_width, MP_OBJ_FROM_PTR(&nat_width_obj));
    mp_store_global(MP_QSTR_height, MP_OBJ_FROM_PTR(&nat_height_obj));
    mp_store_global(MP_QSTR_debug_state, MP_OBJ_FROM_PTR(&nat_debug_state_obj));
    mp_store_global(MP_QSTR_pos, MP_OBJ_FROM_PTR(&nat_pos_obj));
    mp_store_global(MP_QSTR_save_slot, MP_OBJ_FROM_PTR(&nat_save_slot_obj));
    mp_store_global(MP_QSTR_load_slot, MP_OBJ_FROM_PTR(&nat_load_slot_obj));

    MP_DYNRUNTIME_INIT_EXIT
}
