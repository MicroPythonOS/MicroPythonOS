#!/bin/sh
# Pack internal_filesystem/ into a littlefs2e image with the vendored tool.
#
# Native cores (*.xip) are packed as extents: one contiguous, 64 KiB aligned
# run that a badge maps straight out of flash, so the first launch does not
# have to defragment and convert them.
set -eu

mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir")
root=$(dirname "$mydir")
tool="$root/third_party/mklittlefs/mklittlefs"

if [ ! -x "$tool" ]; then
    "$mydir"/build_mklittlefs.sh
fi

size=0x700000 # 7 MB filesystem

extents=""
for xip in "$root"/internal_filesystem/apps/*/*.xip; do
    [ -f "$xip" ] || continue
    relative=${xip#"$root"/internal_filesystem/}
    extents="$extents -x $relative"
done

# shellcheck disable=SC2086
"$tool" -b 4096 -c "$root"/internal_filesystem/ -s "$size" $extents internal_filesystem.bin
