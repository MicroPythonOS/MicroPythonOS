// SDL's system half on top of the core ABI: clock, delay, error strings and
// the mutex/thread helpers. A core is single-threaded, so the mutexes are
// placeholders and a delay is a no-op (the host paces frames; sleeping inside
// a tick would only steal time from the panel transfer).

#include <stddef.h>
#include <stdlib.h>

#include "SDL.h"
#include "../../core_abi.h"
#include "duke_platform.h"

struct SDL_mutex {
    int unused;
};

int SDL_Init(Uint32 flags) {
    if (flags & SDL_INIT_VIDEO) {
        SDL_InitSubSystem(flags);
    }
    return 0;
}

void SDL_Quit(void) {}

void SDL_Delay(Uint32 ms) {
    (void)ms;
    duke_platform_idle();
}

char *SDL_GetError(void) {
    return (char *)"";
}

void SDL_ClearError(void) {}

const SDL_version *SDL_Linked_Version(void) {
    static SDL_version version = {SDL_MAJOR_VERSION, SDL_MINOR_VERSION,
                                  SDL_PATCHLEVEL};
    return &version;
}

Uint32 SDL_GetTicks(void) {
    const mpos_core_abi_t *abi = duke_platform_abi();
    return abi != NULL ? abi->now_ms(abi->host) : 0;
}

char **allocateTwoDimenArrayOnHeapUsingMalloc(int row, int col) {
    char **ptr = (char **)malloc((size_t)row * sizeof(char *)
                                 + (size_t)row * col);
    if (ptr == NULL) {
        return NULL;
    }
    char *data = (char *)(ptr + row);
    for (int i = 0; i < row; i++) {
        ptr[i] = data + (size_t)i * col;
    }
    return ptr;
}

void SDL_DestroyMutex(SDL_mutex *mutex) {
    (void)mutex;
}

SDL_mutex *SDL_CreateMutex(void) {
    return (SDL_mutex *)calloc(1, sizeof(SDL_mutex));
}

int SDL_LockMutex(SDL_mutex *mutex) {
    (void)mutex;
    return 0;
}

int SDL_UnlockMutex(SDL_mutex *mutex) {
    (void)mutex;
    return 0;
}

int SDL_putenv(const char *variable) {
    (void)variable;
    return 0;
}

Uint32 SDL_GetMouseState(int *x, int *y) {
    if (x != NULL) *x = 0;
    if (y != NULL) *y = 0;
    return 0;
}

void SDL_WarpMouse(Uint16 x, Uint16 y) {
    (void)x;
    (void)y;
}
