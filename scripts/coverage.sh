#!/bin/bash
# Run MicroPythonOS tests with code coverage and generate HTML reports.
# Requires mpcov build variant: ./scripts/build_mpos.sh unix coverage
#
# Usage:
#   ./scripts/coverage.sh              # full coverage (all tests) + HTML report
#   ./scripts/coverage.sh audio        # audio cluster only
#   ./scripts/coverage.sh apps         # app management cluster only
#   ./scripts/coverage.sh util         # utility cluster only
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEST_RUNNER="$REPO_ROOT/scripts/test_runner.py"
REPORT_SCRIPT="$REPO_ROOT/scripts/coverage_report.py"

# ---- Build coverage binary ----
echo "=== Building mpcov variant ==="
"$REPO_ROOT/scripts/build_mpos.sh" unix coverage

# ---- Partial coverage clusters ----
run_cluster() {
    local name="$1"; shift
    local tests=("$@")
    echo ""
    echo "=== Cluster: $name (${#tests[@]} tests) ==="
    python3 "$TEST_RUNNER" --coverage --coverage-save "tmp/cov_${name}.json" --timeout 60 "${tests[@]}"
    python3 "$REPORT_SCRIPT" "tmp/cov_${name}.json" -o "tmp/coverage_${name}.html"
    echo "  Report: tmp/coverage_${name}.html"
}

# Audio/sound cluster — codec, audio manager, RTTTL parser, error paths
# run_cluster audio \
#   tests/test_adpcm_ima.py \
#   tests/test_audiomanager.py \
#   tests/test_rtttl.py \
#   tests/test_tfl_audio_error.py

# App management cluster — app lifecycle, install, prefs, notifications
# run_cluster apps \
#   tests/test_app.py \
#   tests/test_app_manager.py \
#   tests/test_shared_preferences.py \
#   tests/test_notification_manager.py

# Utility cluster — number formatting, helpers, logging
# run_cluster util \
#   tests/test_number_format.py \
#   tests/test_util.py \
#   tests/test_logging.py

# ---- Full coverage (all non-graphical tests) ----
echo ""
echo "=== Full coverage ==="
python3 "$TEST_RUNNER" --coverage --coverage-save tmp/cov_full.json --timeout 300
python3 "$REPORT_SCRIPT" tmp/cov_full.json -o tmp/coverage_full.html
echo "  Report: tmp/coverage_full.html"
echo ""
echo "Done. Open tmp/coverage_full.html in a browser."
