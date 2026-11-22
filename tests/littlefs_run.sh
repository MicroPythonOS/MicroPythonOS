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

# Shared helpers, injected into every generated case file. The header includes
# the runner header itself, because --include replaces that default.
cp "$root/tests/relocate_test_helpers.h" "$work/"
cp "$root/tests/relocate_test_helpers.h" "$work/tests/"

# An older copy may have been left under the flattened file name.
rm -f "$work"/tests/littlefs_test_extent.*
rm -f "$work"/tests/test_relocate.t.* "$work"/tests/test_extent.t.*
cp "$root/tests/littlefs_test_extent.toml" "$work/tests/test_extent.toml"
cp "$root/tests/littlefs_test_relocate.toml" "$work/tests/test_relocate.toml"

cd "$work"
# Power loss: none/linear cut once at every write offset, which is bounded.
# The {} entries add fixed two-cut sequences at the points a relocation and a
# file move interleave. Do NOT use -Pexhaustive here: it forks a full device
# copy at every cut point and the tree of copies needs gigabytes (it has
# OOM-killed this machine).
make test NO_COV=1 -j4 \
    TESTFLAGS="tests/test_extent.toml tests/test_relocate.toml \
        -P none,linear,{1,1},{1,2},{2,1},{3,3}" \
    TESTCFLAGS="--include=relocate_test_helpers.h"
