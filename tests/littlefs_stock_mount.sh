#!/bin/sh
# A 2.1 image with an extent, written by the fork and read by stock littlefs.
#
#   ./tests/littlefs_stock_mount.sh
#
# This is the compatibility claim in one run:
#
#   1. the littlefs2e fork formats a 2.1 image, writes a normal file and a
#      contiguous extent, and the extent's CRC reads back intact;
#   2. stock littlefs v2.11.3 mounts the same image, reads the normal file, and
#      sees the extent's inode (its payload is an unknown struct attribute);
#   3. a stock write that fills the free space overwrites the extent's blocks -
#      stock treats them as free - and the fork's CRC check catches it. That is
#      why stock tools must be read-only on such an image.
#
# The upstream suites are in tests/littlefs_run.sh; this one needs two builds
# of the same test program, one against each source tree.
set -eu

root=$(cd "$(dirname "$0")/.." && pwd)
work="$root/third_party/littlefs2e"
stock="$root/tmp/littlefs-stock"
out="$root/tmp/littlefs-stock-mount"
image="$out/test.img"

if [ ! -f "$work/lfs.c" ]; then
    echo "FATAL: third_party/littlefs2e is missing; fetch the submodule with:" >&2
    echo "         git submodule update --init third_party/littlefs2e" >&2
    exit 1
fi
if [ ! -f "$stock/lfs.c" ]; then
    mkdir -p "$stock"
    echo "Downloading littlefs v2.11.3..."
    curl -sL https://github.com/littlefs-project/littlefs/archive/refs/tags/v2.11.3.tar.gz \
        | tar xz -C "$stock" --strip-components=1
fi
mkdir -p "$out"

cc -std=c99 -O1 -I"$work" -I"$work/bd" -DHAVE_EXTENTS \
    "$root/tests/littlefs_stock_mount.c" "$work/lfs.c" "$work/lfs_util.c" \
    "$work/bd/lfs_filebd.c" -o "$out/fork"
cc -std=c99 -O1 -I"$stock" -I"$stock/bd" \
    "$root/tests/littlefs_stock_mount.c" "$stock/lfs.c" "$stock/lfs_util.c" \
    "$stock/bd/lfs_filebd.c" -o "$out/stock"

echo "1. creating the image with the fork"
"$out/fork" create "$image"

echo "2. reading it with stock littlefs"
"$out/stock" read "$image"

echo "3. the fork's CRC over the intact extent"
"$out/fork" check "$image"

echo "4. filling the free space with stock littlefs"
"$out/stock" clobber "$image"

echo "5. the fork's CRC again (a mismatch is the expected result)"
if "$out/fork" check "$image"; then
    echo "FAIL: the extent survived a stock write; the test filled the wrong blocks" >&2
    exit 1
fi

echo "OK: stock littlefs mounts 2.1 images with extents, sees the normal files, and a stock write is caught by the CRC"
