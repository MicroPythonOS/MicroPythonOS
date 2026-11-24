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

// A no-op in a core (there is no scheduler to yield to), but it is where the
// retro-go shims park their SDL_Delay/vTaskDelay calls.
void duke_platform_idle(void);

// Diagnostics for the 16 KB MicroPython task stack: the lowest stack pointer
// seen from the engine, relative to where core_init entered.
void duke_platform_stack_mark(void);
unsigned duke_platform_stack_used(void);

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

#endif
