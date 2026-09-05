#!/bin/bash

scriptdir=$(cd "$(dirname "$0")" && pwd -P)

# Optional CPU throttling to simulate a slow device (mirrors test_runner.py --cpulimit).
# Usage: ./scripts/run_desktop.sh [--cpulimit PERCENT] [scriptfile.py|appname]
cpulimit=""
args=()
while [ $# -gt 0 ]; do
    case "$1" in
        --cpulimit)
            if [ -z "$2" ]; then
                echo "ERROR: --cpulimit requires a value between 1 and 100" >&2
                exit 1
            fi
            cpulimit="$2"
            shift 2
            ;;
        --cpulimit=*)
            cpulimit="${1#--cpulimit=}"
            shift
            ;;
        -h|--help)
            echo "Usage:"
            echo "$0 [--cpulimit PERCENT] # with no arguments just starts it up normally"
            echo "$0 [--cpulimit PERCENT] scriptfile.py # doesn't initialize anything, just runs scriptfile.py directly"
            echo "$0 [--cpulimit PERCENT] appname # starts the app by appname, for example: com.example.helloworld"
            echo "--cpulimit PERCENT: throttle the desktop MicroPython process to PERCENT% CPU"
            echo "  (1-100, desktop only). Useful for reproducing timing-sensitive failures"
            echo "  on slow devices/runners. Requires cpulimit to be installed."
            exit 0
            ;;
        *)
            args+=("$1")
            shift
            ;;
    esac
done
set -- "${args[@]:-}"

if [ -n "$cpulimit" ]; then
    case "$cpulimit" in
        ''|*[!0-9]*)
            echo "ERROR: --cpulimit must be between 1 and 100" >&2
            exit 1
            ;;
    esac
    if [ "$cpulimit" -lt 1 ] || [ "$cpulimit" -gt 100 ]; then
        echo "ERROR: --cpulimit must be between 1 and 100" >&2
        exit 1
    fi
    if ! command -v cpulimit >/dev/null 2>&1; then
        echo "ERROR: --cpulimit requires cpulimit to be installed" >&2
        exit 1
    fi
fi

# Prefix the binary invocation with cpulimit when throttling was requested.
# (test_runner.py attaches with `cpulimit -p PID -l PCT -q`; here cpulimit
# launches the binary directly, which avoids a PID race in shell.)
run_binary() {
    if [ -n "$cpulimit" ]; then
        echo "Throttling desktop process to ${cpulimit}% CPU with cpulimit"
        cpulimit -l "$cpulimit" -q -- "$@"
    else
        "$@"
    fi
}

script="${1:-}"
if [ -n "$script" ] && [ -f "$script" ]; then
    script="$(cd "$(dirname "$script")" && pwd -P)/$(basename "$script")"
fi

echo "Usage:"
echo "$0 [--cpulimit PERCENT] # with no arguments just starts it up normally"
echo "$0 [--cpulimit PERCENT] scriptfile.py # doesn't initialize anything, just runs scriptfile.py directly"
echo "$0 [--cpulimit PERCENT] appname # starts the app by appname, for example: com.example.helloworld"

#export SDL_WINDOW_FULLSCREEN=true

export HEAPSIZE=8M # default, same a PSRAM on many ESP32-S3 boards
#export HEAPSIZE=16M # on desktop, a bit more is warranted (different C library etc)
#export HEAPSIZE=32M
#export HEAPSIZE=64M # fine for fullscreen 1280x720 slides

os_name=$(uname -s)
if [ "$os_name" = "Darwin" ]; then
    echo "Running on macOS"
    binary="$scriptdir"/../lvgl_micropython/build/lvgl_micropy_macOS
else
    echo "Running on $os_name"
    binary="$scriptdir"/../lvgl_micropython/build/lvgl_micropy_unix
fi
binary="$(cd "$(dirname "$binary")" && pwd -P)/$(basename "$binary")"
chmod +x "$binary"

pushd "$scriptdir"/../internal_filesystem/

if [ -f "$script" ]; then
    echo "Running script $script"
    run_binary "$binary" -v -i "$script"
else
    CONFIG_FILE="prefs/com.micropythonos.settings/config.json"
    set_autostart_config() {
        local mode="$1"
        local early_value="$2"
        mkdir -p "$(dirname "$CONFIG_FILE")"
        python3 - "$CONFIG_FILE" "$mode" "$early_value" <<'PY'
import json
import os
import sys

path = sys.argv[1]
mode = sys.argv[2]
early_value = sys.argv[3]

config = {}
if os.path.exists(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            if isinstance(loaded, dict):
                config = loaded
    except Exception:
        config = {}

if mode == "set":
    config["auto_start_app_early"] = early_value
elif mode == "clear":
    config.pop("auto_start_app_early", None)

config.pop("auto_start_app", None)

with open(path, "w", encoding="utf-8") as f:
    json.dump(config, f, separators=(",", ":"))
PY
    }

    if [ -n "$script" ]; then
        echo "run_desktop.sh: running app $script"
        set_autostart_config "set" "$script"
    else
        echo "Clearing auto_start_app_early and auto_start_app in config file"
        set_autostart_config "clear" ""
    fi
    run_binary "$binary" -X heapsize=$HEAPSIZE -v -i -m main # internal_filesystem/main.py is frozen in and can't be changed after compilation
    # Useful for testing a slow device (manual equivalent of --cpulimit):
    # cpulimit -l 1 -- "$binary" -X heapsize=$HEAPSIZE -v -i -m main # internal_filesystem/main.py is frozen in and can't be changed after compilation
fi

popd
