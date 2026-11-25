MPY_DIR = ../../lvgl_micropython/lib/micropython/

# Duke Nukem 3D as a MicroPython native module (desktop).
#
#   make            -> module_x64.mpy
#
# The engine sources are rewritten into gen/ by tools/prepare.py first, because
# a native module has no data section and no static BSS (see that script). The
# flash-resident core build (build_duke_core.sh) keeps compiling the pristine
# sources: it has a real .data/.bss arena.
#
# MOD is the file name the app imports: module_<mpy-arch>.mpy, the name the
# installer selects from the manifest's "native" map.

CORE = \
	gen/duke_audio.c gen/duke_libc.c gen/duke_platform.c gen/lodepng.c \
	gen/sdl_event.c gen/sdl_input.c gen/sdl_system.c gen/sdl_video.c

GAME = \
	gen/Game/actors.c gen/Game/animlib.c gen/Game/config.c \
	gen/Game/console.c gen/Game/control.c gen/Game/cvar_defs.c \
	gen/Game/cvars.c gen/Game/dummy_audiolib.c gen/Game/game.c \
	gen/Game/gamedef.c gen/Game/global.c gen/Game/keyboard.c \
	gen/Game/menues.c gen/Game/player.c gen/Game/premap.c gen/Game/rts.c \
	gen/Game/scriplib.c gen/Game/sector.c gen/Game/sounds.c

ENGINE = \
	gen/Engine/cache.c gen/Engine/display.c gen/Engine/draw.c \
	gen/Engine/engine.c gen/Engine/filesystem.c \
	gen/Engine/fixedPoint_math.c gen/Engine/mmulti.c \
	gen/Engine/network.c gen/Engine/tiles.c

SRC = natmod.c natmod_libc.c natmod_net.c gen/duke_data_init.c \
	gen/mpos_printf.c $(CORE) $(GAME) $(ENGINE)

LINK_RUNTIME = 1

ARCHES = x64

# MPOS_CORE keeps the badge's bounds checks, its direct level start (no Logo
# intro) and its sound-off defaults; MPOS_NATMOD is only for shims that need to
# know the host is a Python module. main() is renamed so natmod.c can call the
# engine's start-up and then drive duke_run_frame() itself.
CFLAGS_EXTRA += -DMPOS_CORE -DMPOS_NATMOD -DLINUX -D_DEFAULT_SOURCE
CFLAGS_EXTRA += -Dmain=duke_engine_main
# -fno-builtin: the compiler otherwise rewrites memcpy/printf into glibc calls
# (or into each other) that a native module does not link.
CFLAGS_EXTRA += -fno-builtin -fno-jump-tables
# mpy_ld handles R_X86_64_GOTPCREL but not the linker-relaxable
# R_X86_64_GOTPCRELX (41); keep the assembler from emitting the relaxed form.
CFLAGS_EXTRA += -Wa,-mrelax-relocations=no
CFLAGS_EXTRA += -Icore -Iengine/Game -Iengine/Engine -Iengine/SDL -Iaudiolib
CFLAGS_EXTRA += -Igen -I../doom -I../doom/core
# The engine is 1990s C and its warnings are not this build's gate; the host
# harness is where style is checked.
CFLAGS_EXTRA += -w -O2 -std=gnu99

.DEFAULT_GOAL := all

.PHONY: prepare
prepare:
	@python3 tools/prepare.py

ifeq ($(ARCH),)
.PHONY: all $(ARCHES) clean

all:
	$(MAKE) -f $(lastword $(MAKEFILE_LIST)) ARCH=x64 MOD=module_x64 BUILD=build_x64

clean:
	rm -rf build_x64 gen *.mpy .mpy_ld_cache

else
include $(MPY_DIR)/py/dynruntime.mk

# Everything compiles from the generated tree, so it has to exist first.
gen/%.c: prepare
	@:
$(CONFIG_H) $(SRC_O): | prepare
endif
