MPY_DIR = ../../lvgl_micropython/lib/micropython/

# The plain probe and the Doom-sized variant are two modules built from the same
# source: framecore_big adds ~256 KB of const tables and ~256 KB of BSS, which is
# what a real engine module weighs.
PLAIN = framecore_probe
BIG = framecore_big

MOD ?= $(PLAIN)
SRC = framecore_probe.c libc_shim.c

# libgcc/libm are linked (the xtensawin module needs memset); libc is not, which
# is the point of libc_shim.c.
LINK_RUNTIME = 1

ARCHES = x64 xtensawin

ifeq ($(ARCH),)
.PHONY: all $(ARCHES) big

all: $(ARCHES)

$(ARCHES):
	$(MAKE) -f $(lastword $(MAKEFILE_LIST)) ARCH=$@ MOD=$(PLAIN)_$@ BUILD=build_$@
	$(MAKE) -f $(lastword $(MAKEFILE_LIST)) ARCH=$@ MOD=$(BIG)_$@ BUILD=build_big_$@ \
		CFLAGS_EXTRA=-DFRAMECORE_BIG=1
else
include $(MPY_DIR)/py/dynruntime.mk
endif
