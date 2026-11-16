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

echo "--- sections"
xtensa-esp32-elf-objdump -h "$base.elf" | awk '$2 ~ /^\./ && $2 != ".debug" {print $2, $3, $4}'
echo "--- size: $(stat -c%s "$base.bin") bytes"
