/* FEATURE_SOUND makes chocolate-doom's i_sound.c include SDL_mixer.h, but it
 * uses nothing from it: the module interface is sound_module_t, and this core
 * provides its own module (core_sound.c). An empty header keeps the include
 * from dragging SDL into a freestanding build. */
