#!/bin/sh
# Run the littlefs2e extent and defragmentation cases against the fork.
#
# The source is the third_party/littlefs2e submodule, unprefixed and
# upstream-style, exactly what scripts/sync_littlefs2e.sh prefixes for the
# firmware. No copy and no download: this runs the pinned revision directly.
#
#   ./tests/littlefs_run.sh          extent and defragmentation cases
#   ./tests/littlefs_run.sh --full   the whole upstream suite as well
set -eu

root=$(cd "$(dirname "$0")/.." && pwd)
src="$root/third_party/littlefs2e"

if [ ! -f "$src/lfs.c" ]; then
    echo "FATAL: third_party/littlefs2e is missing; fetch the submodule with:" >&2
    echo "         git submodule update --init third_party/littlefs2e" >&2
    exit 1
fi

if ! python3 -c "import toml" >/dev/null 2>&1; then
    echo "FATAL: the littlefs test runner needs the 'toml' module:" >&2
    echo "         python3 -m pip install toml" >&2
    exit 1
fi

cd "$src"

if [ "${1:-}" = "--full" ]; then
    make test NO_COV=1 -j4
    exit 0
fi

# Power loss: none/linear cut once at every write offset, which is bounded.
# The {} entries add fixed two-cut sequences at the points a relocation and a
# file move interleave. Do NOT use -Pexhaustive here: it forks a full device
# copy at every cut point and the tree of copies needs gigabytes (it has
# OOM-killed this machine).
make test NO_COV=1 -j4 \
    TESTFLAGS="tests/test_extent.toml tests/test_extent_defrag.toml \
        -P none,linear,{1,1},{1,2},{2,1},{3,3}"
