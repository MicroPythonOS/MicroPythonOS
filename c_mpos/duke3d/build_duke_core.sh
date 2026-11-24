#!/bin/bash
# Build Duke Nukem 3D as an mpos_core blob.
#
#   ./build_duke_core.sh          -> build_core/esp32s3.xip / .elf / .map
#
# Same two-window layout as the Doom core (see duke_core.ld): text is executed
# from the instruction window, .rodata plus the .data image are mapped in the
# data window, and the engine's globals live in the RAM arena the host maps at
# a fixed address.
#
# The source is the DukeNano3D port of Chocolate Duke3D (retro-go flavour) under
# engine/, with the platform seams in core/. It is a 1990s C engine and its
# warnings are not this build's gate; the host build is where style is checked.

set -e

XTENSA_BIN=${XTENSA_BIN:-$HOME/.espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119/xtensa-esp-elf/bin}
export PATH="$XTENSA_BIN:$PATH"
GCC=xtensa-esp32-elf-gcc

mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir")
cd "$mydir"

build=build_core
rm -rf "$build"
mkdir -p "$build"

# -O2: the renderer's inner loops are the frame time. -fno-common keeps every
# tentative definition in one place so the link can resolve them.
CFLAGS="-O2 -std=gnu99 -ffreestanding -fno-builtin -fno-common"
CFLAGS="$CFLAGS -ffunction-sections -fdata-sections -mtext-section-literals"
CFLAGS="$CFLAGS -DMPOS_CORE -DCONFIG_IDF_TARGET_ESP32S3 -DCONFIG_IDF_TARGET_ESP32 -DLINUX -D_DEFAULT_SOURCE"
CFLAGS="$CFLAGS -Icore -Iengine/Game -Iengine/Engine -Iengine/SDL -Iaudiolib"
CFLAGS="$CFLAGS -I../doom -I../doom/core"
CFLAGS="$CFLAGS -w"
# GCC 14 promoted pointer/int conversions to errors; this is 1990s C that the
# original ESP-IDF build demotes too.
CFLAGS="$CFLAGS -Wno-error=int-conversion -Wno-error=incompatible-pointer-types"
CFLAGS="$CFLAGS -Wno-error=implicit-function-declaration -Wno-error=implicit-int"
CFLAGS="$CFLAGS -Wno-error=return-mismatch -Wno-error=pointer-sign"

sources=""
for src in engine/Game/*.c engine/Engine/*.c core/*.c ../doom/mpos_printf.c; do
    case "$src" in
        *filesystem.c.old|*multi.c.old) continue ;;
        # dummy_multi.c and mmulti.c both define the network globals; same for
        # network.c and mmulti.c's callcommit. The ESP-IDF link tolerates the
        # duplicates, this one does not: keep the stub-networking build.
        *Engine/dummy_multi.c) continue ;;
    esac
    sources="$sources $src"
done

# setjmp/longjmp come from the toolchain's C library; this core links no libc,
# so pull just that object in (it has no dependencies of its own).
NEWLIB_LIBC="$XTENSA_BIN/../xtensa-esp-elf/lib/esp32s3/libc.a"
if [ -f "$NEWLIB_LIBC" ]; then
    ( cd "$build" && xtensa-esp32-elf-ar x "$NEWLIB_LIBC" libc_a-setjmp.o )
    extra_objects="$build/libc_a-setjmp.o"
else
    echo "setjmp object not found in $NEWLIB_LIBC" >&2
    exit 1
fi

pids=()
for src in $sources; do
    obj="$build/$(echo "${src#./}" | sed 's|^\.\./|up_|' | tr '/' '_' | sed 's/\.c$/.o/')"
    $GCC $CFLAGS -c "$src" -o "$obj" &
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

$GCC -nostdlib -nostartfiles \
    -Wl,-T,core/duke_core.ld \
    -Wl,--gc-sections -Wl,--allow-multiple-definition \
    -Wl,-Map,"$build/duke_core.map" \
    -o "$build/duke_core.elf" "$build"/*.o -lgcc

xtensa-esp32-elf-objcopy -O binary "$build/duke_core.elf" "$build/esp32s3.xip"

echo "--- sections (name size vma lma)"
xtensa-esp32-elf-objdump -h "$build/duke_core.elf" |
    awk '$2 ~ /^\./ && $2 != ".debug" {print $2, $3, $4, $5}'
echo "--- size: $(stat -c%s "$build/esp32s3.xip") bytes"

# The entry table states where the loader must map the blob; the data offset
# and the arena size depend on the linked sections, so they are patched here.
python3 - "$build/duke_core.elf" "$build/esp32s3.xip" <<'PYEOF'
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
data_sec_size, data_vma, data_lma = sections.get(".data", (0, arena_addr, rodata_lma + rodata_size))
bss_size, bss_vma, _ = sections[".bss"]
text_lma = sections[".core_entry"][2]
data_offset = rodata_lma - text_lma
data_size = rodata_size + data_sec_size

# .data is linked at the start of the arena, .bss after it.
assert data_vma == arena_addr, "data section is not at arena_addr"
assert bss_vma == arena_addr + data_sec_size, "bss does not follow data"
total = data_sec_size + bss_size
total = (total + 0xFFFF) & ~0xFFFF  # page-aligned: the loader maps page by page

struct.pack_into("<II", data, 16, data_offset, data_size)
struct.pack_into("<I", data, 28, total)
open(blob, "wb").write(data)

print("entry: abi=%d text=0x%x data=0x%x offset=0x%x size=%d arena=0x%x+%u "
      "(data %d, bss %d)"
      % (abi, text_addr, data_addr, data_offset, data_size, arena_addr, total,
         data_sec_size, bss_size))
assert sections[".core_entry"][1] == text_addr, "entry table is not at load_addr"
assert rodata_vma == data_addr, "data_addr does not match .rodata"
assert data_offset + data_size == len(data), "blob does not end with its data region"
PYEOF
