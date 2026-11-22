#!/bin/sh
# Build the mklittlefs used to pack the preloaded filesystem.
#
# The tool is the third_party/mklittlefs submodule: the littlefs2e fork of
# mklittlefs, which can pack a file as an extent (-x). Building it in place
# leaves only ignored artefacts in the submodule.
#
#   scripts/build_mklittlefs.sh           # build if needed
#   scripts/build_mklittlefs.sh --force   # rebuild from scratch
set -eu

root=$(cd "$(dirname "$0")/.." && pwd)
src="$root/third_party/mklittlefs"
binary="$src/mklittlefs"

if [ ! -f "$src/main.cpp" ]; then
    echo "FATAL: $src is missing; fetch the submodule with:" >&2
    echo "         git submodule update --init --recursive third_party/mklittlefs" >&2
    exit 1
fi

if [ ! -f "$src/littlefs/lfs.c" ]; then
    echo "Initialising mklittlefs's littlefs submodule..."
    git -C "$src" submodule update --init littlefs
fi

if [ "${1:-}" = "--force" ]; then
    make -C "$src" clean >/dev/null 2>&1 || true
fi

jobs=4
if command -v nproc >/dev/null 2>&1; then
    jobs=$(nproc)
fi
make -C "$src" -j"$jobs" >/dev/null

if [ ! -x "$binary" ]; then
    echo "FATAL: $binary was not produced" >&2
    exit 1
fi
echo "mklittlefs: $binary ($("$binary" --version 2>&1 | head -1))"
