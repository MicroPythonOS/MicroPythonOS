# _webio build rules (MicroPythonOS web/Emscripten target only).
#
# Discovered automatically by MicroPython's USER_C_MODULES Makefile mechanism
# (USER_C_MODULES points at lvgl_micropython/ext_mod). The source is only added
# for the web build (MPOS_WEB=1); on native unix / other ports it compiles to
# nothing, so this module never affects non-web builds.

WEBIO_MOD_DIR := $(USERMOD_DIR)

ifeq ($(MPOS_WEB),1)
    SRC_USERMOD_C += $(WEBIO_MOD_DIR)/webio.c
endif
