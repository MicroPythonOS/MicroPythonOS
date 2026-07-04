#!/bin/bash

mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir")
codebasedir=$(readlink -f "$mydir"/..) # build process needs absolute paths

disable_native_viper() {
	echo "Disabling @micropython.native/@micropython.viper for $target build..."
	# Walk through symlinked directories (e.g. lib/nostr -> micropython-nostr/nostr)
	# but skip files that are themselves symlinks: BSD/macOS sed -i.bak refuses
	# to edit symlink paths even when the target is a regular file.
	find -L "$1" -name '*.py' -type f -print0 | while IFS= read -r -d '' f; do
		if [ -L "$f" ]; then
			continue
		fi
		sed -i.bak -E 's/^([[:space:]]*)(@micropython\.(native|viper)[[:space:]]*)$/\1#\2/' "$f"
	done
	# Use rm instead of -delete because find still follows symlinks here.
	find -L "$1" -name '*.py.bak' -type f -exec rm -f {} +
}

reset_web_port_changes() {
	# The web build applies web-port-only patches and copies web-only files into
	# the lvgl_micropython submodule.  These changes must not leak into esp32,
	# unix, or macOS builds, so restore the affected tracked files and remove
	# the web-only untracked files before building anything else.
	echo "Resetting web-port-only changes from lvgl_micropython submodule..."
	local lvgl_dir="$codebasedir"/lvgl_micropython
	local mp_dir="$lvgl_dir"/lib/micropython

	# Remove web-port-only untracked files/directories.
	rm -f "$lvgl_dir"/builder/web.py
	rm -rf "$lvgl_dir"/ext_mod/_webnet
	rm -rf "$lvgl_dir"/ext_mod/_webterm

	# Remove stale patch reject files left by earlier failed/forward patch runs.
	rm -f "$lvgl_dir"/make.py.rej
	rm -f "$lvgl_dir"/ext_mod/lcd_bus/micropython.mk.rej
	rm -f "$lvgl_dir"/ext_mod/lcd_bus/sdl_bus/sdl_bus.h.rej

	# Restore tracked files touched by the web-port patches.
	if [ -e "$lvgl_dir"/.git ]; then
		git -C "$lvgl_dir" checkout -- \
			make.py \
			ext_mod/lcd_bus/micropython.mk \
			ext_mod/lcd_bus/sdl_bus/sdl_bus.h \
			2>/dev/null || true
	fi
	if [ -e "$mp_dir"/.git ]; then
		git -C "$mp_dir" checkout -- \
			ports/unix/gccollect.c \
			ports/unix/unix_mphal.c \
			2>/dev/null || true
	fi
}

target="$1"
buildtype="$2"

if [ -z "$target" ]; then
    echo "Usage: $0 target"
    echo "Usage: $0 <esp32 or esp32-small or unix or macOS or web>"
    echo "Example: $0 unix"
    echo "Example: $0 macOS"
    echo "Example: $0 web"
    echo "Example: $0 esp32"
    echo "Example: $0 esp32-small"
    echo "Example: $0 esp32s3"
    echo "Example: $0 unphone"
    echo "Example: $0 lilygo_t4"
    echo "Example: $0 clean"
	exit 1
fi


if [ "$target" == "clean" ]; then
	rm -rf "$mydir"/../lvgl_micropython/lib/micropython/ports/unix/build-standard/
	rm -rf "$mydir"/../lvgl_micropython/lib/micropython/ports/esp32/build-ESP32_GENERIC/
	rm -rf "$mydir"/../lvgl_micropython/lib/micropython/ports/esp32/build-ESP32_GENERIC_S3-SPIRAM_OCT/
	exit 0
fi

# This assumes all the git submodules have been checked out recursively

echo "Fetch tags for lib/SDL, otherwise lvgl_micropython's make.py script can't checkout a specific tag..."
pushd "$codebasedir"/lvgl_micropython/lib/SDL
git fetch --unshallow origin 2>/dev/null # will give error if already done
# Or fetch all refs without unshallowing (keeps it shallow but adds refs)
git fetch origin 'refs/tags/*:refs/tags/*'
popd

idfile="$codebasedir"/lvgl_micropython/lib/micropython/ports/esp32/main/idf_component.yml
echo "Patching $idfile"...

echo "Check need to add esp32-camera to $idfile"
if ! grep esp32-camera "$idfile"; then
	echo "Adding esp32-camera to $idfile"
	echo "  mpos/esp32-camera:
    git: https://github.com/MicroPythonOS/esp32-camera" >> "$idfile"
else
	echo "No need to add esp32-camera to $idfile"
fi

echo "Check need to add adc_mic to $idfile"
if ! grep adc_mic "$idfile"; then
	echo "Adding adc_mic to $idfile"
        echo '  espressif/adc_mic: "*"' >> "$idfile"
else
	echo "No need to add adc_mic to $idfile"
fi

echo "Resulting $idfile file:"
cat "$idfile"

echo "Check need to add lvgl_micropython manifest to micropython-camera-API's manifest..."
camani="$codebasedir"/micropython-camera-API/src/manifest.py
rellvglmani=lvgl_micropython/build/manifest.py
abslvglmani="$codebasedir"/"$rellvglmani"
if ! grep "$rellvglmani" "$camani"; then
	echo "Adding include(\"$abslvglmani\") to $camani"
	echo >> "$camani" # needs newline because file doesn't have newline at the end
	echo "include(\"$abslvglmani\") # workaround to prevent micropython-camera-API from overriding the lvgl_micropython manifest..." >> "$camani"
	echo "Resulting file:"
	cat "$camani"
else
	echo "No need to add include(\"$abslvglmani\") to $camani"
fi

echo "Check need to add asyncio..."
manifile="$codebasedir"/lvgl_micropython/lib/micropython/ports/unix/variants/manifest.py
if ! grep asyncio "$manifile"; then
	echo "Adding asyncio to $manifile"
	echo 'include("$(MPY_DIR)/extmod/asyncio") # needed to have asyncio, which is used by aiohttp, which has used by websockets' >> "$manifile"
	echo "Resulting file:"
	cat "$manifile"
else
	echo "No need to add asyncio to $manifile"
fi

echo "Installing customized font sources to lvgl_micropython/lib/lvgl"
if ! cp "$codebasedir"/lvgl_micropython/lib_lvgl_src_font/* "$codebasedir"/lvgl_micropython/lib/lvgl/src/font/ ; then
	echo "Could not install $codebasedir/lvgl_micropython/lib_lvgl_src_fonts/ so you probably need to update or re-clone the lvgl_micropython folder. See https://docs.micropythonos.com/os-development/"
	exit 1
fi
# Remove deprecated simsun CJK fonts from the LVGL source (replaced by source-han-sans-sc).
# They contain #warning directives that fail with -Werror on the unix port.
rm -f "$codebasedir"/lvgl_micropython/lib/lvgl/src/font/lv_font_simsun_14_cjk.c
rm -f "$codebasedir"/lvgl_micropython/lib/lvgl/src/font/lv_font_simsun_16_cjk.c

# unix and macOS builds need these symlinks because make.py doesn't handle USER_C_MODULE arguments for them:
echo "Symlinking secp256k1-embedded-ecdh for unix and macOS builds..."
ln -sf ../../secp256k1-embedded-ecdh "$codebasedir"/lvgl_micropython/ext_mod/secp256k1-embedded-ecdh
echo "Symlinking c_mpos for unix and macOS builds..."
ln -sf ../../c_mpos "$codebasedir"/lvgl_micropython/ext_mod/c_mpos

echo "Applying lvgl_micropython esp32 uart repl enable/disable at runtime patch..."
pushd "$codebasedir"/lvgl_micropython/lib/micropython
patch -p1 --forward < ../../esp32_uart_repl_runtime.patch || true
popd

echo "Applying lvgl_micropython/lib/lvgl bmp scaling fix patch..."
pushd "$codebasedir"/lvgl_micropython/lib/lvgl
patch -p1 --forward < ../../lib_lvgl_lv_bmp.c.patch || true
popd

echo "Applying lvgl_micropython/lib/lvgl/src/libs/tjpgd scaling fix patch..."
pushd "$codebasedir"/lvgl_micropython/lib/lvgl
patch -p1 --forward < ../../lib_lvgl_src_libs_tjpgd_fix_scaling.patch || true
popd

# Fast emoji rendering: bake a codepoint range filter into lv_imgfont so
# non-emoji glyphs bail out in C without invoking the MicroPython path_cb.
# Pre-existence check so MPOS still builds against older pinned
# lvgl_micropython SHAs that don't ship this patch yet (FontManager.py
# degrades gracefully via try/except AttributeError when the setter is
# absent — see internal_filesystem/lib/mpos/ui/font_manager.py).
imgfont_patch="$codebasedir"/lvgl_micropython/imgfont_set_range.patch
if [ -f "$imgfont_patch" ]; then
	echo "Applying lvgl_micropython imgfont_set_range patch..."
	pushd "$codebasedir"/lvgl_micropython/lib/lvgl
	patch -p1 --forward < "$imgfont_patch" || true
	popd
fi

echo "Minifying and inlining HTML..."
pushd "$codebasedir"/webrepl/
python3 inline_minify_webrepl.py
result=$?
if [ $? -ne 0 ]; then
	echo "ERROR: webrepl/inline_minify_webrepl.py failed with exit code $result, webrepl won't work"
else
	mv webrepl_inlined_minified.html.gz ../internal_filesystem/builtin/html/
fi
popd

if [ "$target" == "unix" -o "$target" == "macOS" -o "$target" == "web" ]; then
	# Native/viper decorators generate Mach-O sections that break frozen bytecode
	# on macOS and are unsupported on some desktop architectures (e.g. arm64),
	# so disable them before freezing. In CI the unix/macOS build is run after
	# the esp32/esp32s3 builds, so those still get the optimized decorators.
	#
	# Native/viper decorators are unsupported by the WASM/native emitter used for
	# the web port, so disable them before freezing.
	disable_native_viper "$codebasedir/internal_filesystem"
fi

echo "Refreshing freezefs..."
if [ "$target" == "esp32" -o "$target" == "esp32s3" -o "$target" == "unphone" -o "$target" == "esp32-small" -o "$target" == "lilygo_t4" ]; then
	builtin_march="xtensawin"
else
	builtin_march="host"
fi
"$codebasedir"/scripts/freezefs_mount_builtin.sh -march "$builtin_march"

# If this is not a web build, make sure no web-port-only modifications are
# still present in the lvgl_micropython submodule from a previous web build.
if [ "$target" != "web" ]; then
	reset_web_port_changes
fi

if [ "$target" == "esp32" -o "$target" == "esp32s3" -o "$target" == "unphone" -o "$target" == "esp32-small" -o "$target" == "lilygo_t4" ]; then
	# Cleanup compiled .py files, otherwise if one from lib/ gets delected, the old .mpy might be used
	rm -r lvgl_micropython/lib/micropython/ports/esp32/build-ESP32_GENERIC-SPIRAM/frozen_mpy 2>/dev/null
	rm -r lvgl_micropython/lib/micropython/ports/esp32/build-ESP32_GENERIC_S3-SPIRAM_OCT/frozen_mpy 2>/dev/null

	echo "Applying lvgl_micropython esp32 inisetup warning patch..."
	pushd "$codebasedir"/lvgl_micropython/lib/micropython
	patch -p1 --forward < ../../esp32_inisetup_warn_and_format.patch || true
	echo "Applying lvgl_micropython esp32 inisetup readsize/progsize patch..."
	patch -p1 --forward < ../../esp32_inisetup_readsize_progsize.patch || true
	popd

	partition_size="4194304"
	flash_size="16"
	otasupport="--ota"
	extra_configs=""
	if [ "$target" == "esp32" ]; then
		BOARD=ESP32_GENERIC
		BOARD_VARIANT=SPIRAM
	elif [ "$target" == "esp32-small" ]; then
        # No PSRAM, so do not set SPIRAM-specific options
		BOARD=ESP32_GENERIC
		BOARD_VARIANT=
		partition_size="3800000"
		flash_size="4"
		otasupport="" # too small for 2 OTA partitions + internal storage
	elif [ "$target" == "lilygo_t4" ]; then
		BOARD=ESP32_GENERIC
		BOARD_VARIANT=SPIRAM
		partition_size="3800000"
		flash_size="4"
		otasupport="" # too small for 2 OTA partitions + internal storage
	else # esp32s3 or unphone
        if [ "$target" == "unphone" ]; then
            flash_size="8"
            otasupport="" # too small for 2 OTA partitions + internal storage
        fi
        BOARD=ESP32_GENERIC_S3
        BOARD_VARIANT=SPIRAM_OCT
        # These options disable hardware AES, SHA and MPI because they give warnings in QEMU: [AES] Error reading from GDMA buffer
        # There's a 25% https download speed penalty for this, but that's usually not the bottleneck.
        extra_configs="CONFIG_MBEDTLS_HARDWARE_AES=n CONFIG_MBEDTLS_HARDWARE_SHA=n CONFIG_MBEDTLS_HARDWARE_MPI=n"
        # --py-freertos: add MicroPython FreeRTOS module to expose internals
        #extra_configs="$extra_configs --py-freertos"
        # Enable UART based REPL, in addition to the USB-CDC or JTAG REPL. Can be disabled with esp.uart_repl(False)
        extra_configs="$extra_configs --enable-uart-repl=y"
	fi

	if [ "$BOARD_VARIANT" == "SPIRAM" -o "$BOARD_VARIANT" == "SPIRAM_OCT" ]; then
		# Camera only works on boards configured with spiram, otherwise the build breaks
		extra_configs="$extra_configs USER_C_MODULE=$codebasedir/micropython-camera-API/src/micropython.cmake"
	fi

	manifest=$(readlink -f "$codebasedir"/manifests/manifest.py)
	frozenmanifest="FROZEN_MANIFEST=$manifest" # Comment this out if you want to make a build without any frozen files, just an empty MicroPython + whatever files you have on the internal storage
	echo "Note that you can also prevent the builtin filesystem from being mounted by umounting it and creating a builtin/ folder."
	pushd "$codebasedir"/lvgl_micropython/
	rm -rf lib/micropython/ports/esp32/build-$BOARD-$BOARD_VARIANT

	# For more info on the options, see https://github.com/lvgl-micropython/lvgl_micropython
	# --optimize-size: optimize for size
	# --ota: support Over-The-Air updates
	# --partition size: both OTA partitions are 4MB
	# --flash-size: total flash size is 16MB
	# --debug: enable debugging from ESP-IDF but makes copying files to it very slow so that's not added
	# --dual-core-threads: disabled GIL, run code on both CPUs
	# --task-stack-size={stack size in bytes}
	# CONFIG_* sets ESP-IDF options
	# listing processes on the esp32 still doesn't work because no esp32.vtask_list_threads() or something
	# CONFIG_FREERTOS_USE_TRACE_FACILITY=y
	# CONFIG_FREERTOS_VTASKLIST_INCLUDE_COREID=y
	# CONFIG_FREERTOS_GENERATE_RUN_TIME_STATS=y
	# CONFIG_ADC_MIC_TASK_CORE=1 because with the default (-1) it hangs the CPU
	# CONFIG_SPIRAM_XIP_FROM_PSRAM: load entire firmware into RAM to reduce SD vs PSRAM contention (recommended at https://github.com/MicroPythonOS/MicroPythonOS/issues/17)
	set -x
	python3 make.py $otasupport --optimize-size --partition-size=$partition_size --flash-size=$flash_size esp32 BOARD=$BOARD BOARD_VARIANT=$BOARD_VARIANT \
		USER_C_MODULE="$codebasedir"/secp256k1-embedded-ecdh/micropython.cmake \
		USER_C_MODULE="$codebasedir"/c_mpos/micropython.cmake \
		CONFIG_ADC_MIC_TASK_CORE=1 \
		$extra_configs \
		"$frozenmanifest"
    set +x
	popd
elif [ "$target" == "unix" -o "$target" == "macOS" ]; then
	# Full cleanup: old .o from upstream MicroPython builds would cause link errors
	rm -rf ./lvgl_micropython/lib/micropython/ports/unix/build-standard/ 2>/dev/null

	echo "Applying unix auto-import main patch..."
	pushd "$codebasedir"/lvgl_micropython/lib/micropython
	patch -p1 --forward < ../../unix_autoimport_main.patch || true
	popd

	manifest=$(readlink -f "$codebasedir"/manifests/manifest.py)
	frozenmanifest="FROZEN_MANIFEST=$manifest"

	# Ensure WebREPL and dupterm are enabled for unix/macOS builds.
	mpconfig_unix="$codebasedir"/lvgl_micropython/lib/micropython/ports/unix/mpconfigport.h
	ensure_mpconfig_define() {
		local name="$1"
		if ! grep -q "$name" "$mpconfig_unix"; then
			echo "Enabling $name in $mpconfig_unix"
			python3 "$mydir"/ensure_mpconfig_define.py "$mpconfig_unix" "$name"
		else
			echo "$name already configured in $mpconfig_unix"
		fi
	}
	ensure_mpconfig_define MICROPY_PY_WEBREPL
	ensure_mpconfig_define MICROPY_PY_OS_DUPTERM

	# sdl2 has been removed from Homebrew in favor of sdl2-compat on some runners,
	# but the lvgl_micropython macOS builder still queries the sdl2 formula. Point
	# it at sdl2-compat so the brew info / LDFLAGS / CFLAGS discovery works.
	if [ "$target" == "macOS" ]; then
		macos_builder="$codebasedir"/lvgl_micropython/builder/macOS.py
		if [ -f "$macos_builder" ] && grep -q "brew_path, 'info', 'sdl2'" "$macos_builder" 2>/dev/null; then
			echo "Patching macOS builder for sdl2-compat..."
			sed -i.backup "s/brew_path, 'info', 'sdl2'/brew_path, 'info', 'sdl2-compat'/g" "$macos_builder"
		fi
	fi

	# Suppress warnings that newer Clang (17+) treats as errors on macOS.
	# GCC on Linux doesn't have -Wgnu-folding-constant so this must be skipped there.
	# -Wno-unknown-warning-option prevents Clang from erroring on GCC-only flag names
	# (e.g. -Wno-error=unterminated-string-initialization is GCC-only; Clang 21 rejects
	# it with -Werror,-Wunknown-warning-option which kills the build).
	unix_makefile="$codebasedir"/lvgl_micropython/lib/micropython/ports/unix/Makefile

	# Ensure the socket module is compiled into the unix binary. The web-port
	# patch removes modsocket.c from SRC_C; if those changes linger (or a clean
	# checkout ships the socket-less Makefile), restore it here.
	if grep -q '^[[:space:]]*modsocket\.c[[:space:]]*\\$' "$unix_makefile"; then
		echo "modsocket.c already present in $unix_makefile"
	else
		echo "Restoring modsocket.c in $unix_makefile"
		sed -i '/^[[:space:]]*fatfs_port\.c[[:space:]]*\\$/a\'$'\t''modsocket.c \\' "$unix_makefile"
	fi

	if [ "$(uname -s)" = "Darwin" ]; then
		echo "Temporarily suppressing Clang warnings for macOS build..."
		sed -i.backup 's/^CWARN = -Wall -Werror$/CWARN = -Wall -Werror -Wno-unknown-warning-option -Wno-error=gnu-folding-constant -Wno-error=missing-field-initializers -Wno-error=unterminated-string-initialization/' "$unix_makefile"
	fi

	# If it's still running, kill it, otherwise "text file busy"
	pkill -9 -f /lvgl_micropy_unix
	# LV_CFLAGS are passed to USER_C_MODULES (compiler flags only, no linker flags)
	# STRIP= makes it so that debug symbols are kept
	pushd "$codebasedir"/lvgl_micropython/
	# USER_C_MODULE doesn't seem to work properly so there are symlinks in lvgl_micropython/extmod/
	# To avoid X11/Wayland being loaded dynamically at runtime, you can use: -DSDL_LOADSO=OFF
	# but then those need to be provided at compile time, or excluded by using: -DSDL_WAYLAND=OFF -DSDL_X11=OFF
	# -march=host tells mpy-cross to generate native code for the host arch.
	# Only supported on architectures where mpy-cross has a native emitter:
	# x86, x64, armv6 (no Thumb2), riscv64. On aarch64/other, skip it — the
	# viper/native decorators will still work (bytecode fallback).
	mpy_cross_arch=""
	case "$(uname -m)" in
		x86_64|i686|i386|armv6l|riscv64) mpy_cross_arch="host" ;;
	esac
	[ -n "$mpy_cross_arch" ] && mpy_cross_flags="-O3 -march=$mpy_cross_arch" || mpy_cross_flags="-O3"
	python3 make.py "$target" \
		LV_CFLAGS="-g -O0 -ggdb" \
		STRIP= \
		DISPLAY=sdl_display \
		INDEV=sdl_pointer \
		SDL_FLAGS="-DSDL_OPENGL=OFF -DSDL_OPENGLES=OFF -DSDL_VULKAN=OFF -DSDL_KMSDRM=OFF -DSDL_IBUS=OFF -DSDL_DBUS=OFF -DSDL_ALSA=OFF -DSDL_PULSEAUDIO=OFF -DSDL_SNDIO=OFF -DSDL_LIBSAMPLERATE=OFF" \
		MPY_CROSS_FLAGS="\"$mpy_cross_flags\"" \
		"$frozenmanifest"

	popd

	# Restore original Makefile CWARN (only if we patched it on macOS)
	if [ -f "$unix_makefile".backup ]; then
		echo "Restoring unix Makefile CWARN..."
		mv "$unix_makefile".backup "$unix_makefile"
	fi
elif [ "$target" == "web" ]; then
	# WebAssembly / Emscripten build.
	# Reuses the unix port (LVGL + SDL display/indev drivers, frozen manifest,
	# ext_mod C modules) but compiles with emcc and links Emscripten's SDL2
	# port, producing web/micropython.{html,js,wasm,data}.

	# Make sure the Emscripten toolchain is available.
	if ! command -v emcc >/dev/null 2>&1; then
		for envsh in "$codebasedir"/../emsdk/emsdk_env.sh "$codebasedir"/../../emsdk/emsdk_env.sh; do
			if [ -f "$envsh" ]; then
				echo "Sourcing Emscripten env from $envsh"
				# shellcheck disable=SC1090
				source "$envsh"
				break
			fi
		done
	fi
	if ! command -v emcc >/dev/null 2>&1; then
		echo "ERROR: emcc not found. Activate the Emscripten SDK first:"
		echo "  source <path-to>/emsdk/emsdk_env.sh"
		exit 1
	fi
	echo "Using $(emcc --version | head -1)"

	# Full cleanup: stale native .o would not relink under emcc.
	rm -rf ./lvgl_micropython/lib/micropython/ports/unix/build-standard/ 2>/dev/null

	echo "Applying unix auto-import main patch..."
	pushd "$codebasedir"/lvgl_micropython/lib/micropython
	patch -p1 --forward < ../../unix_autoimport_main.patch || true
	popd

	# Apply the web-port modifications to the lvgl_micropython submodule. These
	# live in THIS (MicroPythonOS) repo under scripts/web_port/ so the entire web
	# port is reproducible from a clean submodule checkout without hand-editing
	# submodule sources. `patch --forward` makes re-application a no-op, and the
	# web.py copy is idempotent, so this is safe to run on every build.
	echo "Applying web-port changes to lvgl_micropython submodule..."
	web_port_dir="$mydir"/web_port
	# 1) Emscripten/WebAssembly build backend consumed by lvgl_micropython's make.py.
	cp "$web_port_dir"/web.py "$codebasedir"/lvgl_micropython/builder/web.py
	# 1b) Register the 'web' target in make.py (argparse choices + builder dispatch).
	patch -p1 --forward -d "$codebasedir"/lvgl_micropython < "$web_port_dir"/make.py.patch || true
	# 1c) Gate lcd_bus SDL flags behind MPOS_WEB=1 so the web build uses Emscripten's
	#     bundled SDL2 (-sUSE_SDL=2) instead of linking a natively built SDL2.
	patch -p1 --forward -d "$codebasedir"/lvgl_micropython < "$web_port_dir"/lcd_bus_micropython.mk.patch || true
	# 2) SDL bus struct-layout fix (32-bit/wasm indirect-call type safety).
	patch -p1 --forward -d "$codebasedir"/lvgl_micropython < "$web_port_dir"/sdl_bus.h.patch || true
	# 3) Conservative-GC stack/register scan for wasm (fixes "memory access out of bounds").
	patch -p1 --forward -d "$codebasedir"/lvgl_micropython/lib/micropython < "$web_port_dir"/gccollect.c.patch || true
	# 3b) Mirror unix stdout to the _webterm bridge (lets an external host see all
	#     REPL/stdout output). Guarded by __EMSCRIPTEN__ so device builds are unaffected.
	patch -p1 --forward -d "$codebasedir"/lvgl_micropython/lib/micropython < "$web_port_dir"/unix_mphal.c.patch || true
	# 4) _webnet native user C module (browser fetch() bridge for HTTP networking).
	#    Auto-discovered via USER_C_MODULES; only built when MPOS_WEB=1.
	mkdir -p "$codebasedir"/lvgl_micropython/ext_mod/_webnet
	cp "$web_port_dir"/ext_mod/_webnet/webnet.c "$codebasedir"/lvgl_micropython/ext_mod/_webnet/webnet.c
	cp "$web_port_dir"/ext_mod/_webnet/micropython.mk "$codebasedir"/lvgl_micropython/ext_mod/_webnet/micropython.mk
	# 5) _webterm native user C module (browser <-> MicroPython stdio byte bridge).
	#    Lets an external host (e.g. ViperIDE) drive the asyncio REPL like a serial
	#    device. Auto-discovered via USER_C_MODULES; only built when MPOS_WEB=1.
	mkdir -p "$codebasedir"/lvgl_micropython/ext_mod/_webterm
	cp "$web_port_dir"/ext_mod/_webterm/webterm.c "$codebasedir"/lvgl_micropython/ext_mod/_webterm/webterm.c
	cp "$web_port_dir"/ext_mod/_webterm/micropython.mk "$codebasedir"/lvgl_micropython/ext_mod/_webterm/micropython.mk

	manifest=$(readlink -f "$codebasedir"/manifests/manifest.py)
	frozenmanifest="FROZEN_MANIFEST=$manifest"

	mkdir -p "$codebasedir"/web
	shell_file="$codebasedir"/web/shell.html
	staged_fs="$codebasedir"/web/.preload_internal_filesystem
	rm -rf "$staged_fs"
	mkdir -p "$staged_fs"

	# Browser packaging cannot include dangling symlinks. The development tree may
	# contain app symlinks that point to optional sibling repositories not present
	# in this workspace, so stage a copy and prune broken links first.
	if command -v rsync >/dev/null 2>&1; then
		rsync -a "$codebasedir"/internal_filesystem/ "$staged_fs"/
	else
		cp -a "$codebasedir"/internal_filesystem/. "$staged_fs"/
	fi

	broken_links=$(find "$staged_fs" -type l ! -exec test -e {} \; -print)
	if [ -n "$broken_links" ]; then
		echo "Pruning dangling symlinks from staged internal_filesystem:"
		echo "$broken_links"
		find "$staged_fs" -type l ! -exec test -e {} \; -delete
	fi

	# Persistence split for the browser build (IDBFS / IndexedDB):
	#   - /data and /apps are mounted from IndexedDB at boot (see web/shell.html)
	#     so app preferences and user-installed apps survive page reloads.
	#   - Those two paths therefore must NOT be baked into the read-only preload
	#     package, or the preload would shadow/conflict with the IDBFS mounts.
	#   - The bundled demo apps still need to ship with the image, so they are
	#     packaged separately at /.bundled_apps and copied into the persistent
	#     /apps store once, on first boot (seedBundledApps() in shell.html).
	staged_bundled_apps="$codebasedir"/web/.preload_bundled_apps
	rm -rf "$staged_bundled_apps"
	if [ -d "$staged_fs"/apps ]; then
		mv "$staged_fs"/apps "$staged_bundled_apps"
	else
		mkdir -p "$staged_bundled_apps"
	fi
	# /data is recreated empty by IDBFS at boot; drop the preloaded copy so it
	# does not collide with the persistent mount.
	rm -rf "$staged_fs"/data

	# The browser build disables native threading (MICROPY_PY_THREAD=0), so the
	# C builtin `_thread` module is absent. MicroPythonOS imports `_thread`
	# widely (TaskManager, threading.py, audio, wifi). Provide a web-only
	# cooperative shim on the staged filesystem so `import _thread` resolves
	# from lib/ (it is not present on real device builds). The shim runs thread
	# bodies as asyncio tasks on the event loop TaskManager already drives, and
	# treats locks as no-ops (a single-threaded cooperative scheduler cannot
	# have true lock contention).
	echo "Injecting web-only cooperative _thread shim into staged lib/..."
	cp "$web_port_dir"/staged_lib/_thread.py "$staged_fs"/lib/_thread.py

	# The browser build also disables native networking (MICROPY_PY_SOCKET=0),
	# so the C builtin `socket` module is absent. MicroPythonOS imports it for
	# the WebREPL/web server, which cannot use raw TCP sockets inside the
	# browser sandbox anyway. Provide a web-only stub so `import socket`
	# succeeds; any actual socket use raises a clear, catchable error instead
	# of crashing the import chain at boot.
	echo "Injecting web-only socket stub into staged lib/..."
	cp "$web_port_dir"/staged_lib/socket.py "$staged_fs"/lib/socket.py

	# Web-only REPL bridge. MicroPythonOS runs an asyncio REPL (aiorepl) that
	# reads sys.stdin, but the browser has no readable stdin, so the stock
	# aiorepl fails with EIO at boot. This staged override replaces aiorepl with
	# a drop-in that reads input from the `_webterm` JS bridge instead, so an
	# external host (e.g. ViperIDE/Fri3d-IDE) can drive the REPL like a serial
	# device. Output still goes through sys.stdout, which the web build mirrors
	# to the host via _webterm (see unix_mphal.c.patch + ext_mod/_webterm).
	# AIOReplService (device source, unchanged) imports aiorepl and calls
	# aiorepl.task(); on web that resolves to this override from lib/.
	echo "Injecting web-only aiorepl (REPL-over-_webterm) shim into staged lib/..."
	cp "$web_port_dir"/staged_lib/aiorepl.py "$staged_fs"/lib/aiorepl.py

	# WebREPL/WebSocket rely on the native `_webrepl` and `websocket` C modules,
	# which are not built for web and which depend on raw sockets (unavailable
	# in the browser sandbox). The webserver code only instantiates these inside
	# connection handlers that never fire here (sockets are stubbed), so plain
	# import-satisfying stubs are sufficient to let the boot import chain
	# complete.
	echo "Injecting web-only _webrepl and websocket stubs into staged lib/..."
	cp "$web_port_dir"/staged_lib/_webrepl.py "$staged_fs"/lib/_webrepl.py
	cp "$web_port_dir"/staged_lib/websocket.py "$staged_fs"/lib/websocket.py

	# Web-only `aiohttp` shim backed by the _webnet native fetch() bridge.
	# Overwrites only __init__.py in the staged aiohttp package so the real
	# socket-based implementation (which cannot work in the browser) is shadowed
	# while leaving the device tree untouched. Provides the surface MPOS uses:
	# ClientSession + get/post/put/delete returning an async context manager with
	# .status, .headers (dict) and a streaming .content.read(n). WebSocket
	# (ws_connect) is not implemented here yet and raises a clear error.
	echo "Injecting web-only aiohttp (fetch) shim into staged lib/aiohttp/..."
	mkdir -p "$staged_fs"/lib/aiohttp
	cp "$web_port_dir"/staged_lib/aiohttp/__init__.py "$staged_fs"/lib/aiohttp/__init__.py

	# Web-only replacement for the frozen `task_handler` driver. The stock
	# driver in lvgl_micropython drives LVGL from a `machine.Timer` interrupt,
	# but `machine_timer.c` is removed from the web build (no native timers).
	# This shim keeps the exact same public API but drives LVGL from an asyncio
	# task instead, integrating with the asyncio loop that TaskManager.start()
	# runs via asyncio.run(). main.py does `sys.path.insert(0, "lib")`, so this
	# file (in /lib) shadows the frozen module.
	cp "$web_port_dir"/staged_lib/task_handler.py "$staged_fs"/lib/task_handler.py

	# Web-only `machine.Timer` replacement. The native timer (machine_timer.c)
	# is removed from the web build, but MicroPythonOS code (connectivity
	# manager, several apps via `from machine import Timer`) expects the
	# standard periodic/one-shot Timer API. This asyncio-backed implementation
	# provides the same surface and is injected into the native `machine`
	# module at boot (see the staged main.py patch below).
	cp "$web_port_dir"/staged_lib/_web_machine_timer.py "$staged_fs"/lib/_web_machine_timer.py

	# Inject machine.Timer into the native `machine` module at the very start of
	# boot, before any MicroPythonOS code runs. Patch the STAGED copy of main.py
	# only (never the source device file). Insert right after the
	# `sys.path.insert(0, "lib")` line so lib/ is importable.
	python3 "$web_port_dir"/inject_web_machine_timer.py "$staged_fs"/main.py

	# Emscripten link-time packaging: bundle internal_filesystem read-only into
	# the virtual FS at "/" (matching the on-device layout, where the internal
	# filesystem is the root). MicroPythonOS' frozen main.py does
	# `sys.path.insert(0, "lib")` and apps use root-relative paths like /apps and
	# /builtin, so the staged tree must live at the root for those to resolve.
	# The bundled demo apps are packaged separately at /.bundled_apps because
	# /apps is a persistent IDBFS mount (see web/shell.html); they are seeded
	# into /apps on first boot.
	export MPOS_WEB_LINK_FLAGS="--preload-file $staged_fs@/ --preload-file $staged_bundled_apps@/.bundled_apps --shell-file $shell_file"

	pushd "$codebasedir"/lvgl_micropython/
	set -x
	python3 make.py web \
		LV_CFLAGS="-O2" \
		STRIP= \
		DISPLAY=sdl_display \
		INDEV=sdl_pointer \
		MPY_CROSS_FLAGS="-O3" \
		"$frozenmanifest"
	build_status=$?
	set +x
	popd

	if [ $build_status -ne 0 ]; then
		echo "ERROR: web build failed (make.py web exit code $build_status)."
		exit $build_status
	fi

	# Collect canonical Emscripten artifacts into web/.
	for f in micropython.html micropython.js micropython.wasm micropython.data micropython.wasm.map; do
		if [ -f "$codebasedir/lvgl_micropython/build/$f" ]; then
			cp "$codebasedir/lvgl_micropython/build/$f" "$codebasedir/web/$f"
		fi
	done

	# Remove stale renamed wasm/js/data aliases from older builds.
	rm -f "$codebasedir/web/mpos.js" "$codebasedir/web/mpos.wasm" "$codebasedir/web/mpos.data" "$codebasedir/web/mpos.wasm.map"

	# Convenience entry points (served as the entry point and legacy URL).
	if [ -f "$codebasedir/web/micropython.html" ]; then
		cp "$codebasedir/web/micropython.html" "$codebasedir/web/index.html"
		cp "$codebasedir/web/micropython.html" "$codebasedir/web/mpos.html"
		echo "Web build complete. Artifacts in $codebasedir/web/"
		echo "Serve with: python3 -m http.server 8080 -d $codebasedir/web"
	else
		echo "Web build did not produce micropython.html — check the build log above."
	fi
else
	echo "invalid target $target"
fi

