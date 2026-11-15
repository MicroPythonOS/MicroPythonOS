#!/bin/bash
# Prepare the updates repo (OTA metadata) for a release.
# See scripts/release_metadata.py and ../docs/docs/other/release-checklist.md.
set -euo pipefail
dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$dir/release_metadata.py" "$@" --updates-only
