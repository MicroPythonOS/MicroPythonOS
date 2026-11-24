#!/bin/bash
# Build the Duke3D core for the host (Linux) as a debugging harness.
#
#   ./build_host.sh             -> build_host/duke_host
#   cd /tmp/duke && /path/duke_host 300 frame.ppm
#
# It links the real engine and core shims; only the ABI callbacks and the
# clock are the harness's. No fixed addresses, no .data copy, no heap arena.

set -e
mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir")
cd "$mydir"

build=build_host
mkdir -p "$build"

CFLAGS="-O2 -g -std=gnu99 -DMPOS_CORE -DCONFIG_IDF_TARGET_ESP32S3 -DCONFIG_IDF_TARGET_ESP32 -DLINUX -D_DEFAULT_SOURCE -DMPOS_HOST -ffunction-sections -fdata-sections"
CFLAGS="$CFLAGS -Icore -Iengine/Game -Iengine/Engine -Iengine/SDL -Iaudiolib -Ihost -I../doom -I../doom/core"
CFLAGS="$CFLAGS -Wno-int-conversion -Wno-incompatible-pointer-types -w"

sources="host/harness.c"
for src in engine/Game/*.c engine/Engine/*.c; do
    case "$src" in
        *filesystem.c.old|*multi.c.old|*Engine/dummy_multi.c) continue ;;
    esac
    sources="$sources $src"
done
sources="$sources core/duke_platform.c core/sdl_video.c core/sdl_event.c core/sdl_system.c core/sdl_input.c core/duke_audio.c core/lodepng.c"

# The engine's main() is renamed so the harness can own main().
gcc $CFLAGS -Dmain=duke_engine_main -c -x c /dev/null -o "$build/empty.o" 2>/dev/null || true
objs=""
for src in $sources; do
    obj="$build/$(echo "$src" | sed 's|^\.\./|up_|' | tr '/' '_' | sed 's/\.c$/.o/')"
    if [ "$src" = "host/harness.c" ]; then
        gcc $CFLAGS -c "$src" -o "$obj"
    else
        gcc $CFLAGS -Dmain=duke_engine_main -c "$src" -o "$obj"
    fi
    objs="$objs $obj"
done
gcc -o "$build/duke_host" $objs -lm -Wl,--gc-sections -Wl,--allow-multiple-definition
echo "built $mydir/$build/duke_host"
