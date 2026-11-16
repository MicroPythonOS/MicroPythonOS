#!/bin/bash

# Builds framecore_probe_{x64,xtensawin}.mpy and framecore_big_{x64,xtensawin}.mpy.
#
# The xtensa toolchain and a python that can import pyelftools/ar are needed;
# the system python on some hosts refuses pip installs, so point at a venv.
# CI has all of it installed already, in which case plain `make` works.

XTENSA_BIN=${XTENSA_BIN:-$HOME/.espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119/xtensa-esp-elf/bin}
if [ -d "$XTENSA_BIN" ]; then
    export PATH="$XTENSA_BIN:$PATH"
fi

mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir")

cd "$mydir"

rm -rf build_x64 build_xtensawin build_big_x64 build_big_xtensawin
rm -f *.mpy

make </dev/null

# The app ships the .mpy files it imports (like Breakout does): an .mpk has to
# run on firmware that was built before this app existed. The 256 KB "big"
# variant is a measurement artefact only and is not shipped.
appdir="$mydir/../../internal_filesystem/apps/com.micropythonos.framecoreprobe"
cp "$mydir"/framecore_probe_x64.mpy "$appdir"/
cp "$mydir"/framecore_probe_xtensawin.mpy "$appdir"/
