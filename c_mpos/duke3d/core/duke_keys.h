#ifndef MPOS_DUKE_KEYS_H
#define MPOS_DUKE_KEYS_H

/* The key protocol between the app and the core.
 *
 * The host's poll_key() packs a code into 8 bits with the press bit above it
 * (the mpos_core ABI's convention), so the codes must fit a byte. SDL keycodes
 * do not - arrows and modifiers are scancode|512 - so the app sends these
 * small names and the core maps them to the engine's SDL keys. Keep in step
 * with duke_controls.py. */
#define DUKE_KEY_LEFT   1
#define DUKE_KEY_RIGHT  2
#define DUKE_KEY_UP     3
#define DUKE_KEY_DOWN   4
#define DUKE_KEY_FIRE   5
#define DUKE_KEY_JUMP   6
#define DUKE_KEY_CROUCH 7
#define DUKE_KEY_USE    8
#define DUKE_KEY_MENU   9
#define DUKE_KEY_WEAPON 10
#define DUKE_KEY_ENTER  11
#define DUKE_KEY_MAP    12

#endif
