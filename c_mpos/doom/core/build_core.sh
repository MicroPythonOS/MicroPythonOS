#!/bin/bash
# Build a core blob and report where its sections landed.
#
#   ./build_core.sh hello_core.c        -> hello_core.bin / .elf / .map
#
# A core is linked at the address the loader maps it at (see core.ld), so the
# result is a flat binary that can be written straight into a partition:
#
#   esptool.py write_flash <partition offset> hello_core.bin

set -e

XTENSA_BIN=${XTENSA_BIN:-$HOME/.espressif/tools/xtensa-esp-elf/esp-14.2.0_20241119/xtensa-esp-elf/bin}
export PATH="$XTENSA_BIN:$PATH"

mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir")
cd "$mydir"

src=${1:-hello_core.c}
base=${src%.c}

xtensa-esp32-elf-gcc \
    -Os -ffreestanding -fno-builtin -fno-common -fno-jump-tables \
    -ffunction-sections -fdata-sections -Wl,--gc-sections \
    -nostdlib -nostartfiles -Wl,-T,core.ld \
    -Wl,-Map,"$base.map" \
    -o "$base.elf" "$src"

xtensa-esp32-elf-objcopy -O binary "$base.elf" "$base.bin"

echo "--- sections (name size vma lma)"
xtensa-esp32-elf-objdump -h "$base.elf" | awk '$2 ~ /^\./ && $2 != ".debug" {print $2, $3, $4, $5}'
echo "--- size: $(stat -c%s "$base.bin") bytes"

# The entry table states where the loader must map the blob, so a mismatch
# between it and the linker script would only show up as a crash on the device.
python3 - "$base.elf" "$base.bin" <<'PYEOF'
import struct, subprocess, sys
elf, blob = sys.argv[1], sys.argv[2]
data = open(blob, "rb").read()
(abi, flags, text_addr, data_addr, data_offset, data_size,
 arena_addr, arena_size) = struct.unpack("<8I", data[:32])
sections = {}
for line in subprocess.run(["xtensa-esp32-elf-objdump", "-h", elf],
                           capture_output=True, text=True).stdout.splitlines():
    parts = line.split()
    if len(parts) >= 7 and parts[1].startswith("."):
        sections[parts[1]] = int(parts[3], 16)
print("entry: abi=%d text=0x%x data=0x%x offset=0x%x size=%d arena=0x%x+%u"
      % (abi, text_addr, data_addr, data_offset, data_size, arena_addr, arena_size))
assert sections.get(".core_entry", 0) == text_addr, "entry table is not at load_addr"
assert sections.get(".data", 0) == 0, "core has .data: build the tree dataless"
if data_addr:
    assert sections.get(".rodata", 0) == data_addr, "data_addr does not match .rodata"
if arena_addr:
    assert sections.get(".bss", 0) == arena_addr, "arena_addr does not match .bss"
PYEOF
