#!/bin/bash
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
boot_dir="$root/tmp/d_shell_boot"
python3 "$root/scripts/d_shell/prepare_boot.py" --output "$boot_dir"
MPOS_BOOT_DIR="$boot_dir" bash "$root/scripts/build_mpos.sh" esp32s3 "$@"
