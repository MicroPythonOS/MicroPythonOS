// No joysticks: the engine's own joystick path is disabled when the device
// reports none, and a badge's controls arrive as touch zones through the key
// queue instead.

#include "SDL.h"

int SDL_NumJoysticks(void) {
    return 0;
}

SDL_Joystick *SDL_JoystickOpen(int device_index) {
    (void)device_index;
    return NULL;
}

const char *SDL_JoystickName(SDL_Joystick *joystick) {
    (void)joystick;
    return "";
}

int SDL_JoystickNumAxes(SDL_Joystick *joystick) {
    (void)joystick;
    return 0;
}

int SDL_JoystickNumBalls(SDL_Joystick *joystick) {
    (void)joystick;
    return 0;
}

int SDL_JoystickNumHats(SDL_Joystick *joystick) {
    (void)joystick;
    return 0;
}

int SDL_JoystickNumButtons(SDL_Joystick *joystick) {
    (void)joystick;
    return 0;
}

Sint16 SDL_JoystickGetAxis(SDL_Joystick *joystick, int axis) {
    (void)joystick;
    (void)axis;
    return 0;
}

Uint8 SDL_JoystickGetHat(SDL_Joystick *joystick, int hat) {
    (void)joystick;
    (void)hat;
    return 0;
}

Uint8 SDL_JoystickGetButton(SDL_Joystick *joystick, int button) {
    (void)joystick;
    (void)button;
    return 0;
}

void SDL_JoystickClose(SDL_Joystick *joystick) {
    (void)joystick;
}

void SDL_JoystickUpdate(void) {}

int SDL_JoystickEventState(int state) {
    (void)state;
    return 0;
}


SDL_GrabMode SDL_WM_GrabInput(SDL_GrabMode mode) {
    (void)mode;
    return SDL_GRAB_ON;
}

int SDL_ShowCursor(int toggle) {
    (void)toggle;
    return 0;
}

void SDL_SetModState(SDL_Keymod modstate) {
    (void)modstate;
}
