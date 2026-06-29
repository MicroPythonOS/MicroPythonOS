#!/bin/bash

mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir")
codebasedir=$(readlink -f "$mydir"/..) # build process needs absolute paths

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
result=$0
if [ $? -ne 0 ]; then
	echo "ERROR: webrepl/inline_minify_webrepl.py failed with exit code $result, webrepl won't work"
else
	mv webrepl_inlined_minified.html.gz ../internal_filesystem/builtin/html/
fi
popd

echo "Refreshing freezefs..."
"$codebasedir"/scripts/freezefs_mount_builtin.sh

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
		partition_size="3700000"
		flash_size="4"
		otasupport="" # too small for 2 OTA partitions + internal storage
	elif [ "$target" == "lilygo_t4" ]; then
		BOARD=ESP32_GENERIC
		BOARD_VARIANT=SPIRAM
		partition_size="3700000"
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

	# Suppress warnings that newer Clang (17+) treats as errors on macOS.
	# GCC on Linux doesn't have -Wgnu-folding-constant so this must be skipped there.
	# -Wno-unknown-warning-option prevents Clang from erroring on GCC-only flag names
	# (e.g. -Wno-error=unterminated-string-initialization is GCC-only; Clang 21 rejects
	# it with -Werror,-Wunknown-warning-option which kills the build).
	unix_makefile="$codebasedir"/lvgl_micropython/lib/micropython/ports/unix/Makefile
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
	cat > "$staged_fs"/lib/_thread.py <<'PYEOF'
# Cooperative _thread shim for the single-threaded WebAssembly/Emscripten build.
#
# Real OS threads are unavailable in the browser without pthreads, so this
# emulates the subset of the CPython/MicroPython `_thread` API that
# MicroPythonOS relies on by scheduling work cooperatively on the asyncio event
# loop that TaskManager runs. Locks are no-ops because a single-threaded
# cooperative scheduler cannot have true contention.

_stack_size = 0


def stack_size(size=None):
    global _stack_size
    prev = _stack_size
    if size is not None:
        _stack_size = size
    return prev


def get_ident():
    return 1


def start_new_thread(function, args=(), kwargs=None):
    if kwargs is None:
        kwargs = {}

    try:
        import asyncio

        async def _runner():
            try:
                function(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                print("[_thread shim] thread function failed:", exc)

        asyncio.get_event_loop().create_task(_runner())
    except Exception:
        # No running event loop yet: run synchronously so behaviour stays defined.
        function(*args, **kwargs)

    return get_ident()


class LockType:
    def __init__(self):
        self._locked = False

    def acquire(self, waitflag=1, timeout=-1):
        self._locked = True
        return True

    def release(self):
        self._locked = False

    def locked(self):
        return self._locked

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


def allocate_lock():
    return LockType()
PYEOF

	# The browser build also disables native networking (MICROPY_PY_SOCKET=0),
	# so the C builtin `socket` module is absent. MicroPythonOS imports it for
	# the WebREPL/web server, which cannot use raw TCP sockets inside the
	# browser sandbox anyway. Provide a web-only stub so `import socket`
	# succeeds; any actual socket use raises a clear, catchable error instead
	# of crashing the import chain at boot.
	echo "Injecting web-only socket stub into staged lib/..."
	cat > "$staged_fs"/lib/socket.py <<'PYEOF'
# Minimal socket stub for the WebAssembly/Emscripten build.
#
# The browser sandbox has no access to raw TCP/UDP sockets, so MicroPythonOS'
# network server features (WebREPL, web server) are unavailable on web. This
# stub lets `import socket` succeed at boot; constructing or using a socket
# raises OSError so callers can detect and skip networking gracefully.

AF_INET = 2
AF_INET6 = 10
SOCK_STREAM = 1
SOCK_DGRAM = 2
SOL_SOCKET = 1
SO_REUSEADDR = 2
IPPROTO_TCP = 6
IPPROTO_UDP = 17


class error(OSError):
    pass


def getaddrinfo(host, port, *args, **kwargs):
    raise OSError("socket not available in the web build")


class socket:
    def __init__(self, *args, **kwargs):
        raise OSError("socket not available in the web build")
PYEOF

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
	cat > "$staged_fs"/lib/aiorepl.py <<'PYEOF'
# Web (Emscripten) REPL bridge for MicroPythonOS — drop-in aiorepl replacement.
#
# The browser has no readable stdin, so the upstream aiorepl (which reads
# sys.stdin via asyncio.StreamReader) fails with EIO. This version reads input
# from the `_webterm` native bridge (fed by the JS host) and yields to the
# asyncio loop between polls, so the LVGL/UI task handler keeps running while a
# host drives the REPL. Output uses sys.stdout, which the web build mirrors to
# the host (Module.__webterm.onOutput) via a C-level stdout hook.
#
# The raw REPL (Ctrl-A) and raw-paste (Ctrl-E A) protocol matches mpremote, so
# external tools that speak the standard MicroPython raw REPL work unchanged.

import micropython
from micropython import const
import sys
import asyncio
import _webterm

_webterm.init()

CHAR_CTRL_A = const(1)
CHAR_CTRL_B = const(2)
CHAR_CTRL_C = const(3)
CHAR_CTRL_D = const(4)
CHAR_CTRL_E = const(5)


class _WebStdin:
    # Async, non-blocking stdin backed by the _webterm input queue. read()
    # waits (yielding to asyncio) until at least one byte is available, then
    # returns up to n bytes as a str (one char per byte), matching how the
    # upstream StreamReader(sys.stdin) reads are consumed by this REPL.
    async def read(self, n=1):
        while _webterm.any() == 0:
            await asyncio.sleep_ms(10)
        out = ""
        while len(out) < n:
            c = _webterm.rx()
            if c < 0:
                break
            out += chr(c)
        return out


async def execute(code, g, s):
    if not code.strip():
        return
    try:
        if "await " in code:
            # Execute the snippet in an async context.
            code = "async def __code():\n    {}\n".format(
                code.replace("\n", "\n    ")
            )
            l = {}
            exec(code, g, l)
            return await l["__code"]()
        else:
            try:
                return eval(code, g)
            except SyntaxError:
                return exec(code, g)
    except Exception as err:
        sys.print_exception(err, sys.stdout)


async def raw_paste(s, window=512):
    sys.stdout.write("R\x01")  # supported
    sys.stdout.write(bytearray([window & 0xFF, window >> 8, 0x01]).decode())
    eof = False
    idx = 0
    buff = bytearray(window)
    file = b""
    while not eof:
        for idx in range(window):
            b = await s.read(1)
            c = ord(b)
            if c == CHAR_CTRL_C or c == CHAR_CTRL_D:
                sys.stdout.write(chr(CHAR_CTRL_D))
                if c == CHAR_CTRL_C:
                    raise KeyboardInterrupt
                file += buff[:idx]
                eof = True
                break
            buff[idx] = c
        if not eof:
            file += buff
            sys.stdout.write("\x01")  # window available
    return file


async def raw_repl(s, g):
    heading = "raw REPL; CTRL-B to exit\n"
    line = ""
    sys.stdout.write(heading)
    while True:
        line = ""
        sys.stdout.write(">")
        while True:
            b = await s.read(1)
            if not b:
                continue
            c = ord(b)
            if c == CHAR_CTRL_A:
                rline = line
                line = ""
                if len(rline) == 2 and ord(rline[0]) == CHAR_CTRL_E:
                    if rline[1] == "A":
                        line = await raw_paste(s)
                        break
                else:
                    # reset raw REPL
                    sys.stdout.write(heading)
                    sys.stdout.write(">")
                continue
            elif c == CHAR_CTRL_B:
                sys.stdout.write("\n")
                return 0
            elif c == CHAR_CTRL_C:
                line = ""
            elif c == CHAR_CTRL_D:
                sys.stdout.write("OK")
                break
            else:
                # any other raw 8-bit value
                line += b
        if isinstance(line, str) and len(line) == 0:
            sys.stdout.write("Ignored: soft reboot\n")
            sys.stdout.write(heading)
        try:
            result = exec(line, g)
            if result is not None:
                sys.stdout.write(repr(result))
            sys.stdout.write(chr(CHAR_CTRL_D))
        except KeyboardInterrupt:
            sys.stdout.write(chr(CHAR_CTRL_D))
        except Exception as ex:
            sys.stdout.write(chr(CHAR_CTRL_D))
            sys.print_exception(ex, sys.stdout)
        sys.stdout.write(chr(CHAR_CTRL_D))


# REPL task. Signature matches upstream aiorepl.task() so AIOReplService can
# call it unchanged: aiorepl.task(g={...}, prompt=">>> ").
async def task(g=None, prompt=">>> "):
    print("Starting web asyncio REPL (input via _webterm)...")
    if g is None:
        g = __import__("__main__").__dict__
    micropython.kbd_intr(-1)
    s = _WebStdin()
    while True:
        sys.stdout.write(prompt)
        cmd = ""
        paste = False
        while True:
            b = await s.read(1)
            if not b:
                continue
            c = ord(b)
            if c == CHAR_CTRL_A:
                await raw_repl(s, g)
                break
            elif c == CHAR_CTRL_B:
                continue
            elif c == CHAR_CTRL_C:
                sys.stdout.write("\n")
                break
            elif c == CHAR_CTRL_D:
                if paste:
                    result = await execute(cmd, g, s)
                    if result is not None:
                        sys.stdout.write(repr(result))
                        sys.stdout.write("\n")
                    break
                # In the browser there is no process to exit; just refresh.
                sys.stdout.write("\n")
                break
            elif c == CHAR_CTRL_E:
                sys.stdout.write("paste mode; Ctrl-C to cancel, Ctrl-D to finish\n===\n")
                paste = True
            elif c == 0x0A or c == 0x0D:
                if paste:
                    sys.stdout.write("\n")
                    cmd += "\n"
                    continue
                sys.stdout.write("\n")
                result = await execute(cmd, g, s)
                if result is not None:
                    sys.stdout.write(repr(result))
                    sys.stdout.write("\n")
                break
            elif c == 0x08 or c == 0x7F:
                if cmd:
                    cmd = cmd[:-1]
                    sys.stdout.write("\x08 \x08")
            elif 0x20 <= c <= 0x7E:
                cmd += b
                sys.stdout.write(b)
            # other control characters are ignored
PYEOF

	# WebREPL/WebSocket rely on the native `_webrepl` and `websocket` C modules,
	# which are not built for web and which depend on raw sockets (unavailable
	# in the browser sandbox). The webserver code only instantiates these inside
	# connection handlers that never fire here (sockets are stubbed), so plain
	# import-satisfying stubs are sufficient to let the boot import chain
	# complete.
	echo "Injecting web-only _webrepl and websocket stubs into staged lib/..."
	cat > "$staged_fs"/lib/_webrepl.py <<'PYEOF'
# Stub for the native `_webrepl` module (unavailable in the web build).


class _webrepl:
    def __init__(self, *args, **kwargs):
        raise OSError("_webrepl not available in the web build")


def password(*args, **kwargs):
    pass
PYEOF
	cat > "$staged_fs"/lib/websocket.py <<'PYEOF'
# Stub for the native `websocket` module (unavailable in the web build).


class websocket:
    def __init__(self, *args, **kwargs):
        raise OSError("websocket not available in the web build")
PYEOF

	# Web-only `aiohttp` shim backed by the _webnet native fetch() bridge.
	# Overwrites only __init__.py in the staged aiohttp package so the real
	# socket-based implementation (which cannot work in the browser) is shadowed
	# while leaving the device tree untouched. Provides the surface MPOS uses:
	# ClientSession + get/post/put/delete returning an async context manager with
	# .status, .headers (dict) and a streaming .content.read(n). WebSocket
	# (ws_connect) is not implemented here yet and raises a clear error.
	echo "Injecting web-only aiohttp (fetch) shim into staged lib/aiohttp/..."
	mkdir -p "$staged_fs"/lib/aiohttp
	cat > "$staged_fs"/lib/aiohttp/__init__.py <<'PYEOF'
# Browser (Emscripten) aiohttp shim — HTTP(S) via the _webnet fetch() bridge.
#
# Raw TCP sockets are unavailable in the browser (MICROPY_PY_SOCKET is off), so
# the device's socket-based aiohttp cannot run here. This shim implements the
# subset of the aiohttp client API that MicroPythonOS uses, on top of the
# non-blocking _webnet native module. Polling yields to the asyncio loop so the
# LVGL/UI task handler keeps running during requests.

import asyncio
import json as _json
import time
import _webnet

# WSMsgType comes from the (import-clean) device aiohttp_ws module; the browser
# WebSocket transport is implemented below on top of the _webnet native bridge.
from .aiohttp_ws import WSMsgType  # noqa: F401

HttpVersion10 = "HTTP/1.0"
HttpVersion11 = "HTTP/1.1"

__all__ = (
    "ClientSession",
    "ClientResponse",
    "ClientWebSocketResponse",
    "WebSocketClient",
    "WSMsgType",
    "HttpVersion10",
    "HttpVersion11",
)

_POLL_MS = 20


class _Content:
    # Minimal StreamReader-like object serving an in-memory body in chunks.
    def __init__(self, body):
        self._body = body
        self._pos = 0

    async def read(self, n=-1):
        if self._pos >= len(self._body):
            return b""
        if n is None or n < 0:
            chunk = self._body[self._pos:]
            self._pos = len(self._body)
        else:
            chunk = self._body[self._pos:self._pos + n]
            self._pos += len(chunk)
        return chunk

    async def readexactly(self, n):
        return await self.read(n)

    async def readline(self):
        if self._pos >= len(self._body):
            return b""
        nl = self._body.find(b"\n", self._pos)
        if nl < 0:
            chunk = self._body[self._pos:]
            self._pos = len(self._body)
        else:
            chunk = self._body[self._pos:nl + 1]
            self._pos = nl + 1
        return chunk


class ClientResponse:
    def __init__(self, handle, status, headers, body):
        self._handle = handle
        self.status = status
        self.headers = headers
        self.url = None
        self._body = body
        self.content = _Content(body)

    def _get_header(self, name, default=None):
        for k in self.headers:
            if k.lower() == name.lower():
                return self.headers[k]
        return default

    async def read(self, sz=-1):
        return self._body

    async def text(self, encoding="utf-8"):
        return self._body.decode(encoding)

    async def json(self):
        return _json.loads(self._body)

    def release(self):
        if self._handle is not None:
            _webnet.free(self._handle)
            self._handle = None

    def __repr__(self):
        return "<ClientResponse %s %s>" % (self.status, self.headers)


class _RequestContextManager:
    def __init__(self, coro):
        self._coro = coro
        self._resp = None

    async def __aenter__(self):
        self._resp = await self._coro
        return self._resp

    async def __aexit__(self, *args):
        if self._resp is not None:
            self._resp.release()
        return False

    def __await__(self):
        return self._coro.__await__()


# --- WebSocket support (browser WebSocket via the _webnet bridge) -----------

_WS_TEXT = 1
_WS_BINARY = 2
_WS_CLOSE = 8


class _WSMessage:
    def __init__(self, type, data):
        self.type = type
        self.data = data


class WebSocketClient:
    # Browser-backed WebSocket. Provides the small surface MPOS reads via
    # `ws.ws` (the .closed flag and the TEXT/BINARY/CLOSE opcodes) plus the
    # receive()/send()/close() coroutines used by ClientWebSocketResponse.
    CLOSE = _WS_CLOSE
    TEXT = _WS_TEXT
    BINARY = _WS_BINARY

    def __init__(self, handle):
        self._handle = handle
        self.closed = False

    async def receive(self):
        # Drain any queued message first, then report closure. Non-blocking:
        # yields to the asyncio loop so the UI keeps running.
        while True:
            t = _webnet.ws_peek_type(self._handle)
            if t:
                data = _webnet.ws_read(self._handle)
                if t == _WS_TEXT:
                    data = str(data, "utf-8")
                return t, data
            if _webnet.ws_state(self._handle) == 3:  # CLOSED
                self.closed = True
                return self.CLOSE, b""
            await asyncio.sleep_ms(_POLL_MS)

    async def send(self, data, opcode=None):
        if isinstance(data, str):
            _webnet.ws_send_text(self._handle, data)
        else:
            _webnet.ws_send_bytes(self._handle, data)

    async def close(self):
        if not self.closed:
            self.closed = True
            _webnet.ws_close(self._handle)


class ClientWebSocketResponse:
    def __init__(self, wsclient):
        self.ws = wsclient

    def __aiter__(self):
        return self

    async def __anext__(self):
        t, data = await self.ws.receive()
        if (not data and t == self.ws.CLOSE) or self.ws.closed:
            raise StopAsyncIteration
        return _WSMessage(t, data)

    async def receive(self):
        t, data = await self.ws.receive()
        return _WSMessage(t, data)

    async def close(self):
        await self.ws.close()

    async def send_str(self, data):
        if not isinstance(data, str):
            raise TypeError("data argument must be str (%r)" % type(data))
        await self.ws.send(data)

    async def send_bytes(self, data):
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("data argument must be byte-ish (%r)" % type(data))
        await self.ws.send(data)

    async def send_json(self, data):
        await self.send_str(_json.dumps(data))

    async def receive_str(self):
        msg = await self.receive()
        if msg.type != self.ws.TEXT:
            raise TypeError("Received message %s:%r is not str" % (msg.type, msg.data))
        return msg.data

    async def receive_bytes(self):
        msg = await self.receive()
        if msg.type != self.ws.BINARY:
            raise TypeError("Received message %s:%r is not bytes" % (msg.type, msg.data))
        return msg.data

    async def receive_json(self):
        return _json.loads(await self.receive_str())


class _WSRequestContextManager:
    def __init__(self, url, protocols):
        self._url = url
        self._protocols = protocols
        self._resp = None

    async def _connect(self):
        handle = _webnet.ws_open(self._url, _json.dumps(self._protocols or []))
        # Wait for the socket to open (or fail), yielding to the asyncio loop.
        while True:
            state = _webnet.ws_state(handle)
            if state == 1:  # OPEN
                break
            if state == 3:  # CLOSED before opening => failed
                err = _webnet.ws_error(handle) or "websocket connection failed"
                _webnet.ws_free(handle)
                raise OSError("ws_connect failed: " + err)
            await asyncio.sleep_ms(_POLL_MS)
        self._resp = ClientWebSocketResponse(WebSocketClient(handle))
        return self._resp

    async def __aenter__(self):
        return await self._connect()

    async def __aexit__(self, *args):
        if self._resp is not None:
            await self._resp.close()
            _webnet.ws_free(self._resp.ws._handle)
        return False

    def __await__(self):
        return self._connect().__await__()


class ClientSession:
    def __init__(self, base_url="", headers=None, **kwargs):
        self._base_url = base_url or ""
        self._base_headers = dict(headers) if headers else {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def close(self):
        pass

    async def _request(self, method, url, data=None, json=None, headers=None,
                       timeout=None, **kwargs):
        full = self._base_url + url
        merged = dict(self._base_headers)
        if headers:
            merged.update(headers)

        body = None
        if json is not None:
            body = _json.dumps(json).encode()
            if not any(k.lower() == "content-type" for k in merged):
                merged["Content-Type"] = "application/json"
        elif data is not None:
            body = data if isinstance(data, (bytes, bytearray)) else str(data).encode()

        handle = _webnet.fetch_start(method, full, _json.dumps(merged), body)

        deadline = None
        if timeout:
            deadline = time.ticks_add(time.ticks_ms(), int(timeout * 1000))

        # Non-blocking poll: yield to the asyncio loop so the UI stays live.
        while True:
            state = _webnet.poll(handle)
            if state == 1:
                break
            if state == -1:
                err = _webnet.error(handle)
                _webnet.free(handle)
                raise OSError("fetch failed: " + err)
            if deadline is not None and time.ticks_diff(time.ticks_ms(), deadline) > 0:
                _webnet.free(handle)
                raise OSError("fetch timeout")
            await asyncio.sleep_ms(_POLL_MS)

        status = _webnet.status(handle)
        try:
            hdrs = _json.loads(_webnet.headers(handle))
        except Exception:
            hdrs = {}
        body_bytes = _webnet.body(handle)
        resp = ClientResponse(handle, status, hdrs, body_bytes)
        resp.url = full
        return resp

    def request(self, method, url, **kwargs):
        return _RequestContextManager(self._request(method, url, **kwargs))

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def put(self, url, **kwargs):
        return self.request("PUT", url, **kwargs)

    def delete(self, url, **kwargs):
        return self.request("DELETE", url, **kwargs)

    def ws_connect(self, url, *, protocols=(), headers=None, ssl=None, **kwargs):
        # Browser WebSocket. Note: the browser WebSocket API cannot set custom
        # request headers, so `headers` (and the session headers) are ignored;
        # `ssl` is handled automatically for wss:// URLs.
        return _WSRequestContextManager(url, list(protocols))
PYEOF

	# Web-only replacement for the frozen `task_handler` driver. The stock
	# driver in lvgl_micropython drives LVGL from a `machine.Timer` interrupt,
	# but `machine_timer.c` is removed from the web build (no native timers).
	# This shim keeps the exact same public API but drives LVGL from an asyncio
	# task instead, integrating with the asyncio loop that TaskManager.start()
	# runs via asyncio.run(). main.py does `sys.path.insert(0, "lib")`, so this
	# file (in /lib) shadows the frozen module.
	cat > "$staged_fs"/lib/task_handler.py <<'PYEOF'
# Web (Emscripten) replacement for the frozen task_handler driver.
# Same public API as lvgl_micropython's task_handler.TaskHandler, but driven
# by an asyncio task instead of machine.Timer (unavailable in the web build).

import lvgl as lv  # NOQA
import sys
import time
import asyncio


TASK_HANDLER_STARTED = 0x01
TASK_HANDLER_FINISHED = 0x02

_default_timer_id = 0


class _DefaultUserData(object):
    pass


def _default_exception_hook(e):
    sys.print_exception(e)  # NOQA
    TaskHandler._current_instance.deinit()  # NOQA


class TaskHandler(object):
    _current_instance = None

    def __init__(
        self,
        duration=33,
        timer_id=_default_timer_id,
        max_scheduled=2,
        exception_hook=_default_exception_hook
    ):
        if TaskHandler._current_instance is not None:
            self.__dict__.update(TaskHandler._current_instance.__dict__)
        else:
            if not lv.is_initialized():
                lv.init()

            TaskHandler._current_instance = self

            self._callbacks = []
            self.duration = duration
            self.exception_hook = exception_hook
            self.max_scheduled = max_scheduled

            self._start_time = time.ticks_ms()  # NOQA
            self._running = False
            self._disabled = 0
            self._deinited = False
            # asyncio.create_task works before the loop is running in
            # MicroPython (the global task queue is a singleton), so the task
            # starts as soon as TaskManager.start() calls asyncio.run().
            self._task = asyncio.create_task(self._run_loop())

    async def _run_loop(self):
        while not self._deinited:
            if self._disabled <= 0:
                self._task_handler()
            await asyncio.sleep_ms(self.duration)

    def add_event_cb(self, callback, event, user_data=_DefaultUserData):
        for i, (cb, evt, data) in enumerate(self._callbacks):
            if cb == callback:
                evt = event
                if user_data != _DefaultUserData:
                    data = user_data

                self._callbacks[i] = (cb, evt, data)
                break
        else:
            if user_data == _DefaultUserData:
                user_data = None

            self._callbacks.append((callback, event, user_data))

    def remove_event_cb(self, callback):
        for (cb, evt, data) in self._callbacks:
            if cb == callback:
                self._callbacks.remove((cb, evt, data))
                break

    def deinit(self):
        self._deinited = True
        if TaskHandler._current_instance is self:
            TaskHandler._current_instance = None

    def disable(self):
        self._disabled += 1

    def enable(self):
        self._disabled -= 1

    @classmethod
    def is_running(cls):
        return cls._current_instance is not None

    def _task_handler(self):
        try:
            if lv._nesting.value == 0:  # NOQA
                self._running = True

                run_update = True
                for cb, evt, data in self._callbacks:
                    if not evt & TASK_HANDLER_STARTED:
                        continue

                    try:
                        if cb(TASK_HANDLER_STARTED, data) is False:
                            run_update = False

                    except Exception as err:  # NOQA
                        if (
                            self.exception_hook and
                            self.exception_hook != _default_exception_hook
                        ):
                            self.exception_hook(err)
                        else:
                            sys.print_exception(err)  # NOQA
                        print(f"TaskHandler callback {cb} threw exception, disabling it")
                        self.remove_event_cb(cb)

                stop_time = time.ticks_ms()  # NOQA
                ticks_diff = time.ticks_diff(stop_time, self._start_time)  # NOQA
                self._start_time = stop_time
                lv.tick_inc(ticks_diff)

                if run_update:
                    try:
                        lv.task_handler()
                    except Exception as e:
                        print(f"lv.task_handler() threw exception: {e}")
                        sys.print_exception(e)

                    start_time = time.ticks_ms()  # NOQA

                    for cb, evt, data in self._callbacks:
                        if not evt & TASK_HANDLER_FINISHED:
                            continue

                        try:
                            cb(TASK_HANDLER_FINISHED, data)
                        except Exception as err:  # NOQA
                            if (
                                self.exception_hook and
                                self.exception_hook != _default_exception_hook
                            ):
                                self.exception_hook(err)
                            else:
                                sys.print_exception(err)  # NOQA

                    stop_time = time.ticks_ms()  # NOQA
                    ticks_diff = time.ticks_diff(stop_time, start_time)  # NOQA
                    lv.tick_inc(ticks_diff)

                self._running = False

        except Exception as e:
            self._running = False

            if self.exception_hook:
                self.exception_hook(e)
PYEOF

	# Web-only `machine.Timer` replacement. The native timer (machine_timer.c)
	# is removed from the web build, but MicroPythonOS code (connectivity
	# manager, several apps via `from machine import Timer`) expects the
	# standard periodic/one-shot Timer API. This asyncio-backed implementation
	# provides the same surface and is injected into the native `machine`
	# module at boot (see the staged main.py patch below).
	cat > "$staged_fs"/lib/_web_machine_timer.py <<'PYEOF'
# asyncio-backed machine.Timer replacement for the WebAssembly/Emscripten build.
import asyncio


class Timer:
    ONE_SHOT = 0
    PERIODIC = 1

    def __init__(self, id=-1, **kwargs):
        self.id = id
        self._task = None
        self._mode = Timer.PERIODIC
        self._period = 0
        self._callback = None
        if kwargs:
            self.init(**kwargs)

    def init(self, mode=PERIODIC, period=-1, callback=None, **kwargs):
        self.deinit()
        self._mode = mode
        self._period = period
        self._callback = callback
        if period is not None and period >= 0:
            # create_task works before the asyncio loop is running in
            # MicroPython (singleton task queue); the timer starts once
            # TaskManager.start() calls asyncio.run().
            self._task = asyncio.create_task(self._run())

    async def _run(self):
        try:
            while True:
                await asyncio.sleep_ms(self._period)
                cb = self._callback
                if cb is not None:
                    try:
                        cb(self)
                    except Exception as e:
                        import sys
                        sys.print_exception(e)
                if self._mode == Timer.ONE_SHOT:
                    break
        except asyncio.CancelledError:
            pass

    def deinit(self):
        if self._task is not None:
            try:
                self._task.cancel()
            except Exception:
                pass
            self._task = None
PYEOF

	# Inject machine.Timer into the native `machine` module at the very start of
	# boot, before any MicroPythonOS code runs. Patch the STAGED copy of main.py
	# only (never the source device file). Insert right after the
	# `sys.path.insert(0, "lib")` line so lib/ is importable.
	python3 - "$staged_fs"/main.py <<'PYEOF'
import sys
path = sys.argv[1]
with open(path) as f:
    src = f.read()
anchor = 'sys.path.insert(0, "lib")\n'
inject = (
    '\n# Web build: native machine.Timer is unavailable (machine_timer.c is\n'
    '# removed). The native `machine` module dict is read-only, so install an\n'
    '# asyncio-backed Timer by replacing sys.modules["machine"] with a thin\n'
    '# wrapper that delegates every other attribute to the native module.\n'
    'try:\n'
    '    import machine as _native_machine\n'
    '    if not hasattr(_native_machine, "Timer"):\n'
    '        import sys as _sys\n'
    '        import _web_machine_timer\n'
    '        class _MachineWrapper:\n'
    '            Timer = _web_machine_timer.Timer\n'
    '            def __getattr__(self, name):\n'
    '                return getattr(_native_machine, name)\n'
    '        _sys.modules["machine"] = _MachineWrapper()\n'
    'except Exception as _e:\n'
    '    print("could not install web machine.Timer:", _e)\n'
)
if anchor in src and 'import _web_machine_timer' not in src:
    src = src.replace(anchor, anchor + inject, 1)
    with open(path, 'w') as f:
        f.write(src)
    print("Injected web machine.Timer into staged main.py")
else:
    print("WARNING: could not inject machine.Timer (anchor missing or already present)")
PYEOF

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

