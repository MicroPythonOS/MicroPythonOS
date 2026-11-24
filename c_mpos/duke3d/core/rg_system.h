/* The small part of retro-go the Duke engine still names.
 *
 * The engine was written against retro-go: it allocates with rg_alloc, reads
 * settings, asks the launcher for its ROM path and has a settings screen that
 * pokes the display and audio drivers. In a core blob there is no retro-go and
 * no firmware to call, so these are answered by the platform layer
 * (duke_platform.c) from the core ABI. The header keeps the engine sources
 * unchanged; where a service makes no sense (there is no settings store, no SD
 * card, no audio sink on this panel) it degrades to a no-op.
 */
#ifndef MPOS_DUKE_RG_SYSTEM_H
#define MPOS_DUKE_RG_SYSTEM_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Allocation flags: the core has one heap, so they are only hints. */
#define MEM_SLOW 0x0
#define MEM_FAST 0x1
#define MEM_DMA 0x2
#define MEM_NOPANIC 0x4

/* The launcher's view of the running app. Only romPath is read here. */
typedef struct {
    const char *romPath;
} rg_app_t;

/* Display scaling and backlight are the OS's business; the engine's
 * "Retro-Go options" screen reads and writes them, so they need a value. */
typedef enum {
    RG_DISPLAY_SCALING_OFF = 0,
    RG_DISPLAY_SCALING_FIT,
    RG_DISPLAY_SCALING_FULL,
    RG_DISPLAY_SCALING_ZOOM,
    RG_DISPLAY_SCALING_COUNT
} display_scaling_t;

typedef enum {
    RG_DISPLAY_BACKLIGHT_MIN = 1,
    RG_DISPLAY_BACKLIGHT_MAX = 100,
} display_backlight_t;

/* Audio sinks: the engine's options screen wants a list. A badge with no PCM
 * output answers with none, which is what makes the screen harmless. */
typedef struct {
    const char *name;
    bool (*init)(int device, int sample_rate);
    bool (*deinit)(void);
    bool (*submit)(const void *frames, size_t count);
    bool (*set_mute)(bool mute);
    bool (*set_volume)(int percent);
    bool (*set_sample_rate)(int sample_rate);
    const char *(*get_error)(void);
} rg_audio_driver_t;

typedef struct {
    const rg_audio_driver_t *driver;
    int device;
    const char *name;
} rg_audio_sink_t;

#define RG_BASE_PATH_SAVES "/saves"
#define RG_BASE_PATH_CONFIG "/config"
#define RG_BASE_PATH_ROMS "/roms"

typedef enum {
    RG_PATH_SCREENSHOT = 0x300,
    RG_PATH_SAVE_STATE = 0x301,
} rg_path_type_t;

#define NS_APP "app"

#define RG_LOGE(...) mpos_duke_log(__VA_ARGS__)
#define RG_LOGW(...) mpos_duke_log(__VA_ARGS__)
#define RG_LOGI(...) mpos_duke_log(__VA_ARGS__)
#define RG_LOGD(...) mpos_duke_log(__VA_ARGS__)
#define RG_LOGV(...) mpos_duke_log(__VA_ARGS__)
#define RG_PANIC(...) mpos_duke_log(__VA_ARGS__)
#define ESP_LOGV(tag, ...) do { (void)(tag); } while (0)
#define ESP_LOGD(tag, ...) do { (void)(tag); } while (0)

void mpos_duke_log(const char *fmt, ...);

void *rg_alloc(size_t size, uint32_t flags);
void *rg_calloc(size_t nmemb, size_t size);
void rg_free(void *ptr);

const rg_app_t *rg_system_get_app(void);
bool rg_system_should_exit(void);
void rg_system_request_exit(void);
void rg_system_tick(uint32_t micros);
int rg_system_get_cpu_speed(void);
int rg_system_get_overclock(void);
void rg_system_set_overclock(int level);
void rg_system_reinit(int sample_rate, void *handlers, void *config);
void rg_system_set_log_level(int level);

extern const int RG_LOG_WARN;

bool rg_storage_exists(const char *path);
bool rg_storage_mkdir(const char *path);
void rg_storage_commit(void);
bool rg_storage_unzip_file(const char *path, const char *filename,
                           void **data, size_t *size, int flags);
char *rg_emu_get_path(rg_path_type_t type, const char *arg);
char *rg_dirname(char *path);
bool rg_extension_match(const char *path, const char *extension);

bool rg_settings_exists(const char *ns, const char *key);
void rg_settings_commit(void);

const rg_audio_sink_t *rg_audio_get_sinks(size_t *count);
const rg_audio_sink_t *rg_audio_get_sink(void);
void rg_audio_set_sink(const char *driver_name, int device);
int rg_audio_get_volume(void);
void rg_audio_set_volume(int percent);
bool rg_audio_get_mute(void);
void rg_audio_set_mute(bool mute);
int rg_audio_get_sample_rate(void);
void rg_audio_set_sample_rate(int sample_rate);

void rg_display_set_scaling(display_scaling_t scaling);
display_scaling_t rg_display_get_scaling(void);
void rg_display_set_backlight(display_backlight_t percent);
display_backlight_t rg_display_get_backlight(void);

/* FreeRTOS calls that leak in through the options screen. The core has no
 * scheduler of its own, so a delay is a no-op. */
void mpos_duke_delay_ms(uint32_t ms);
#define vTaskDelay(ms) mpos_duke_delay_ms((uint32_t)(ms))
#define pdMS_TO_TICKS(ms) (ms)

#endif
