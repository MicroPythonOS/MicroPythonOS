#!/bin/bash
# Firmware size drill-down for MicroPythonOS ESP32 builds.
# Parses micropython.elf/.map + frozen .mpy tree + sdkconfig, writes a
# terminal report plus drill-down datafiles for treemap/CSV inspection.
#
# Usage:
#   scripts/size.sh [--build-dir <dir>] [--out-dir <dir>] [--label <name>]
#
# Defaults target the ESP32-S3 usbdisplay build and write to tmp/size-reports/.

set -u

mydir=$(readlink -f "$0")
mydir=$(dirname "$mydir")
codebasedir=$(readlink -f "$mydir"/..)

BUILD_DIR="$codebasedir/lvgl_micropython/lib/micropython/ports/esp32/build-ESP32_GENERIC_S3-SPIRAM_OCT"
OUT_DIR="$codebasedir/tmp/size-reports"
LABEL="size"

while [ $# -gt 0 ]; do
    case "$1" in
        --build-dir) BUILD_DIR="$2"; shift 2 ;;
        --out-dir) OUT_DIR="$2"; shift 2 ;;
        --label) LABEL="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 [--build-dir <dir>] [--out-dir <dir>] [--label <name>]"
            exit 0
            ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

mkdir -p "$OUT_DIR"
python3 "$mydir/size_analyze.py" --build-dir "$BUILD_DIR" --out-dir "$OUT_DIR" --label "$LABEL"
