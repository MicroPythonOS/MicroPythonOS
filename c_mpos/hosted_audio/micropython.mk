################################################################################
# hosted_audio build rules (PCM sink for hosts without machine.I2S).
#
# The backend is SDL's audio, so there is one implementation for every host:
#
#   * WebAssembly: Emscripten's SDL2 port implements it over WebAudio
#     (-sUSE_SDL=2 is already part of that build for display and input).
#   * Linux desktop: the bundled SDL is built with SDL_ALSA=ON, so its ALSA
#     backend links libasound. The desktop binary is linked dynamically for
#     exactly this reason (patches/unix_desktop_dynamic.patch): a static binary
#     cannot link libasound, and a statically linked alsa-lib was measured to be
#     unusable (its config parser spins, and without the plugin layer it can
#     only take the card exclusively).
#
# macOS builds SDL itself (sdl2 framework or brew); audio there needs the
# same module but has not been wired or tested yet.

MOD_DIR := $(USERMOD_DIR)

ifeq ($(MPOS_WEB),1)
    CFLAGS_USERMOD += -DMICROPY_PY_HOSTED_AUDIO=1 -DMICROPY_PY_HOSTED_AUDIO_SDL=1
    CFLAGS_USERMOD += -sUSE_SDL=2
    SRC_USERMOD_C += $(MOD_DIR)/mod_hosted_audio.c
else ifneq (,$(findstring unix, $(LV_PORT)))
    CFLAGS_USERMOD += -DMICROPY_PY_HOSTED_AUDIO=1 -DMICROPY_PY_HOSTED_AUDIO_SDL=1
    CFLAGS_USERMOD += -I$(BUILD)/SDL/include/SDL2
    CFLAGS_USERMOD += -I$(BUILD)/SDL/include-config-release/SDL2
    SRC_USERMOD_C += $(MOD_DIR)/mod_hosted_audio.c
    LDFLAGS_USERMOD += -L$(BUILD)/SDL -lSDL2
endif
