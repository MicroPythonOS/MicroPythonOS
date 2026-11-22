#!/bin/sh
# Copy the littlefs2e sources into the MicroPython tree.
#
# MicroPython vendors littlefs twice, prefixed at compile time (lfs1 and lfs2),
# so extmod/vfs_lfs.c includes lib/littlefs/lfs2.h and calls lfs2_*. The fork
# is upstream-style unprefixed source (lfs.c/lfs.h), so it is prefixed on the
# way in. This runs before every build: the tree always carries the pinned
# submodule revision, never a local edit left behind by an earlier build.
#
# Usage: sync_littlefs2e.sh [--check]
#   --check  report whether the tree matches the submodule and exit non-zero
#            if it does not (used to notice drift without building)
set -eu

root=$(cd "$(dirname "$0")/.." && pwd)
src="$root/third_party/littlefs2e"
tree="$root/lvgl_micropython/lib/micropython/lib/littlefs"
work="$root/tmp/littlefs2e-prefix"

check_only=0
if [ "${1:-}" = "--check" ]; then
    check_only=1
fi

for name in lfs.c lfs.h lfs_util.c lfs_util.h; do
    if [ ! -f "$src/$name" ]; then
        echo "FATAL: $src/$name is missing." >&2
        echo "       littlefs2e is a git submodule; fetch it with:" >&2
        echo "         git submodule update --init third_party/littlefs2e" >&2
        exit 1
    fi
done
if [ ! -f "$src/scripts/changeprefix.py" ]; then
    echo "FATAL: $src/scripts/changeprefix.py is missing; the submodule is incomplete." >&2
    exit 1
fi

rm -rf "$work"
mkdir -p "$work"
cp "$src"/lfs.c "$src"/lfs.h "$src"/lfs_util.c "$src"/lfs_util.h "$work/"
(cd "$work" && python3 "$src/scripts/changeprefix.py" lfs lfs2 \
    lfs.c lfs.h lfs_util.c lfs_util.h >/dev/null)

changed=""
for name in lfs2.c lfs2.h lfs2_util.c lfs2_util.h; do
    if ! cmp -s "$work/$name" "$tree/$name"; then
        changed="$changed $name"
        if [ "$check_only" = "0" ]; then
            cp "$work/$name" "$tree/$name"
        fi
    fi
done
rm -rf "$work"

if [ -n "$changed" ]; then
    if [ "$check_only" = "1" ]; then
        echo "littlefs2e: $tree differs from third_party/littlefs2e:$changed" >&2
        echo "             run scripts/sync_littlefs2e.sh" >&2
        exit 1
    fi
    echo "littlefs2e: updated$changed from $(git -C "$src" describe --tags --always 2>/dev/null || echo unknown)"
else
    echo "littlefs2e: $tree is in sync with the submodule"
fi
