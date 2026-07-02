#!/bin/bash
# Convenience wrapper: build the WebAssembly / Emscripten target of MicroPythonOS.
#
# Activates the in-tree Emscripten SDK if emcc is not already on PATH, then
# delegates to build_mpos.sh which contains the actual web build logic.

set -euo pipefail

mydir=$(cd "$(dirname "$0")" && pwd -P)
codebasedir=$(cd "$mydir/.." && pwd -P)

if ! command -v emcc >/dev/null 2>&1; then
	for envsh in "$codebasedir"/../emsdk/emsdk_env.sh "$codebasedir"/../../emsdk/emsdk_env.sh; do
		if [ -f "$envsh" ]; then
			echo "Sourcing Emscripten env from $envsh"
			# shellcheck disable=SC1090
			source "$envsh"
			break
		fi
	done
fi

exec "$mydir/build_mpos.sh" web "$@"
