#!/bin/sh
# Build Doom's engines and populate the flat app directory.
#
#   ./scripts/build_doom_app.sh
#
# Outputs, all in internal_filesystem/apps/com.micropythonos.doom/:
#
#   module_x64.mpy   desktop native module (the manifest's "x64" key)
#   esp32s3.xip      S3 flash-resident core (the manifest's "esp32s3" key)
#   doom1.wad.zip    shareware WAD, deflated (common file, unpacked at launch)
#
# The AppStore installs only the files for the running host (mpos.platform), so
# both engines can live in one package. Building the S3 core needs the Xtensa
# toolchain (XTENSA_BIN, see c_mpos/doom/core/build_doom_core.sh); pass
# --desktop to build only the native module.

set -eu

root=$(cd "$(dirname "$0")/.." && pwd)
doom=$root/c_mpos/doom
app=$root/internal_filesystem/apps/com.micropythonos.doom
wad=$root/internal_filesystem/doom1.wad

# mpy_ld needs the `ar` package and pyelftools for the system toolchain here;
# a local venv is where this workspace keeps them (system pip is blocked).
if [ -d "$root/tmp/venv/bin" ]; then
    PATH="$root/tmp/venv/bin:$PATH"
    export PATH
fi

desktop_only=0
if [ "${1:-}" = "--desktop" ]; then
    desktop_only=1
fi

echo "Building the x64 native module..."
make -C "$doom" ARCH=x64 MOD=module_x64 BUILD=build_x64
cp "$doom/module_x64.mpy" "$app/module_x64.mpy"

if [ "$desktop_only" -eq 0 ]; then
    echo "Building the ESP32-S3 core..."
    "$doom/core/build_doom_core.sh"
    cp "$doom/build_core/esp32s3.xip" "$app/esp32s3.xip"
fi

if [ ! -f "$app/doom1.wad.zip" ]; then
    if [ ! -f "$wad" ]; then
        echo "ERROR: $wad is missing; cannot make doom1.wad.zip" >&2
        exit 1
    fi
    echo "Compressing the shareware WAD..."
    (cd "$(dirname "$wad")" && zip -9 -X doom1.wad.zip doom1.wad)
    mv "$(dirname "$wad")/doom1.wad.zip" "$app/doom1.wad.zip"
fi

echo "--- app directory"
ls -l "$app"
