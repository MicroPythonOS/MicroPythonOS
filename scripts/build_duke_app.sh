#!/bin/sh
# Build Duke3D's engines and populate the flat app directory.
#
#   ./scripts/build_duke_app.sh
#
# Outputs, all in internal_filesystem/apps/com.micropythonos.duke3d/:
#
#   module_x64.mpy   desktop native module (the manifest's "x64" key)
#   esp32s3.xip      S3 flash-resident core (the manifest's "esp32s3" key)
#
# The engine source is shared: the core build compiles the pristine tree, and
# the native module first rewrites it into gen/ (no data section, no static
# BSS). Building the S3 core needs the Xtensa toolchain (XTENSA_BIN, see
# c_mpos/duke3d/build_duke_core.sh); pass --desktop to build only the module.

set -eu

root=$(cd "$(dirname "$0")/.." && pwd)
duke=$root/c_mpos/duke3d
app=$root/internal_filesystem/apps/com.micropythonos.duke3d

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

if [ ! -f "$app/E1L1-4_compromise.grp.zip" ]; then
    echo "ERROR: $app/E1L1-4_compromise.grp.zip is missing" >&2
    exit 1
fi

echo "Building the x64 native module..."
make -C "$duke" ARCH=x64 MOD=module_x64 BUILD=build_x64
cp "$duke/module_x64.mpy" "$app/module_x64.mpy"

if [ "$desktop_only" -eq 0 ]; then
    echo "Building the ESP32-S3 core..."
    "$duke/build_duke_core.sh"
    cp "$duke/build_core/esp32s3.xip" "$app/esp32s3.xip"
fi

echo "--- app directory"
ls -l "$app"
