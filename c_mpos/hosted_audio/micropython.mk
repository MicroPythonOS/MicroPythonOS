################################################################################
# hosted_audio build rules (PCM sink for hosts without machine.I2S).
#
# The backend is SDL's audio. The web build gets it from Emscripten's SDL2 port
# (WebAudio) with -sUSE_SDL=2, which is already part of that build for display
# and input. A Linux desktop has the bundled SDL built with every audio backend
# off (SDL_ALSA=OFF in builder/unix.py), so the module is not built there yet: a
# shared libasound cannot be linked into a static binary, and the static
# alsa-lib route was measured to be unusable (its config parsing spins, and a
# config without the plugin layer can only grab the card exclusively). Turning
# SDL_ALSA=ON is the one-line change that would enable it, at the cost of the
# binary becoming dynamically linked; that is a distribution decision.

MOD_DIR := $(USERMOD_DIR)

ifeq ($(MPOS_WEB),1)
    CFLAGS_USERMOD += -DMICROPY_PY_HOSTED_AUDIO=1 -DMICROPY_PY_HOSTED_AUDIO_SDL=1
    CFLAGS_USERMOD += -sUSE_SDL=2
    SRC_USERMOD_C += $(MOD_DIR)/mod_hosted_audio.c
endif
