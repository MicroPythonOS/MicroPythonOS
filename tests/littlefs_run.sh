#!/bin/sh
# Run the littlefs2e extent cases against the patched littlefs source.
set -eu

root=$(cd "$(dirname "$0")/.." && pwd)
work="$root/tmp/littlefs-tests"
src="$root/lvgl_micropython/lib/micropython/lib/littlefs"

if [ ! -d "$work" ]; then
    mkdir -p "$work"
    url=https://github.com/littlefs-project/littlefs/archive/refs/tags/v2.11.3.tar.gz
    curl -L "$url" | tar xz -C "$work" --strip-components=1
fi

# The upstream runner compiles lfs.c in the tree root; our firmware compiles
# the prefixed lfs2.c. Reverse the prefix on a copy so the tests exercise the
# exact source the device gets (including the extent changes).
mkdir -p "$work/build-src"
cp "$src/lfs2.c" "$work/build-src/lfs2.c"
cp "$src/lfs2.h" "$work/build-src/lfs2.h"
cp "$src/lfs2_util.c" "$work/build-src/lfs2_util.c"
cp "$src/lfs2_util.h" "$work/build-src/lfs2_util.h"
(cd "$work/build-src" && python3 ../scripts/changeprefix.py lfs2 lfs \
    lfs2.c lfs2.h lfs2_util.c lfs2_util.h)
cp "$work/build-src"/lfs.c "$work/build-src"/lfs.h \
   "$work/build-src"/lfs_util.c "$work/build-src"/lfs_util.h "$work/"
# An older copy may have been left under the flattened file name.
rm -f "$work"/tests/littlefs_test_extent.*
cp "$root/tests/littlefs_test_extent.toml" "$work/tests/test_extent.toml"

cd "$work"
make test NO_COV=1 -j4 TESTFLAGS="tests/test_extent.toml"
