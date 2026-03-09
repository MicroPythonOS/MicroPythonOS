MPY_DIR = ../../lvgl_micropython/lib/micropython/

# Name of module
MOD = mpong

# Source files (.c or .py)
SRC = mpong.c

# Link runtime libraries (needed for memset on xtensawin)
LINK_RUNTIME = 1

# Architectures to build for (x86, x64, armv6m, armv7m, xtensa, xtensawin, rv32imc, rv64imc)
ARCHES = x64 xtensawin

ifeq ($(ARCH),)
.PHONY: all $(ARCHES)

all: $(ARCHES)

$(ARCHES):
	$(MAKE) -f $(lastword $(MAKEFILE_LIST)) ARCH=$@ MOD=$(MOD)_$@
else
# Include to get the rules for compiling and linking the module
include $(MPY_DIR)/py/dynruntime.mk
endif
