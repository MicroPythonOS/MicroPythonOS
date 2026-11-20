MPY_DIR = ../../lvgl_micropython/lib/micropython/

# The engine sources are vendored pristine in doomgeneric/ and rewritten into
# gen/ by tools/dataless.py at build time (a natmod has no data section and no
# static BSS). gen/ is generated, not committed.
#
# MOD is the file name the app imports: module_<mpy-arch>.mpy, the name the
# installer selects from the manifest's "native" map.
ENGINE = \
	gen/dummy.c gen/am_map.c gen/doomdef.c gen/doomstat.c gen/dstrings.c \
	gen/d_event.c gen/d_items.c gen/d_iwad.c gen/d_loop.c gen/d_main.c \
	gen/d_mode.c gen/d_net.c gen/f_finale.c gen/f_wipe.c gen/g_game.c \
	gen/hu_lib.c gen/hu_stuff.c gen/info.c gen/i_cdmus.c gen/i_endoom.c \
	gen/i_input.c gen/i_joystick.c gen/i_scale.c gen/i_sound.c \
	gen/i_system.c gen/i_timer.c gen/i_video.c gen/memio.c gen/m_argv.c \
	gen/m_bbox.c gen/m_cheat.c gen/m_config.c gen/m_controls.c gen/m_fixed.c \
	gen/m_menu.c gen/m_misc.c gen/m_random.c gen/p_ceilng.c gen/p_doors.c \
	gen/p_enemy.c gen/p_floor.c gen/p_inter.c gen/p_lights.c gen/p_map.c \
	gen/p_maputl.c gen/p_mobj.c gen/p_plats.c gen/p_pspr.c gen/p_saveg.c \
	gen/p_setup.c gen/p_sight.c gen/p_spec.c gen/p_switch.c gen/p_telept.c \
	gen/p_tick.c gen/p_user.c gen/r_bsp.c gen/r_data.c gen/r_draw.c \
	gen/r_main.c gen/r_plane.c gen/r_segs.c gen/r_sky.c gen/r_things.c \
	gen/sha1.c gen/sounds.c gen/statdump.c gen/st_lib.c gen/st_stuff.c \
	gen/s_sound.c gen/tables.c gen/v_video.c gen/wi_stuff.c gen/w_checksum.c \
	gen/w_file.c gen/w_file_stdc.c gen/w_main.c gen/w_wad.c gen/z_zone.c \
	gen/doomgeneric.c gen/doom_data_init.c

ENGINE_STEMS = $(patsubst gen/%.c,%,$(ENGINE))

# core_sound.c is the engine's own mixer, shared with the flash-resident core:
# the host pulls mixed samples with audio_mix() instead of the engine pushing
# them from a thread it does not have.
SRC = doomgeneric_mpos.c mpos_libc.c mpos_printf.c core/core_sound.c $(ENGINE)

LINK_RUNTIME = 1

ARCHES = x64 xtensawin

# CMAP256 makes the engine keep an 8-bit paletted framebuffer (pixel_t is
# uint8_t): the port converts it to RGB565 one band at a time while the panel
# is being fed, which is the only conversion cost this budget can afford.
# The engine is 1990s C; its warnings are not our build gate, but ours are.
# -fno-builtin: the compiler otherwise rewrites printf/puts into glibc calls
# (fputs(s, stdout)) that our shim's dummy stdout pointer cannot satisfy.
CFLAGS_EXTRA += -fno-builtin -Idoomgeneric -Igen -Icore -Icore/stub -DCMAP256 -DNORMALUNIX -DLINUX -D_DEFAULT_SOURCE
# The engine's sound module (core/core_sound.c) is part of the dataless tree's
# module list; without this the list is empty and S_Init finds no device.
CFLAGS_EXTRA += -DFEATURE_SOUND
CFLAGS_EXTRA += -Wno-error -Wno-unused-but-set-variable -Wno-unused-variable
CFLAGS_EXTRA += -Wno-sign-compare -Wno-missing-braces -Wno-implicit-fallthrough
CFLAGS_EXTRA += -Wno-pointer-sign -Wno-stringop-truncation -Wno-array-bounds
CFLAGS_EXTRA += -Wno-strict-aliasing -Wno-format -Wno-unused-function
# Jump tables on xtensa use R_XTENSA_NDIFF32, which mpy_ld does not relocate.
CFLAGS_EXTRA += -fno-jump-tables

.DEFAULT_GOAL := all

.PHONY: prepare
prepare:
	@python3 tools/dataless.py doomgeneric gen $(ENGINE_STEMS)

ifeq ($(ARCH),)
.PHONY: all $(ARCHES) clean

all:
	$(MAKE) -f $(lastword $(MAKEFILE_LIST)) ARCH=x64 MOD=module_x64 BUILD=build_x64
	$(MAKE) -f $(lastword $(MAKEFILE_LIST)) ARCH=xtensawin MOD=module_xtensawin BUILD=build_xtensawin

clean:
	rm -rf build_x64 build_xtensawin gen *.mpy

else
include $(MPY_DIR)/py/dynruntime.mk

# Everything compiles from the generated tree, so it has to exist first.
gen/%.c: prepare
	@:
$(CONFIG_H) $(SRC_O): | prepare
endif
