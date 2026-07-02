#!/bin/bash
# Build (if needed) and serve the MicroPythonOS WebAssembly build locally.
#
# Usage:
#   scripts/run_web.sh           # build then serve on :8080
#   scripts/run_web.sh --no-build # just serve the existing web/ directory
#   PORT=9000 scripts/run_web.sh  # serve on a different port

set -euo pipefail

mydir=$(cd "$(dirname "$0")" && pwd -P)
codebasedir=$(cd "$mydir/.." && pwd -P)
port="${PORT:-8080}"

if [ "${1:-}" != "--no-build" ]; then
	"$mydir/build_mpos_web.sh"
fi

webdir="$codebasedir/web"
if [ ! -f "$webdir/index.html" ]; then
	echo "ERROR: $webdir/index.html not found. Run the build first."
	exit 1
fi

echo "Serving $webdir at http://localhost:$port/"
echo "Press Ctrl-C to stop."
exec python3 -m http.server "$port" -d "$webdir"
