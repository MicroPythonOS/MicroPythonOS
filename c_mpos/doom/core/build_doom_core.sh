#!/bin/bash
# Build the Doom engine as an mpos_core blob.
#
#   ./build_doom_core.sh          -> build_core/esp32s3.xip / .elf / .map
#
# The blob is linked for fixed addresses (see doom_core.ld). In a release it is
# shipped in the app package as esp32s3.xip and installed as a littlefs2e
# extent; for a stand-in partition it can still be flashed instead:
#
#   esptool.py write_flash 0x710000 build_core/esp32s3.xip
#
# The engine sources are the same generated tree the native module uses
# (tools/dataless.py rewrites doomgeneric so it has no initialised data), so
# there is one engine build description, not two.

set -e

XTENSA_BIN=${XTENSA_BIN:-$HOME/.espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119/xtensa-esp-elf/bin}
export PATH="$XTENSA_BIN:$PATH"

mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir")
doomdir=$(dirname "$mydir")
cd "$doomdir"

# The engine list lives in the natmod Makefile; use it rather than a second copy.
stems=$(python3 - <<'PY'
import re
text = open("Makefile").read()
match = re.search(r"ENGINE = \\\n(.*?)\n\n", text, re.S)
print(" ".join(path[4:-2] for path in re.findall(r"gen/[\w.]+\.c", match.group(1))))
PY
)

python3 tools/dataless.py doomgeneric gen $stems

build=build_core
rm -rf "$build"
mkdir -p "$build"

# -O2, not -Os: the engine is a software renderer whose inner loops are the
# frame time, and the blob has a megabyte of flash around it.
CFLAGS="-O2 -std=gnu99 -ffreestanding -fno-builtin -fno-common -fno-jump-tables"
CFLAGS="$CFLAGS -ffunction-sections -fdata-sections -mtext-section-literals"
CFLAGS="$CFLAGS -DCMAP256 -DNORMALUNIX -DLINUX -D_DEFAULT_SOURCE -DMPOS_CORE -DFEATURE_SOUND"
CFLAGS="$CFLAGS -Idoomgeneric -Igen -Icore -Icore/stub -I."
# The engine is 1990s C and its warnings are not this build's gate; ours are
# covered by the host build.
CFLAGS="$CFLAGS -w"

sources="core/doom_core.c core/core_libc.c core/core_sound.c mpos_printf.c"
for stem in $stems; do
    sources="$sources gen/$stem.c"
done

pids=()
for src in $sources; do
    obj="$build/$(basename "${src%.c}").o"
    xtensa-esp32-elf-gcc $CFLAGS -c "$src" -o "$obj" &
    pids+=($!)
done
failed=0
for pid in "${pids[@]}"; do
    wait "$pid" || failed=1
done
if [ "$failed" -ne 0 ]; then
    echo "compile failed" >&2
    exit 1
fi

xtensa-esp32-elf-gcc -nostdlib -nostartfiles \
    -Wl,-T,core/doom_core.ld \
    -Wl,--gc-sections \
    -Wl,-Map,"$build/doom_core.map" \
    -o "$build/doom_core.elf" "$build"/*.o -lgcc

xtensa-esp32-elf-objcopy -O binary "$build/doom_core.elf" "$build/esp32s3.xip"

echo "--- sections (name size vma lma)"
xtensa-esp32-elf-objdump -h "$build/doom_core.elf" |
    awk '$2 ~ /^\./ && $2 != ".debug" {print $2, $3, $4, $5}'
echo "--- size: $(stat -c%s "$build/esp32s3.xip") bytes"

# The entry table states where the loader must map the blob; the data offset
# depends on the text size, so it is patched here from the linked sections.
python3 - "$build/doom_core.elf" "$build/esp32s3.xip" <<'PYEOF'
import struct, subprocess, sys

elf, blob = sys.argv[1], sys.argv[2]
data = bytearray(open(blob, "rb").read())

(abi, flags, text_addr, data_addr, data_offset, data_size,
 arena_addr, arena_size) = struct.unpack("<8I", data[:32])

sections = {}
for line in subprocess.run(["xtensa-esp32-elf-objdump", "-h", elf],
                           capture_output=True, text=True).stdout.splitlines():
    parts = line.split()
    if len(parts) >= 7 and parts[1].startswith("."):
        sections[parts[1]] = (int(parts[2], 16), int(parts[3], 16), int(parts[4], 16))

rodata_size, rodata_vma, rodata_lma = sections[".rodata"]
text_lma = sections[".core_entry"][2]
data_offset = rodata_lma - text_lma
data_size = rodata_size

struct.pack_into("<II", data, 16, data_offset, data_size)
open(blob, "wb").write(data)

print("entry: abi=%d text=0x%x data=0x%x offset=0x%x size=%d arena=0x%x+%u"
      % (abi, text_addr, data_addr, data_offset, data_size, arena_addr, arena_size))
assert sections[".core_entry"][1] == text_addr, "entry table is not at load_addr"
assert rodata_vma == data_addr, "data_addr does not match .rodata"
assert sections[".bss"][1] == arena_addr, "arena_addr does not match .bss"
assert sections.get(".data", (0,))[0] == 0, "core has .data: build the tree dataless"
assert data_offset + data_size == len(data), "blob does not end with its data region"
PYEOF
