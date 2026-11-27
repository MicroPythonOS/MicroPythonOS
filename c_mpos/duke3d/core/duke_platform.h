#ifndef MPOS_DUKE_PLATFORM_H
#define MPOS_DUKE_PLATFORM_H

#include "../../core_abi.h"

// Set once by core_init and read by the SDL shims.
void duke_platform_init(const mpos_core_abi_t *abi);
const mpos_core_abi_t *duke_platform_abi(void);

// Called by the video path so the core can profile a frame and the host can
// be sure the engine is making progress.
void duke_platform_frame_started(void);
void duke_platform_frame_presented(void);
void duke_platform_add_convert(uint32_t ms);
void duke_platform_add_present(uint32_t ms);
void duke_platform_add_engine(uint32_t ms);
void duke_platform_add_wait(uint32_t ms);

// A no-op in a core (there is no scheduler to yield to), but it is where the
// retro-go shims park their SDL_Delay/vTaskDelay calls.
void duke_platform_idle(void);
uint32_t duke_platform_ticks(void);
void duke_platform_progress(int permille, const char *text);

// Diagnostics for the MicroPython task stack: record the lowest stack pointer
// seen from the engine and name the phase that reached it.
void duke_platform_stack_mark(const char *tag);

// The engine's exit request (its "quit" menu entry or a fatal error).
void duke_platform_request_exit(void);
int duke_platform_exit_requested(void);

// 0 during the engine's start-up (the host surface is not live yet), 1 once
// the first tick can present. SDL_Flip skips its callback work while it is 0.
void duke_platform_set_running(int running);
int duke_platform_running(void);

// 1 while the engine's menus (not the game) are up. Used to let the fire
// button confirm in a menu.
int duke_in_menu(void);

// The native-module host can hand the GRP over as one contiguous buffer, so
// the engine's archive can be memory-backed instead of doing 64 KB read
// allocations through the ABI. NULL when the asset is a file.
extern const uint8_t *mpos_duke_asset_data;
extern uint32_t mpos_duke_asset_size;

#endif
