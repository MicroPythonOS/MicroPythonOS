// SDL events from the core ABI's key queue.
//
// The engine polls SDL_PollEvent until it returns 0, so each call hands over at
// most one queued key. The app's controls are touch zones, but the engine's
// menus still expect arrows and Enter, so fire/use double as "confirm" while a
// menu is up - exactly what a console pad does.

#include <string.h>

#include "SDL.h"
#include "duke3d.h"
#include "duke_keys.h"
#include "duke_platform.h"

// Defined in game.c (the engine's global player array and connection index).
extern struct player_struct ps[];
extern short myconnectindex;

// keyboard.c reads the input mode through this (1 = game keys).
int keyMode = 1;

static int code_to_sym(int code) {
    switch (code) {
        case DUKE_KEY_LEFT:   return SDLK_LEFT;
        case DUKE_KEY_RIGHT:  return SDLK_RIGHT;
        case DUKE_KEY_UP:     return SDLK_UP;
        case DUKE_KEY_DOWN:   return SDLK_DOWN;
        case DUKE_KEY_FIRE:   return SDLK_LCTRL;
        case DUKE_KEY_JUMP:   return SDLK_a;
        case DUKE_KEY_CROUCH: return SDLK_z;
        case DUKE_KEY_USE:    return SDLK_SPACE;
        case DUKE_KEY_MENU:   return SDLK_ESCAPE;
        case DUKE_KEY_WEAPON: return SDLK_QUOTE;
        case DUKE_KEY_ENTER:  return SDLK_RETURN;
        case DUKE_KEY_MAP:    return SDLK_TAB;
        default:              return SDLK_UNKNOWN;
    }
}

int duke_in_menu(void) {
    return myconnectindex >= 0 && (ps[myconnectindex].gm & 1);
}

int SDL_PollEvent(SDL_Event *event) {
    if (event == NULL) {
        return 0;
    }
    const mpos_core_abi_t *abi = duke_platform_abi();
    if (abi == NULL) {
        return 0;
    }
    int pressed = 0;
    int code = abi->poll_key(abi->host, &pressed);
    if (code < 0) {
        return 0;
    }
    // A badge has no Enter key. In the menus, the button a player calls "fire"
    // (A) and the one they call "use" (Y) both mean "select"; in the game they
    // keep their own meaning.
    if (duke_in_menu() && (code == DUKE_KEY_FIRE || code == DUKE_KEY_USE)) {
        code = DUKE_KEY_ENTER;
    }
    const int sym = code_to_sym(code);
    if (sym == SDLK_UNKNOWN) {
        return SDL_PollEvent(event);  // drop it, ask again
    }
    memset(event, 0, sizeof(*event));
    event->key.type = pressed ? SDL_KEYDOWN : SDL_KEYUP;
    event->key.state = pressed ? SDL_PRESSED : SDL_RELEASED;
    event->key.keysym.sym = sym;
    event->key.keysym.scancode = 0;
    event->key.keysym.mod = 0;
    return 1;
}

Uint8 SDL_EventState(Uint32 type, int state) {
    (void)type;
    (void)state;
    return 0;
}
